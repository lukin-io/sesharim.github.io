#!/usr/bin/env python3
"""Start, inspect or stop an on-demand Mac VPN relay (until stopped by default)."""

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import subprocess
import sys
import tempfile
import time

from relay_config import load_config, select_profile, snapshot_config


PYTHON = str(Path(sys.executable).resolve())
SOURCE = Path(__file__).resolve().parent
RUNTIME = Path.home() / "Library/Application Support/VPNRelay"
TAILSCALE = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def run_launchctl(*args, timeout=8):
    return subprocess.run(
        ["/bin/launchctl", *args], capture_output=True, text=True, timeout=timeout
    )


def inspect_job(target, timeout=3):
    result = run_launchctl("print", target, timeout=timeout)
    if result.returncode:
        if "Could not find service" in result.stderr:
            return {"loaded": False, "state": "not_loaded", "pid": None}
        raise RuntimeError(f"launchctl print failed (exit {result.returncode})")
    def field(name):
        match = re.search(r"(?m)^\t" + re.escape(name) + r" = ([^\n]+)$", result.stdout)
        return match.group(1).strip() if match else None

    pid = field("pid")
    exit_status = field("last exit code")
    return {
        "loaded": True,
        "state": field("state") or "loaded",
        "pid": int(pid) if pid and pid.isdigit() else None,
        "runs": int(field("runs")) if (field("runs") or "").isdigit() else None,
        "last_exit_status": exit_status,
        "last_exit_code": int(exit_status) if exit_status and re.fullmatch(r"-?\d+", exit_status) else None,
        "last_terminating_signal": field("last terminating signal"),
        "stdout_path": field("stdout path"),
        "stderr_path": field("stderr path"),
    }


def private_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".relay-", dir=RUNTIME)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def mutation_lock():
    if RUNTIME.is_symlink():
        raise RuntimeError("Refusing a symlink as the relay runtime directory")
    RUNTIME.mkdir(parents=True, mode=0o700, exist_ok=True)
    if RUNTIME.stat().st_uid != os.getuid():
        raise RuntimeError("Relay runtime directory belongs to another user")
    RUNTIME.chmod(0o700)
    fd = os.open(RUNTIME / "controller.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another relay start or stop is in progress") from error
        yield
    finally:
        os.close(fd)


def check_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"Loopback UDP port {port} is unavailable; refusing a duplicate") from error


def owns_listener(pid, port, timeout=1):
    result = subprocess.run(
        ["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid),
         f"-iUDP@127.0.0.1:{port}", "-Fpn"],
        capture_output=True, text=True, timeout=timeout,
    )
    lines = result.stdout.splitlines()
    return result.returncode == 0 and f"p{pid}" in lines and f"n127.0.0.1:{port}" in lines


def bootout(target):
    result = run_launchctl("bootout", target)
    if result.returncode:
        raise RuntimeError(f"launchctl bootout failed (exit {result.returncode})")


def inspect_listener(port):
    """Observe socket owners without binding or sending any packets."""
    endpoint = f"127.0.0.1:{port}"
    try:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-nP", f"-iUDP:{port}", "-Fpn"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode not in (0, 1) or result.stderr.strip():
            return {"endpoint": endpoint, "checked": False, "error": "lsof could not reliably inspect sockets"}
        bindings, pid = [], None
        for line in result.stdout.splitlines():
            if line.startswith("p") and line[1:].isdigit():
                pid = int(line[1:])
            elif line.startswith("n") and pid and line[1:] in (endpoint, f"*:{port}"):
                bindings.append({"pid": pid, "address": line[1:]})
        return {"endpoint": endpoint, "checked": True, "bindings": bindings}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"endpoint": endpoint, "checked": False, "error": type(error).__name__}


def read_tail(filename):
    if not isinstance(filename, str) or not filename:
        return ""
    path = Path(filename)
    if path.resolve().parent != RUNTIME.resolve():
        raise ValueError("Log path is outside the relay runtime directory")
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(0, handle.tell() - 65536))
        return handle.read().decode("utf-8", errors="replace")


