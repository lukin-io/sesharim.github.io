"""Loopback-only tests: no Tailscale, VPN, launchd jobs or firewall changes."""

import importlib.util
import contextlib
import io
import json
import plistlib
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relay_config import RelaySettings, load_config, select_profile, snapshot_config
from mac_relay_core import Upstream


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


relay = module("relay_under_test", "mac-relay.py")
control = None if sys.platform == "win32" else module("controller_under_test", "mac-relay-control.py")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".tmp-config-", dir=ROOT / "tests")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.json"
        # Synthetic inputs for parsing only; these addresses receive no traffic.
        self.config = {"configured": True, "office_tailscale_ip": "100.100.100.10",
                       "mac_tailscale_ip": "100.100.100.11", "profiles": {
                           "DEV": {"gateway_ip": "1.1.1.1", "gateway_port": 1194,
                                   "office_port": 11194, "mac_port": 11195}}}

    def load(self):
        self.path.write_text(json.dumps(self.config))
        return load_config(self.path)

    def test_example_refuses_start_until_edited(self):
        with self.assertRaises(ValueError):
            load_config(ROOT / "relay-config.example.json")

    def test_dev_only_and_snapshot_roundtrip(self):
        profiles = self.load()
        self.assertEqual(set(profiles), {"DEV"})
        with self.assertRaisesRegex(ValueError, "not configured"):
            select_profile(profiles, "LIVE")
        self.path.write_bytes(snapshot_config(profiles))
        self.assertEqual(load_config(self.path), profiles)

    def test_gateway_and_peer_guards(self):
        for value in ("192.0.2.10", "10.0.0.1", "127.0.0.1", "0.0.0.0", "224.0.0.1"):
            with self.subTest(value=value):
                self.config["profiles"]["DEV"]["gateway_ip"] = value
                with self.assertRaises(ValueError): self.load()
        self.config["profiles"]["DEV"]["gateway_ip"] = "1.1.1.1"
        self.config["mac_tailscale_ip"] = self.config["office_tailscale_ip"]
        with self.assertRaises(ValueError): self.load()

    def test_ports_and_unapproved_environment(self):
        for port in (True, "11195", 0, 80, 65536):
            self.config["profiles"]["DEV"]["mac_port"] = port
            with self.assertRaises(ValueError): self.load()
        self.config["profiles"]["DEV"]["mac_port"] = 11195
        self.config["profiles"]["LIVE"] = dict(self.config["profiles"]["DEV"])
        with self.assertRaisesRegex(ValueError, "different"): self.load()
        self.config["profiles"]["OTHER"] = self.config["profiles"].pop("LIVE")
        with self.assertRaises(ValueError): self.load()


class LoopbackUpstream:
    """Integration fixture only: real connected UDP sockets without a system route."""
    def __init__(self, office, expected_source, event):
        self.office, self.expected_source = office, expected_source
        self.socket = None
        self.next_check = 0

    def refresh(self, timeout=2):
        if self.socket is None:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((self.expected_source, 0))
            self.socket.connect(self.office)
            self.socket.setblocking(False)
        self.next_check = time.monotonic() + 2

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def recover(self, error, stage):
        raise error


