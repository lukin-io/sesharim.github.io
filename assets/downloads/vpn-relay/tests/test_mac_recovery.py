"""Offline route/socket recovery tests. No real route, interface or VPN changes."""

import errno
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mac_relay_core as core

SOURCE = '100.100.100.11'
OFFICE = '100.100.100.10'


def route(interface='utun4', index=7, source=SOURCE):
    return dict(ready=True, interface=interface, interface_index=index,
                source_ip=source, reason='ready')


class Clock:
    now = 0.0
    def __call__(self):
        return self.now


class FakeSocket:
    def __init__(self, *args):
        self.closed = False
        self.options, self.sent = {}, []
        self.bound = None
        self.send_error = None
        self.recv_calls = 0
    def setsockopt(self, level, option, value):
        self.options[level, option] = value
    def getsockopt(self, level, option):
        return self.options[level, option]
    def bind(self, endpoint):
        self.bound = endpoint
    def connect(self, endpoint):
        self.peer = endpoint
    def setblocking(self, value):
        self.blocking = value
    def getsockname(self):
        return self.bound[0], 12345
    def send(self, packet):
        if self.send_error:
            raise self.send_error
        self.sent.append(packet)
        return len(packet)
    def recv(self, count):
        self.recv_calls += 1
        return b'reply'
    def close(self):
        self.closed = True