def run_evidence(job, metadata_path):
    evidence = {}
    try:
        metadata = json.loads(metadata_path.read_text())
        if not isinstance(metadata, dict):
            raise ValueError("Metadata is not an object")
    except (OSError, ValueError) as error:
        metadata = {}
        evidence["metadata_note"] = type(error).__name__
    log_path = job.get("stdout_path") if job.get("loaded") else metadata.get("log")
    error_path = job.get("stderr_path") if job.get("loaded") else metadata.get("error_log")
    # Launchd's actual log path takes precedence over a stale metadata PID.
    if job.get("loaded") and job.get("stdout_path") != metadata.get("log"):
        evidence["metadata_note"] = "Saved metadata does not match the loaded job's log"
    else:
        evidence["metadata"] = {key: metadata[key] for key in
                                ("pid", "start_utc", "seconds") if key in metadata}
        evidence["estimated_expiry_utc"] = metadata.get("expiry_utc")
    saved_run = evidence.get("metadata", {})
    if "seconds" in saved_run and saved_run["seconds"] is None:
        evidence["limit_mode"] = "until_stopped"
        evidence["estimated_expiry_utc"] = None
        evidence["expiry_note"] = "No scheduled expiry. Stop explicitly; process/network failures can still interrupt the relay. No automatic restart."
    else:
        seconds = saved_run.get("seconds")
        evidence["limit_mode"] = "bounded" if isinstance(seconds, int) and 1 <= seconds <= 28800 else "unknown"
        evidence["expiry_note"] = "For bounded runs, expiry is a no-sleep estimate: monotonic time excludes system sleep."
    for key, filename in (("log", log_path), ("error_log", error_path)):
        if not isinstance(filename, str):
            continue
        evidence[key] = filename
        try:
            content = read_tail(filename)
        except (OSError, ValueError) as error:
            evidence[key + "_note"] = type(error).__name__
            continue
        if key == "error_log":
            evidence["stderr_nonempty"] = bool(content.strip())
            continue
        for line in content.splitlines():
            match = re.match(r"^(\S+) (STOPPED|SOCKET_ERROR|ROUTE_ERROR|COUNTERS|FIRST_REPLY_DATAGRAM) (.*)$", line)
            if match:
                fields = dict(re.findall(r"([a-z_]+)=([^\s]+)", match.group(3)))
                event = {"utc": match.group(1), **fields}
                if match.group(2) == "STOPPED":
                    evidence["last_stop"] = event
                elif match.group(2) == "SOCKET_ERROR":
                    evidence["socket_error"] = event
                elif match.group(2) == "ROUTE_ERROR":
                    evidence["route_error"] = event
                elif match.group(2) == "FIRST_REPLY_DATAGRAM":
                    evidence["first_reply"] = event
                else:
                    evidence["last_counters"] = event
    return evidence


def local_diagnosis(environment, job, listener, evidence):
    bindings = listener.get("bindings", [])
    running = bool(job.get("pid")) or job.get("state") == "running"
    owns = any(b["pid"] == job.get("pid") and b["address"] == listener["endpoint"] for b in bindings)
    if running:
        if not listener["checked"]:
            return "unknown", "The relay process is running, but its listener could not be checked.", "Retry status; do not start a duplicate."
        if owns:
            limit = ("This run has no scheduled expiry; use the stop launcher when finished."
                     if evidence.get("limit_mode") == "until_stopped" else
                     "This is a bounded or unconfirmed run; check run_evidence for its runtime limit.")
            return "local_ready", f"{environment} relay is listening locally; office forwarding and VPN traffic are not verified by this status.", "Keep the office relay and Tailscale running, then connect the work VPN. " + limit
        return "listener_missing", "The relay process is running without its expected loopback listener.", "Inspect the relay logs; disconnect the work VPN before a deliberate stop/start."
    if bindings:
        return "unmanaged_listener", "The loopback port has an owner outside this running launchd job.", "Inspect the reported owner; do not start a duplicate or kill an unverified PID."
    stopped = evidence.get("last_stop", {})
    reason, exit_code = stopped.get("reason"), job.get("last_exit_code")
    if reason == "wrong_source_route":
        cause, summary = "wrong_source_route", "The office socket did not use the configured Mac Tailscale IPv4; inspect routes and Tailscale."
    elif reason == "socket_error":
        cause, summary = "socket_error", "The relay stopped on a socket error; its stage/errno are in run_evidence."
    elif exit_code not in (None, 0):
        cause, summary = "failed", f"The relay exited unsuccessfully (launchd exit {exit_code}); inspect its logs."
    elif job.get("last_terminating_signal"):
        cause, summary = "terminated", "Launchd reports that the relay was terminated by a signal."
    elif reason == "signal":
        cause, summary = "stopped_by_signal", "The relay stopped after receiving a stop signal."
    elif reason == "time_limit" and not evidence.get("stderr_nonempty"):
        cause, summary = "time_limit", "The relay reached its normal runtime limit and stopped; this is not a VPN authentication error."
    elif not job.get("loaded") and not evidence.get("log"):
        cause, summary = "not_started", "No relay job or saved run was found."
    else:
        cause, summary = "stopped_unknown", "The relay is not running; the available evidence does not establish why it stopped."
    if not listener["checked"]:
        return cause, summary, "Listener inspection failed. Retry status before starting another relay."
    return cause, summary, f"Disconnect the work VPN, confirm the office {environment} relay is running, then use start-{environment.lower()}-relay.command and reconnect."


