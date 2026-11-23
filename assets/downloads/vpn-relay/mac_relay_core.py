#!/usr/bin/env python3
"""Shared, fail-closed Mac UDP forwarding over the expected Tailscale interface."""

import datetime
import errno
import ipaddress
import re
import select
import socket
import subprocess
import time

# Darwin SDK netinet/in.h: IP_BOUND_IF is an int socket option, value 25.
IP_BOUND_IF = 25
ROUTE_INTERVAL = 2.0
MAX_RETRY_INTERVAL = 10.0
RECOVERABLE_ERRORS = {
    errno.EADDRNOTAVAIL, errno.ENETDOWN, errno.ENETUNREACH,
    errno.EHOSTUNREACH, errno.EHOSTDOWN, errno.ECONNREFUSED, errno.ECONNRESET,
    errno.ETIMEDOUT, errno.ENXIO,
}


def emit(event, **fields):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    print(timestamp, event, " ".join(f"{key}={value}" for key, value in fields.items()), flush=True)


def inspect_tailscale_route(office_ip, expected_source, timeout=2):
    """Inspect route/interface state only; never send a probe or alter settings."""
    result = dict(ready=False, interface=None, interface_index=None,
                  source_ip=None, reason="route_unavailable")
    deadline = time.monotonic() + max(0.01, timeout)

    def command(arguments):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(arguments, timeout)
        return subprocess.run(arguments, capture_output=True, text=True,
                              timeout=remaining, check=False)

    try:
        ipaddress.IPv4Address(office_ip)
        route = command(["/sbin/route", "-n", "get", office_ip])
        if route.returncode:
            return result
        match = re.search(r"^\s*interface:\s*(\S+)\s*$", route.stdout, re.MULTILINE)
        if not match:
            result["reason"] = "route_interface_missing"
            return result
        interface = result["interface"] = match.group(1)
        if not re.fullmatch(r"utun\d+", interface):
            result["reason"] = "route_not_utun"
            return result
        interface_info = command(["/sbin/ifconfig", interface])
        if interface_info.returncode:
            result["reason"] = "interface_unavailable"
            return result
        addresses = re.findall(r"^\s*inet\s+(\d+(?:\.\d+){3})\b", interface_info.stdout, re.MULTILINE)
        result["source_ip"] = expected_source if expected_source in addresses else (addresses[0] if addresses else None)
        if expected_source not in addresses:
            result["reason"] = "expected_source_missing"
            return result
        result["interface_index"] = socket.if_nametoindex(interface)
        result.update(ready=True, reason="ready")
    except subprocess.TimeoutExpired:
        result["reason"] = "route_check_timeout"
    except (OSError, ValueError):
        result["reason"] = "route_check_failed"
    return result


class Upstream:
    """Own one source/interface-bound socket; retry after a fresh route check."""

    def __init__(self, office, expected_source, *, route_checker=inspect_tailscale_route,
                 socket_factory=socket.socket, clock=time.monotonic, event=emit):
        self.office, self.expected_source = office, expected_source
        self.route_checker, self.socket_factory = route_checker, socket_factory
        self.clock, self.event = clock, event
        self.socket, self.route_key = None, None
        self.next_check, self.retry_interval = 0.0, ROUTE_INTERVAL
        self.wait_reason, self.last_wait_report = None, float("-inf")

    def close(self):
        if self.socket is not None:
            self.socket.close()
        self.socket, self.route_key = None, None

    def waiting(self, reason, snapshot=None):
        self.close()
        now = self.clock()
        if reason != self.wait_reason or now - self.last_wait_report >= 30:
            self.event("WAITING_FOR_TAILSCALE", reason=reason,
                       expected_source=self.expected_source,
                       interface=(snapshot or {}).get("interface") or "none",
                       route_source=(snapshot or {}).get("source_ip") or "none",
                       retry_s=self.retry_interval)
            self.last_wait_report = now
        self.wait_reason = reason
        self.next_check = now + self.retry_interval
        self.retry_interval = min(MAX_RETRY_INTERVAL, self.retry_interval * 2)

    def recover(self, error, stage):
        if error.errno not in RECOVERABLE_ERRORS:
            raise error
        self.event("SOCKET_RECOVERING", stage=stage, errno=error.errno)
        self.waiting("socket_error")

    def refresh(self, timeout=2):
        if self.clock() < self.next_check:
            return
        snapshot = self.route_checker(self.office[0], self.expected_source, timeout=timeout)
        interface, index = snapshot.get("interface"), snapshot.get("interface_index")
        valid = (snapshot.get("ready") is True and snapshot.get("source_ip") == self.expected_source
                 and isinstance(interface, str) and re.fullmatch(r"utun\d+", interface)
                 and isinstance(index, int) and index > 0)
        if not valid:
            self.waiting(snapshot.get("reason", "invalid_route"), snapshot)
            return
        route_key = (interface, index, self.expected_source)
        if self.socket is not None and self.route_key == route_key:
            self.next_check = self.clock() + ROUTE_INTERVAL
            return
        self.close()
        candidate = None
        try:
            candidate = self.socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
            # Source binding alone cannot prevent fallback onto a physical route.
            # Mandatory interface binding protects the interval between checks too.
            candidate.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, index)
            candidate.bind((self.expected_source, 0))
            candidate.connect(self.office)
            candidate.setblocking(False)
            source_ip, source_port = candidate.getsockname()
            if source_ip != self.expected_source or candidate.getsockopt(socket.IPPROTO_IP, IP_BOUND_IF) != index:
                raise OSError(errno.EPERM, "Upstream source/interface binding could not be verified")
            self.socket, candidate = candidate, None
            self.route_key = route_key
            self.next_check, self.retry_interval = self.clock() + ROUTE_INTERVAL, ROUTE_INTERVAL
            self.wait_reason = None
            self.event("UPSTREAM_READY", interface=interface, interface_index=index,
                       upstream=f"{self.office[0]}:{self.office[1]}",
                       upstream_source=f"{source_ip}:{source_port}")
        except OSError as error:
            self.recover(error, "upstream_setup")
        finally:
            if candidate is not None:
                candidate.close()


