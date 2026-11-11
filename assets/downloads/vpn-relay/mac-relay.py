#!/usr/bin/env python3
"""Forward localhost OpenVPN UDP through one explicitly configured office peer."""

import argparse
import datetime
from pathlib import Path
import select
import signal
import socket
import sys
import threading
import time

from relay_config import load_config, select_profile


def emit(event, **fields):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    print(timestamp, event, " ".join(f"{key}={value}" for key, value in fields.items()), flush=True)


def allowed_client(sender):
    return sender[0] == "127.0.0.1" and 0 < sender[1] <= 65535


def run_relay(settings, seconds=None, stop=None, report=emit):
    """The CLI supplies validated settings; tests inject isolated loopback fixtures."""
    if seconds is not None and not 0 < seconds <= 28800:
        raise ValueError("seconds must be positive and at most 28800")
    stop = stop if stop is not None else threading.Event()
    started = time.monotonic()
    deadline = started + seconds if seconds is not None else None
    next_report = started + 30
    latest_client = None
    counts = dict(up_packets=0, up_bytes=0, reply_packets=0, reply_bytes=0,
                  rejected_packets=0, replies_without_client=0)
    reason, stage, exit_code = "unexpected_exit", "socket_setup", 0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
                stage = "loopback_bind"
                listener.bind(("127.0.0.1", settings.mac_port))
                listener.setblocking(False)
                stage = "office_connect"
                upstream.connect((settings.office_tailscale_ip, settings.office_port))
                upstream.setblocking(False)
                source_ip, source_port = upstream.getsockname()
                if source_ip != settings.mac_tailscale_ip:
                    reason, exit_code = "wrong_source_route", 1
                    report("ROUTE_ERROR", expected_source=settings.mac_tailscale_ip,
                           actual_source=source_ip)
                    return exit_code
                report("START", listener=f"127.0.0.1:{settings.mac_port}",
                       upstream=f"{settings.office_tailscale_ip}:{settings.office_port}",
                       upstream_source=f"{source_ip}:{source_port}",
                       limit_s=seconds if seconds is not None else "unlimited")
                while not stop.is_set():
                    remaining = deadline - time.monotonic() if deadline is not None else None
                    if remaining is not None and remaining <= 0:
                        reason = "time_limit"
                        break
                    stage = "select"
                    ready, _, _ = select.select([listener, upstream], [], [],
                                                min(1.0, remaining) if remaining is not None else 1.0)
                    for current in ready:
                        if stop.is_set() or (deadline is not None and time.monotonic() >= deadline):
                            break
                        try:
                            if current is listener:
                                stage = "loopback_receive"
                                packet, sender = listener.recvfrom(65535)
                                if not allowed_client(sender):
                                    counts["rejected_packets"] += 1
                                    continue
                                latest_client = sender
                                stage = "office_send"
                                upstream.send(packet)
                                counts["up_packets"] += 1
                                counts["up_bytes"] += len(packet)
                                if counts["up_packets"] == 1:
                                    report("FIRST_UPSTREAM_DATAGRAM", bytes=len(packet))
                            else:
                                stage = "office_receive"
                                packet = upstream.recv(65535)
                                if latest_client is None:
                                    counts["replies_without_client"] += 1
                                    continue
                                stage = "loopback_send"
                                listener.sendto(packet, latest_client)
                                counts["reply_packets"] += 1
                                counts["reply_bytes"] += len(packet)
                                if counts["reply_packets"] == 1:
                                    report("FIRST_REPLY_DATAGRAM", bytes=len(packet))
                        except BlockingIOError:
                            continue
                    if time.monotonic() >= next_report:
                        report("COUNTERS", **counts)
                        next_report = time.monotonic() + 30
                if stop.is_set():
                    reason = "signal"
    except OSError as error:
        report("SOCKET_ERROR", stage=stage, errno=error.errno)
        reason, exit_code = "socket_error", 1
    finally:
        report("STOPPED", reason=reason, elapsed_s=f"{time.monotonic() - started:.1f}", **counts)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("relay-config.json"))
    parser.add_argument("--environment", choices=("DEV", "LIVE"), required=True)
    parser.add_argument("--seconds", type=int, help="Optional 1-28800 second test; default runs until stopped")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Install Python 3.10 or newer")
    if args.seconds is not None and not 1 <= args.seconds <= 28800:
        parser.error("--seconds must be between 1 and 28800")
    try:
        settings = select_profile(load_config(args.config), args.environment)
    except ValueError as error:
        parser.error(str(error))
    stop = threading.Event()
    def request_stop(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    return run_relay(settings, args.seconds, stop)


if __name__ == "__main__":
    raise SystemExit(main())
