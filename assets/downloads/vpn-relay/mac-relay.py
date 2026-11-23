#!/usr/bin/env python3
"""Forward localhost OpenVPN UDP through one explicitly configured office peer."""

import argparse
from pathlib import Path
import signal
import socket
import sys
import threading

from relay_config import load_config, select_profile
from mac_relay_core import Upstream, emit, relay_loop



def run_relay(settings, seconds=None, stop=None, report=emit, upstream_factory=Upstream):
    """The CLI validates settings; tests inject an isolated loopback upstream."""
    if seconds is not None and not 0 < seconds <= 28800:
        raise ValueError("seconds must be positive and at most 28800")
    stop = stop if stop is not None else threading.Event()
    listen = ("127.0.0.1", settings.mac_port)
    upstream = upstream_factory((settings.office_tailscale_ip, settings.office_port),
                                settings.mac_tailscale_ip, event=report)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            # Exclusive loopback binding; never enable address/port reuse.
            listener.bind(listen)
            listener.setblocking(False)
            return relay_loop(listener, listen, upstream, seconds=seconds,
                              should_stop=stop.is_set, event=report)
    except OSError as error:
        report("SOCKET_ERROR", stage="loopback_bind", errno=error.errno)
        report("STOPPED", reason="socket_error", elapsed_s="0.0")
        return 1
    finally:
        upstream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("relay-config.json"))
    parser.add_argument("--environment", choices=("DEV", "LIVE"), required=True)
    parser.add_argument("--seconds", type=int, help="Optional 1-28800 second test; default runs until stopped")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Install Python 3.10 or newer")
    if sys.platform != "darwin":
        parser.error("The relay uses macOS interface binding and runs on macOS only")
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