def tailscale_status(office_ip):
    try:
        result = subprocess.run([TAILSCALE, "status", "--json"], capture_output=True, text=True, timeout=5)
        if result.returncode:
            return {"checked": False, "error": f"Tailscale status exited {result.returncode}"}
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError("Tailscale status is not an object")
        self_info = data.get("Self") if isinstance(data.get("Self"), dict) else {}
        peers = data.get("Peer") if isinstance(data.get("Peer"), dict) else {}
        peer = next((p for p in peers.values() if isinstance(p, dict) and
                     isinstance(p.get("TailscaleIPs"), list) and
                     office_ip in p["TailscaleIPs"]), None)
        return {"checked": True, "backend_state": data.get("BackendState"),
                "self_online": self_info.get("Online"), "office_ip": office_ip,
                "office_known": peer is not None,
                "office_online": peer.get("Online") if peer else None,
                "office_last_seen": peer.get("LastSeen") if peer else None,
                "limitation": "Tailscale's reported state only; no UDP reachability, office listener, or VPN traffic test was performed."}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {"checked": False, "error": type(error).__name__}


def show_status(environment, target, metadata_path, config_path, diagnose=False, human=False):
    job = inspect_job(target)
    runtime_config = RUNTIME / f"{environment.lower()}-config.json"
    try:
        settings = select_profile(load_config(runtime_config if runtime_config.exists() else config_path), environment)
    except ValueError as error:
        output = {"environment": environment, "service": target, **job,
                  "local_status": "config_unavailable", "config_note": str(error),
                  "run_evidence": run_evidence(job, metadata_path),
                  "next_action": "Edit the example config. Stop still works without a readable config."}
        if human:
            print(f"{environment} relay: configuration unavailable. {error}\n{output['next_action']}")
        else:
            print(json.dumps(output, indent=2))
        return
    listener = inspect_listener(settings.mac_port)
    evidence = run_evidence(job, metadata_path)
    cause, summary, action = local_diagnosis(environment, job, listener, evidence)
    output = {"summary": summary, "local_status": cause, "next_action": action,
              "environment": environment, "service": target,
              "runtime_directory": str(RUNTIME), **job,
              "listener": listener, "run_evidence": evidence}
    if diagnose:
        output["tailscale"] = tailscale_status(settings.office_tailscale_ip)
        ts = output["tailscale"]
        if ts.get("checked") and (ts.get("backend_state") != "Running" or
                                  not ts.get("office_known") or ts.get("office_online") is False):
            output["tailscale_next_action"] = "Check Tailscale on both devices and that the office PC is awake; this command does not repair or test the transport."
    if human:
        print(f"{environment} relay: {summary}\n\nNext: {action}")
        print(f"\nLocal state: {cause}; launchd: {job['state']}; PID: {job.get('pid') or 'none'}")
        print(f"Listener: {listener['endpoint']}; checked: {listener['checked']}; owners: {listener.get('bindings', [])}")
        print(f"Run mode: {evidence.get('limit_mode', 'unknown')}. {evidence.get('expiry_note', '')}")
        if evidence.get("last_stop"):
            stopped = evidence["last_stop"]
            print(f"Last stop: {stopped.get('reason', 'unknown')} at {stopped.get('utc', 'unknown')}")
        if job.get("last_exit_status"):
            print(f"Launchd last exit: {job['last_exit_status']}")
        if evidence.get("socket_error"):
            print(f"Socket failure: {evidence['socket_error']}")
        if diagnose:
            ts = output["tailscale"]
            print(f"\nTailscale: checked={ts.get('checked')}; state={ts.get('backend_state', 'unknown')}; office online={ts.get('office_online', 'unknown')}")
            print(ts.get("limitation", f"Tailscale check unavailable: {ts.get('error', 'unknown')}"))
            if output.get("tailscale_next_action"):
                print(output["tailscale_next_action"])
        for key in ("log", "error_log"):
            if evidence.get(key):
                print(f"{key}: {evidence[key]}")
    else:
        print(json.dumps(output, indent=2))