class RouteTests(unittest.TestCase):
    def inspect(self, interface, addresses):
        responses = [mock.Mock(returncode=0, stdout=f' interface: {interface}\n'),
                     mock.Mock(returncode=0, stdout=addresses)]
        with mock.patch.object(core.subprocess, 'run', side_effect=responses) as run, \
             mock.patch.object(core.socket, 'if_nametoindex', return_value=7):
            result = core.inspect_tailscale_route(OFFICE, SOURCE)
        return result, run

    def test_expected_tailscale_interface_is_ready(self):
        result, commands = self.inspect('utun4', f' inet {SOURCE} netmask 0xffffffff\n')
        self.assertEqual(result, route())
        self.assertEqual(commands.call_count, 2)

    def test_physical_or_other_vpn_route_is_rejected(self):
        result, commands = self.inspect('en0', '')
        self.assertFalse(result['ready'])
        self.assertEqual(result['reason'], 'route_not_utun')
        self.assertEqual(commands.call_count, 1)
        result, _ = self.inspect('utun4', ' inet 192.0.2.20 netmask 0xffffffff\n')
        self.assertEqual(result['reason'], 'expected_source_missing')
        self.assertFalse(result['ready'])

    def test_timeout_returns_waiting_state(self):
        with mock.patch.object(core.subprocess, 'run', side_effect=subprocess.TimeoutExpired('route', 2)):
            result = core.inspect_tailscale_route(OFFICE, SOURCE)
        self.assertEqual(result['reason'], 'route_check_timeout')
        self.assertFalse(result['ready'])


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.events, self.sockets = Clock(), [], []
        self.checker = mock.Mock(return_value=route())
        self.factory = mock.Mock(side_effect=self.make_socket)
        self.upstream = core.Upstream((OFFICE, 11194), SOURCE, route_checker=self.checker,
                                      socket_factory=self.factory, clock=self.clock,
                                      event=lambda event, **fields: self.events.append((event, fields)))
        self.addCleanup(self.upstream.close)

    def make_socket(self, *args):
        value = FakeSocket()
        self.sockets.append(value)
        return value

    def test_source_and_interface_are_both_bound_and_checked(self):
        self.upstream.refresh()
        value = self.sockets[0]
        self.assertEqual(value.bound, (SOURCE, 0))
        self.assertEqual(value.options[socket.IPPROTO_IP, core.IP_BOUND_IF], 7)
        self.assertEqual(value.peer, (OFFICE, 11194))
        self.assertFalse(value.blocking)
        self.assertEqual(self.events[-1][0], 'UPSTREAM_READY')

    def test_waiting_never_creates_physical_socket_then_recovers(self):
        self.checker.return_value = {'ready': False, 'reason': 'route_not_utun', 'interface': 'en0'}
        self.upstream.refresh()
        self.factory.assert_not_called()
        self.assertIsNone(self.upstream.socket)
        self.checker.return_value = route()
        self.clock.now = 2
        self.upstream.refresh()
        self.assertIsNotNone(self.upstream.socket)

    def test_interface_change_replaces_socket_even_with_same_ip(self):
        self.upstream.refresh()
        first = self.upstream.socket
        self.clock.now = 2
        self.checker.return_value = route('utun9', 12)
        self.upstream.refresh()
        self.assertTrue(first.closed)
        self.assertIsNot(first, self.upstream.socket)
        self.assertEqual(self.upstream.socket.options[socket.IPPROTO_IP, core.IP_BOUND_IF], 12)

    def test_route_loss_closes_socket_and_waits(self):
        self.upstream.refresh()
        first = self.upstream.socket
        self.clock.now = 2
        self.checker.return_value = {'ready': False, 'reason': 'expected_source_missing'}
        self.upstream.refresh()
        self.assertTrue(first.closed)
        self.assertIsNone(self.upstream.socket)

    def test_recoverable_error_recreates_only_after_backoff(self):
        self.upstream.refresh()
        first = self.upstream.socket
        self.upstream.recover(OSError(errno.EADDRNOTAVAIL, 'fixture'), 'upstream_send')
        self.assertTrue(first.closed)
        self.upstream.refresh()
        self.assertEqual(self.factory.call_count, 1)
        self.clock.now = 2
        self.upstream.refresh()
        self.assertEqual(self.factory.call_count, 2)

    def test_wait_backoff_is_capped(self):
        self.checker.return_value = {'ready': False, 'reason': 'route_not_utun'}
        intervals = []
        for _ in range(6):
            self.upstream.refresh()
            intervals.append(self.upstream.next_check - self.clock.now)
            self.clock.now = self.upstream.next_check
        self.assertEqual(intervals, [2, 4, 8, 10, 10, 10])
        self.factory.assert_not_called()

    def test_setup_failure_closes_candidate_and_retries(self):
        value = FakeSocket()
        value.connect = mock.Mock(side_effect=OSError(errno.ENETUNREACH, 'fixture'))
        self.factory.side_effect = [value, FakeSocket()]
        self.upstream.refresh()
        self.assertTrue(value.closed)
        self.assertIsNone(self.upstream.socket)
        self.clock.now = 2
        self.upstream.refresh()
        self.assertIsNotNone(self.upstream.socket)

    def test_wrong_source_or_unverifiable_interface_fails_closed(self):
        for source, index in [('192.0.2.20', 7), (SOURCE, 8)]:
            with self.subTest(source=source, index=index):
                value = FakeSocket()
                value.getsockname = lambda: (source, 12345)
                value.getsockopt = lambda *args: index
                self.factory.side_effect = None
                self.factory.return_value = value
                with self.assertRaises(OSError) as error:
                    self.upstream.refresh()
                self.assertEqual(error.exception.errno, errno.EPERM)
                self.assertTrue(value.closed)
                self.assertIsNone(self.upstream.socket)

    def test_unrelated_error_remains_fatal(self):
        with self.assertRaises(OSError):
            self.upstream.recover(OSError(errno.EBADF, 'fixture'), 'upstream_send')

    def test_loop_keeps_listener_skips_closed_selected_socket_and_resumes(self):
        self.upstream.refresh()
        first = self.upstream.socket
        first.send_error = OSError(errno.EADDRNOTAVAIL, 'fixture')
        listener = mock.Mock()
        listener.recvfrom.return_value = (b'packet', ('127.0.0.1', 54321))
        calls = []
        def selector(sockets, _write, _errors, timeout):
            calls.append(sockets)
            self.clock.now += 2
            if len(calls) == 1:
                return [listener, first], [], []
            if len(calls) in (2, 3):
                return [listener], [], []
            return [self.upstream.socket], [], []
        result = core.relay_loop(listener, ('127.0.0.1', 11195), self.upstream,
            should_stop=lambda: len(calls) >= 5, clock=self.clock, selector=selector,
            event=lambda event, **fields: self.events.append((event, fields)))
        self.assertEqual(result, 0)
        self.assertEqual(first.recv_calls, 0)
        listener.close.assert_not_called()
        self.assertEqual(len(self.sockets), 2)
        self.assertEqual(self.sockets[1].sent, [b'packet'])
        listener.sendto.assert_called_once_with(b'reply', ('127.0.0.1', 54321))
        self.assertEqual(self.events[-1][1]['waiting_drops'], 2)
        self.assertEqual(self.events[-1][1]['reply_packets'], 1)

    def test_loop_rejects_wrong_client_source_and_zero_port(self):
        listener = mock.Mock()
        listener.recvfrom.side_effect = [(b'bad', ('127.0.0.2', 12345)),
                                         (b'bad', ('127.0.0.1', 0))]
        calls = []
        def selector(*args):
            calls.append(1)
            return [listener], [], []
        result = core.relay_loop(listener, ('127.0.0.1', 11195), self.upstream,
            should_stop=lambda: len(calls) > 2, clock=self.clock, selector=selector,
            event=lambda event, **fields: self.events.append((event, fields)))
        self.assertEqual(result, 0)
        self.assertEqual(self.events[-1][1]['rejected_packets'], 2)
        self.assertEqual(self.sockets[0].sent, [])


if __name__ == '__main__':
    unittest.main()