class ForwarderTests(unittest.TestCase):
    def setUp(self):
        self.office = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.office.bind(("127.0.0.1", 0))
        self.office.settimeout(1)
        self.addCleanup(self.office.close)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        # Direct internal fixture: production CLI validation forbids loopback office peers.
        self.settings = RelaySettings("DEV", "127.0.0.1", "127.0.0.1", "192.0.2.10",
                                      1194, self.office.getsockname()[1], port)
        self.events, self.result = [], []
        self.started, self.stop = threading.Event(), threading.Event()

    def report(self, event, **fields):
        self.events.append((event, fields))
        if event == "START": self.started.set()

    def begin(self, seconds=None):
        self.thread = threading.Thread(target=lambda: self.result.append(
            relay.run_relay(self.settings, seconds, self.stop, self.report, LoopbackUpstream)))
        self.thread.start()
        self.addCleanup(self.finish)
        self.assertTrue(self.started.wait(2), self.events)

    def finish(self):
        self.stop.set()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())

    def client(self, address="127.0.0.1"):
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            client.bind((address, 0))
        except OSError:
            client.close()
            raise
        client.settimeout(1)
        self.addCleanup(client.close)
        return client

    def test_payload_roundtrip_and_wrong_upstream_port_rejected(self):
        self.begin()
        client = self.client()
        payload = b"\x00\xffloopback fixture" * 64
        client.sendto(payload, ("127.0.0.1", self.settings.mac_port))
        packet, relay_peer = self.office.recvfrom(65535)
        self.assertEqual(packet, payload)
        rogue = self.client()
        rogue.sendto(b"unauthorized peer", relay_peer)
        client.settimeout(0.15)
        with self.assertRaises(socket.timeout): client.recvfrom(65535)
        self.office.sendto(packet[::-1], relay_peer)
        client.settimeout(1)
        self.assertEqual(client.recvfrom(65535)[0], payload[::-1])
        self.finish()
        self.assertEqual(self.result, [0])
        self.assertEqual(self.events[-1][1]["reason"], "signal")
        self.assertEqual(self.events[-1][1]["reply_packets"], 1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reopened:
            reopened.bind(("127.0.0.1", self.settings.mac_port))

    def test_loopback_source_restriction(self):
        self.begin()
        try: rogue = self.client("127.0.0.2")
        except OSError: self.skipTest("OS has no second loopback source; synthetic dispatcher guard has separate coverage")
        rogue.sendto(b"rejected fixture", ("127.0.0.1", self.settings.mac_port))
        self.office.settimeout(0.2)
        with self.assertRaises(socket.timeout): self.office.recvfrom(65535)
        self.finish()
        self.assertGreaterEqual(self.events[-1][1]["rejected_packets"], 1)

    def test_timer_is_bounded_and_expiry_is_explicit(self):
        began = time.monotonic()
        self.begin(seconds=0.2)
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertLess(time.monotonic() - began, 1.5)
        self.assertEqual(self.events[-1][1]["reason"], "time_limit")

    def test_bind_failure_reports_stage_and_errno(self):
        occupied = self.client()
        settings = RelaySettings("DEV", "127.0.0.1", "127.0.0.1", "192.0.2.10", 1194,
                                 self.office.getsockname()[1], occupied.getsockname()[1])
        self.assertEqual(relay.run_relay(settings, 1, report=self.report), 1)
        error = next(fields for event, fields in self.events if event == "SOCKET_ERROR")
        self.assertEqual(error["stage"], "loopback_bind")
        self.assertIsInstance(error["errno"], int)
        self.assertNotIn("packet", error)

    def test_wrong_route_waits_without_sending(self):
        checker = mock.Mock(return_value={"ready": False, "reason": "route_not_utun"})
        factory = mock.Mock()
        def upstream(office, source, event):
            return Upstream(office, source, event=event, route_checker=checker,
                            socket_factory=factory)
        self.assertEqual(relay.run_relay(self.settings, 0.1, report=self.report,
                                        upstream_factory=upstream), 0)
        factory.assert_not_called()
        self.assertEqual(self.events[-1][1]["reason"], "time_limit")
        self.assertEqual(self.events[-1][1]["up_packets"], 0)


@unittest.skipIf(control is None, "launchd controller is macOS-only")
class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".tmp-controller-", dir=ROOT / "tests")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.path = self.base / "config.json"
        self.path.write_bytes(snapshot_config({"DEV": RelaySettings(
            "DEV", "100.100.100.10", "100.100.100.11", "1.1.1.1", 1194, 11194, 11195)}))

    def test_job_parser_ignores_nested_fields(self):
        output = "\tstate = not running\n\truns = 1\n\tlast exit code = 0\n\tresource coalition = {\n\t\tstate = active\n\t\tpid = 999\n\t}\n"
        with mock.patch.object(control, "run_launchctl", return_value=mock.Mock(returncode=0, stdout=output)):
            result = control.inspect_job("gui/501/local.vpn-relay.dev")
        self.assertIsNone(result["pid"])
        self.assertEqual(result["state"], "not running")
        self.assertEqual(result["last_exit_code"], 0)

    def test_status_distinguishes_process_from_listener(self):
        status, summary, _ = control.local_diagnosis("DEV", {"pid": 42, "state": "running"},
            {"checked": True, "bindings": [], "endpoint": "127.0.0.1:11195"}, {})
        self.assertEqual(status, "listener_missing")
        self.assertIn("without", summary)

    def test_actual_diagnose_dispatch_uses_configured_settings(self):
        job = {"loaded": True, "state": "running", "pid": 42}
        listener = {"checked": True, "endpoint": "127.0.0.1:11195",
                    "bindings": [{"pid": 42, "address": "127.0.0.1:11195"}]}
        output = io.StringIO()
        with mock.patch.object(control, "RUNTIME", self.base / "runtime"), \
                mock.patch.object(control, "inspect_job", return_value=job), \
                mock.patch.object(control, "inspect_listener", return_value=listener) as inspect, \
                mock.patch.object(control, "run_evidence", return_value={"limit_mode": "until_stopped"}), \
                mock.patch.object(control, "tailscale_status", return_value={"checked": False}) as ts, \
                mock.patch.object(control, "inspect_upstream", return_value={"checked": True, "sockets": [{"source_ip": "100.100.100.11"}]}) as upstream, \
                mock.patch.object(control, "inspect_tailscale_route", return_value={"ready": True, "source_ip": "100.100.100.11"}) as route, \
                mock.patch.object(control.sys, "platform", "darwin"), \
                mock.patch.object(control.os, "getuid", return_value=501), \
                mock.patch.object(control.sys, "argv", ["controller", "diagnose", "DEV", "--config", str(self.path)]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(control.main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["local_status"], "local_ready")
        inspect.assert_called_once_with(11195)
        ts.assert_called_once_with("100.100.100.10")
        upstream.assert_called_once_with(42, "100.100.100.10", 11194)
        route.assert_called_once_with("100.100.100.10", "100.100.100.11")

    def test_readiness_requires_listener_source_and_route(self):
        job = {"pid": 42, "state": "running"}
        listener = {"checked": True, "endpoint": "127.0.0.1:11195",
                    "bindings": [{"pid": 42, "address": "127.0.0.1:11195"}]}
        for upstream, route, expected in (
            ({"checked": False}, None, "upstream_unknown"),
            ({"checked": True, "sockets": [{"source_ip": "192.0.2.20"}]},
             {"ready": True, "source_ip": "100.100.100.11"}, "stale_upstream"),
            ({"checked": True, "sockets": [{"source_ip": "100.100.100.11"}]},
             {"ready": False}, "waiting_for_tailscale"),
            ({"checked": True, "sockets": []},
             {"ready": True, "source_ip": "100.100.100.11"}, "recovering_upstream"),
            ({"checked": True, "sockets": [{"source_ip": "100.100.100.11"}]},
             {"ready": True, "source_ip": "100.100.100.11"}, "local_ready"),
        ):
            with self.subTest(expected=expected):
                result = control.local_diagnosis("DEV", job, listener, {}, upstream,
                                                 route, "100.100.100.11")
                self.assertEqual(result[0], expected)
                if expected == "local_ready":
                    self.assertIn("VPN traffic are not verified", result[1])

    def test_upstream_inspection_uses_exact_configured_destination(self):
        result = mock.Mock(returncode=0, stderr="", stdout=(
            "n127.0.0.1:11195\n"
            "n192.0.2.20:54321->100.100.100.10:11194\n"
            "n100.100.100.11:54322->100.100.100.10:11196\n"))
        with mock.patch.object(control.subprocess, "run", return_value=result):
            parsed = control.inspect_upstream(42, "100.100.100.10", 11194)
        self.assertEqual(parsed, {"checked": True, "sockets": [
            {"source_ip": "192.0.2.20", "source_port": "54321", "remote": "100.100.100.10:11194"}]})

    def test_repeated_start_checks_running_job_without_mutation(self):
        with mock.patch.object(control, "inspect_job", return_value={"pid": 42, "state": "running"}), \
             mock.patch.object(control, "show_status", return_value=2) as status, \
             mock.patch.object(control, "bootout") as bootout, \
             mock.patch.object(control, "private_write") as write:
            self.assertEqual(control.start("DEV", "target", "label", self.base / "metadata.json",
                                            self.path, None), 2)
        status.assert_called_once_with("DEV", "target", self.base / "metadata.json", self.path)
        bootout.assert_not_called()
        write.assert_not_called()

    def test_recovery_log_tail_remains_visible_without_start_line(self):
        log = ("2026-01-01T00:00:01Z SOCKET_RECOVERING stage=upstream_send errno=49\n"
               "2026-01-01T00:00:02Z WAITING_FOR_TAILSCALE reason=route_unavailable\n"
               "2026-01-01T00:00:03Z UPSTREAM_READY upstream_source=100.100.100.11:54321\n"
               "2026-01-01T00:00:04Z COUNTERS up_packets=20 reply_packets=15 waiting_drops=2\n")
        with mock.patch.object(control, "read_tail", return_value=log):
            evidence = control.run_evidence({"loaded": True, "stdout_path": "run.log"},
                                            self.base / "missing.json")
        self.assertEqual(evidence["last_network_event"]["event"], "UPSTREAM_READY")
        self.assertEqual(evidence["last_counters"]["waiting_drops"], "2")

    def test_stop_succeeds_without_readable_config(self):
        output = io.StringIO()
        with mock.patch.object(control, "RUNTIME", self.base / "runtime"), \
                mock.patch.object(control, "inspect_job", return_value={"loaded": False, "pid": None, "state": "not_loaded"}), \
                mock.patch.object(control, "run_evidence", return_value={}), \
                mock.patch.object(control, "bootout") as bootout, \
                contextlib.redirect_stdout(output):
            control.stop("DEV", "gui/501/local.vpn-relay.dev", self.base / "metadata.json", self.base / "missing.json")
        bootout.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["local_status"], "config_unavailable")

    def test_start_builds_manual_job_and_preserves_duration_choice(self):
        runtime = self.base / "runtime"
        runtime.mkdir(mode=0o700)
        target = "gui/501/local.vpn-relay.dev"
        for seconds in (None, 60):
            with self.subTest(seconds=seconds), \
                    mock.patch.object(control, "RUNTIME", runtime), \
                    mock.patch.object(control, "inspect_job", side_effect=[
                        {"loaded": False, "state": "not_loaded", "pid": None},
                        {"loaded": True, "state": "running", "pid": 42}]), \
                    mock.patch.object(control, "check_port_free"), \
                    mock.patch.object(control, "run_launchctl", return_value=mock.Mock(returncode=0)) as launch, \
                    mock.patch.object(control, "owns_listener", return_value=True), \
                    mock.patch.object(control, "show_status") as status, \
                    mock.patch.object(control.os, "getuid", return_value=501):
                control.start("DEV", target, "local.vpn-relay.dev", runtime / "dev.json", self.path, seconds)
                definition = plistlib.loads((runtime / "dev.plist").read_bytes())
                self.assertIs(definition["KeepAlive"], False)
                self.assertIs(definition["RunAtLoad"], True)
                self.assertEqual("--seconds" in definition["ProgramArguments"], seconds is not None)
                self.assertNotIn("StartInterval", definition)
                self.assertEqual(json.loads((runtime / "dev.json").read_text())["seconds"], seconds)
                launch.assert_called_once_with("bootstrap", "gui/501", str(runtime / "dev.plist"))
                status.assert_called_once_with("DEV", target, runtime / "dev.json", self.path)
                self.assertEqual(load_config(runtime / "dev-config.json"), load_config(self.path))
                self.assertEqual((runtime / "mac_relay_core.py").read_bytes(), (ROOT / "mac_relay_core.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