def start(environment, target, label, metadata_path, config_path, seconds):
    profiles = load_config(config_path)
    settings = select_profile(profiles, environment)
    filename, port = "mac-relay.py", settings.mac_port
    job = inspect_job(target)
    if job["pid"] or job["state"] == "running":
        raise RuntimeError(f"{environment} relay is already running; use status or stop")
    check_port_free(port)
    if job["loaded"]:
        bootout(target)

    script = RUNTIME / filename
    private_write(script, (SOURCE / filename).read_bytes())
    private_write(RUNTIME / "relay_config.py", (SOURCE / "relay_config.py").read_bytes())
    runtime_config = RUNTIME / f"{environment.lower()}-config.json"
    private_write(runtime_config, snapshot_config(profiles))
    stamp = utc_now().strftime("%Y%m%dT%H%M%S.%fZ")
    log_path = RUNTIME / f"{environment.lower()}-{stamp}.log"
    error_path = RUNTIME / f"{environment.lower()}-{stamp}.stderr.log"
    private_write(log_path, b"")
    private_write(error_path, b"")
    plist_path = RUNTIME / f"{environment.lower()}.plist"
    arguments = [PYTHON, str(script), "--config", str(runtime_config), "--environment", environment]
    if seconds is not None:
        arguments += ["--seconds", str(seconds)]
    definition = {
        "Label": label,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(RUNTIME),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(error_path),
    }
    private_write(plist_path, plistlib.dumps(definition))
    started = utc_now()
    try:
        result = run_launchctl("bootstrap", f"gui/{os.getuid()}", str(plist_path))
        if result.returncode:
            raise RuntimeError(f"launchctl bootstrap failed (exit {result.returncode})")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = inspect_job(target, timeout=max(0.1, min(1, deadline - time.monotonic())))
            if job["pid"] and owns_listener(
                job["pid"], port, timeout=max(0.1, min(1, deadline - time.monotonic()))
            ):
                break
            time.sleep(0.15)
        else:
            raise RuntimeError("Relay did not acquire its loopback socket within five seconds")
        metadata = {
            "pid": job["pid"], "start_utc": started.isoformat(),
            "expiry_utc": (started + dt.timedelta(seconds=seconds)).isoformat() if seconds is not None else None,
            "seconds": seconds, "log": str(log_path), "error_log": str(error_path),
        }
        private_write(metadata_path, (json.dumps(metadata, indent=2) + "\n").encode())
    except Exception:
        try:
            partial = inspect_job(target)
            if partial.get("stdout_path") == str(log_path):
                bootout(target)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            print("Warning: startup cleanup was not confirmed; inspect status before retrying", file=sys.stderr)
        raise
    show_status(environment, target, metadata_path, config_path)


def stop(environment, target, metadata_path, config_path):
    job = inspect_job(target)
    if job["loaded"]:
        bootout(target)
    if job.get("pid"):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(job["pid"], 0)  # Existence check only; no signal is sent.
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Job unloaded, but process exit was not confirmed within five seconds")
    # The fixed service label can be stopped even if its user config was removed.
    show_status(environment, target, metadata_path, config_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "diagnose", "stop"))
    parser.add_argument("environment", choices=("DEV", "LIVE"))
    parser.add_argument("--config", type=Path, default=SOURCE / "relay-config.json")
    parser.add_argument("--seconds", type=int, help="Optional bounded test duration, 1-28800 seconds; default runs until stopped")
    parser.add_argument("--human", action="store_true", help="Readable status/diagnose output instead of JSON")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Install Python 3.10 or newer")
    if args.human and args.action not in ("status", "diagnose"):
        parser.error("--human is only valid with status or diagnose")
    if args.seconds is not None and (args.action != "start" or not 1 <= args.seconds <= 28800):
        parser.error("--seconds is only valid with start and must be between 1 and 28800")
    if sys.platform != "darwin":
        parser.error("The launchd controller runs on macOS only")
    if os.getuid() == 0:
        parser.error("Run this controller as the logged-in user, without sudo")
    label = f"local.vpn-relay.{args.environment.lower()}"
    target = f"gui/{os.getuid()}/{label}"
    metadata_path = RUNTIME / f"{args.environment.lower()}.json"
    try:
        if args.action in ("status", "diagnose"):
            show_status(args.environment, target, metadata_path, args.config, diagnose=args.action == "diagnose", human=args.human)
        else:
            with mutation_lock():
                if args.action == "start":
                    start(args.environment, target, label, metadata_path, args.config, args.seconds)
                else:
                    stop(args.environment, target, metadata_path, args.config)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Relay {args.action} failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