def relay_loop(listener, listen, upstream, *, seconds=None, should_stop=lambda: False,
               clock=time.monotonic, selector=select.select, event=emit):
    """Keep loopback stable while recovering only the network-facing socket."""
    started = clock()
    deadline = started + seconds if seconds is not None else None
    next_report, latest_client = started + 30, None
    counters = dict(up_packets=0, up_bytes=0, reply_packets=0, reply_bytes=0,
                    rejected_packets=0, replies_without_client=0, waiting_drops=0)
    reason, exit_code, stage = "unexpected_exit", 0, "route_check"
    event("START", listener=f"{listen[0]}:{listen[1]}",
          upstream=f"{upstream.office[0]}:{upstream.office[1]}", expected_source=upstream.expected_source,
          limit_s=seconds if seconds is not None else "unlimited")
    try:
        while not should_stop():
            remaining = deadline - clock() if deadline is not None else None
            if remaining is not None and remaining <= 0:
                reason = "time_limit"
                break
            stage = "upstream_setup"
            upstream.refresh(timeout=min(2, remaining) if remaining is not None else 2)
            if should_stop():
                break
            remaining = deadline - clock() if deadline is not None else None
            if remaining is not None and remaining <= 0:
                reason = "time_limit"
                break
            sockets = [listener] + ([upstream.socket] if upstream.socket is not None else [])
            wait = min(1.0, max(0.01, upstream.next_check - clock()))
            if remaining is not None:
                wait = min(wait, remaining)
            stage = "select"
            ready, _, _ = selector(sockets, [], [], wait)
            for current in ready:
                if should_stop() or (deadline is not None and clock() >= deadline):
                    break
                try:
                    if current is listener:
                        stage = "loopback_receive"
                        packet, sender = listener.recvfrom(65535)
                        if sender[0] != listen[0] or sender[1] <= 0:
                            counters["rejected_packets"] += 1
                            continue
                        latest_client = sender
                        if upstream.socket is None:
                            counters["waiting_drops"] += 1
                            continue
                        stage = "upstream_send"
                        upstream.socket.send(packet)
                        counters["up_packets"] += 1
                        counters["up_bytes"] += len(packet)
                        if counters["up_packets"] == 1:
                            event("FIRST_UPSTREAM_DATAGRAM", bytes=len(packet))
                    elif current is upstream.socket:
                        stage = "upstream_receive"
                        packet = upstream.socket.recv(65535)
                        if latest_client is None:
                            counters["replies_without_client"] += 1
                            continue
                        stage = "loopback_send"
                        listener.sendto(packet, latest_client)
                        counters["reply_packets"] += 1
                        counters["reply_bytes"] += len(packet)
                        if counters["reply_packets"] == 1:
                            event("FIRST_REPLY_DATAGRAM", bytes=len(packet))
                except BlockingIOError:
                    continue
                except OSError as error:
                    if stage in ("upstream_send", "upstream_receive"):
                        upstream.recover(error, stage)
                        if stage == "upstream_send":
                            counters["waiting_drops"] += 1
                    else:
                        raise
            if clock() >= next_report:
                event("COUNTERS", **counters)
                next_report = clock() + 30
        if should_stop():
            reason = "signal"
    except OSError as error:
        event("SOCKET_ERROR", stage=stage, errno=error.errno)
        reason, exit_code = "socket_error", 1
    finally:
        upstream.close()
        event("STOPPED", reason=reason, elapsed_s=f"{clock() - started:.1f}", **counters)
    return exit_code
