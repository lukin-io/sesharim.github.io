MANUAL OPENVPN-OVER-TAILSCALE RELAY KIT

Updated November 23, 2026: Mac source/interface recovery and Windows gateway
send-error recovery. Explicitly restart both ends when upgrading; downloading
new files does not replace code in a running process or the Mac runtime copy.

This kit carries one existing OpenVPN UDP connection through an authorized
Windows office computer. It is not a VPN server, exit node, public proxy or
replacement for the original OpenVPN encryption/authentication.

Path:
OpenVPN -> Mac localhost UDP -> office Tailscale IPv4 UDP -> fixed VPN gateway.

The original private deployment was tested on macOS and Windows PowerShell 5.1.
This public, configurable adaptation has separate tests. Do not interpret those
tests as proof that your network, account, firewall or VPN server will work.
The test commands below do not connect to a real VPN or modify a firewall.

FILES AND REQUIREMENTS

- macOS: Python 3.10 or newer, Tailscale, and an existing OpenVPN UDP client/profile.
- Windows: Windows PowerShell 5.1, Tailscale connected on the intended office PC.
- Both devices must belong to a tailnet where the Mac can reach the office's
  configured UDP relay port. Obtain permission to use the office connection.
- No router port forwarding, public relay listener or Tailscale exit node is needed.
- DEV is required; LIVE is optional. The names are labels, not hardcoded work sites.
- relay-config.example.json is deliberately unusable until edited.
- mac-relay.py uses mac_relay_core.py for forwarding and Tailscale path recovery;
  relay_config.py validates its config. Keep all three files together.
- mac-relay-control.py manages manual launchd jobs and reports status/diagnostics.
- office-relay.ps1 and relay-config.ps1 implement the restricted Windows relay.
- office-firewall.ps1 provides explicit Plan/Add/Remove for an exact inbound rule.
- All launchers resolve files relative to their own folder; keep the kit together.

1. CONFIGURE BOTH MACHINES

Copy relay-config.example.json to relay-config.json. Use the SAME edited JSON on
both machines. Never put passwords, private keys, certificates or session tokens
in it. All OpenVPN credentials stay in your original VPN client/profile.

Replace:
- office_tailscale_ip: the office PC's current Tailscale IPv4.
- mac_tailscale_ip: the Mac's current Tailscale IPv4; it must be different.
- each gateway_ip: the actual public IPv4 of the authorized OpenVPN UDP gateway.
  The supplied 192.0.2.x addresses are documentation examples and are rejected.
- configured: set true only after replacing those values.

Keep the default ports unless you have a specific conflict:
            office UDP listener     Mac localhost UDP listener
  DEV             11194                        11195
  LIVE            11196                        11197

gateway_port defaults to 1194. It must match the actual server's UDP listener.
For one VPN, remove the entire LIVE object from profiles and use DEV launchers.
The check helper skips unconfigured LIVE; attempting to start LIVE fails clearly.

Read the Tailscale address on Windows with:
  & "$env:ProgramFiles\Tailscale\tailscale.exe" ip -4
On macOS use Tailscale's interface or:
  /Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4

Gateway IPs and Tailscale device identities can change. Re-resolve the original
VPN hostname when appropriate, verify the intended device/gateway, and update
both config copies deliberately. Do not widen listeners or firewall rules to
work around an address mismatch. Existing Mac jobs keep their validated runtime
snapshot; disconnect the VPN, stop and explicitly start after changing config.

2. REVIEW AND CHECK WINDOWS

Review the downloaded scripts before running them. In the extracted kit folder,
remove the downloaded-file marker only from the reviewed PowerShell scripts:
  Get-ChildItem -LiteralPath . -Filter '*.ps1' -File -Recurse | Unblock-File

The CMD launchers use -ExecutionPolicy RemoteSigned for that PowerShell process
only. They do not set a permanent execution policy, use Bypass or override managed
MachinePolicy/UserPolicy. If organizational policy prevents execution, follow
your administrator's policy instead of changing it globally.

Double-click check-office-relays.cmd. This reads configuration, Tailscale service/
backend state, the expected local IPv4, selected settings and port occupancy.
It starts no relay, changes no settings and writes no diagnostic file. Read the
findings, not only the exit code: Plan can complete while showing a not-ready
interface or an occupied port. Start fails closed in either case.

3. REVIEW AND ADD THE NARROW WINDOWS FIREWALL RULE

Connect Tailscale first. In Windows PowerShell, from the kit folder:
  powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Plan -Environment DEV

After reviewing the displayed scope, run Add from an elevated Windows PowerShell:
  powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Add -Environment DEV

Repeat for LIVE only if configured and needed. The rule permits inbound UDP only
to the configured office Tailscale IPv4/port, from the configured Mac Tailscale
IPv4, on the actual Tailscale interface, for the Windows PowerShell executable.
The Mac uses an ephemeral source port, so RemotePort is Any. All other listed
constraints remain exact. The helper never disables the firewall.

An existing identical rule is a no-op. A differently scoped rule with the reserved
name is refused, not silently replaced or widened. The rules persist after relay
exit. Other broader firewall rules or tailnet grants are not narrowed by adding
this rule. Review the effective tailnet/access policy; grants are additive.

4. START THE OFFICE RELAY, THEN THE MAC RELAY

Windows: double-click start-office-dev.cmd (or start-office-live.cmd).
Leave that console open. It runs until stopped, unless an unhandled error interrupts it.
It pauses on return so the reason remains visible. Ctrl+C stops the relay.

Start waits briefly for an already-starting Tailscale interface. This is a 30-second
polling budget; a stalled native Windows cmdlet can take longer. It does not log in,
start a service, select a tailnet or repair Tailscale for you. It requires the exact
office IP once in Preferred state and Tailscale service/backend Running. It refuses
a selected exit node and an occupied listener. After readiness, Start sets office
Tailscale accept-dns=false and accept-routes=false; it prints their prior values.
Those two preferences remain false after cleanup. Plan never changes them.

Mac: double-click start-dev-relay.command (or start-live-relay.command).
If executable permissions were lost during extraction, from the kit folder:
  chmod +x ./*.command
Alternatively:
  python3 mac-relay-control.py start DEV

Mac jobs are manually bootstrapped into the logged-in user's launchd domain.
RunAtLoad=true, KeepAlive=false. No files are placed in ~/Library/LaunchAgents.
Closing Terminal or the app that launched the command does not own the relay's
lifetime. Recoverable upstream/network failures now recreate the socket while
the relay process stays alive. Logout/reboot, process termination and unrelated
fatal errors still stop it; there is no automatic startup or arbitrary crash
restart. Do not run the controller with sudo.

The runtime directory is ~/Library/Application Support/VPNRelay, mode 0700. It
contains private copies of the generic relay/core/config modules, validated config
snapshots, job definitions and mode 0600 logs. The actual Python executable used
to run the controller is recorded in ProgramArguments; no Homebrew path is assumed.

5. CONNECT THE EXISTING OPENVPN PROFILE

Make a local copy of the correct existing UDP .ovpn profile. Change its remote
endpoint to localhost and the selected Mac port:
  remote 127.0.0.1 11195
For LIVE use 11197. Preserve CA, certificates, keys, tls-crypt/tls-auth, routing,
remote-cert-tls and any existing explicit server-identity checks. Do not disable
certificate validation or change ciphers to make the relay work. A profile that
uses TCP needs a server-supported UDP profile; editing proto alone is insufficient.

Do not add auth-nocache as a troubleshooting measure: in supported OpenVPN Connect
versions it can prevent credential reuse at renewal/reconnect. If your original
profile intentionally includes it, follow your VPN administrator's credential
policy. This kit neither saves a VPN password nor changes a VPN profile.

Import the separate copy in OpenVPN Connect and authenticate there. A connected
indicator alone is not a data-path test. Check the office Tailscale route before
and after connecting; it must remain usable outside the work tunnel:
  route -n get YOUR_OFFICE_TAILSCALE_IPV4

Verify the routes for your work DNS/test destination, explicit UDP and TCP DNS,
and verified HTTPS. Use your own work DNS IP and known internal hostname;
neither is shipped with this kit:
  dig @YOUR_WORK_DNS_IPV4 YOUR_KNOWN_INTERNAL_HOSTNAME A +notcp +ignore +time=3 +tries=1
  dig @YOUR_WORK_DNS_IPV4 YOUR_KNOWN_INTERNAL_HOSTNAME A +tcp +time=3 +tries=1
  curl -q --noproxy '*' --head --connect-timeout 5 --max-time 10 https://YOUR_KNOWN_WORK_HOST/

Use a harmless work endpoint that supports HEAD, or its normal read-only request.
Keep TLS verification enabled. For full-tunnel profiles only, public HTTPS is an
additional forwarding probe after confirming its route uses the work tunnel:
  route -n get 1.1.1.1
  curl -q --noproxy '*' --head --max-time 5 https://1.1.1.1/
A public probe or public-name lookup does not establish internal app access.

If those destinations should traverse the work VPN, verify their routes first.
Repeat after several minutes. Preserve ordinary system DNS tests separately from
explicit DNS-server tests. Do not blindly add a route via net_gateway: the right
path depends on both tunnel providers. Prove actual traffic as well as routes.

6. CHECK, STOP, AND USE BOUNDED TEST RUNS

Mac read-only diagnosis:
  python3 mac-relay-control.py diagnose DEV
  python3 mac-relay-control.py status DEV
Or double-click check-dev.command / check-live.command. These inspect job state,
socket ownership, last stop/error/counters and, for diagnose, a limited Tailscale
status summary. They send no test packets. A local listener or an online office
peer does NOT prove that the office relay, gateway or VPN traffic is working.

The Mac relay requires the configured Tailscale source address and verified utun
interface. It waits without forwarding when that path is absent, and recreates
its upstream socket on an interface change or recoverable socket error. Waiting
packets are dropped, not queued. A local_ready status checks the Mac listener,
source and current route only. stale_upstream identifies an old/wrong socket;
waiting_for_tailscale and recovering_upstream identify recovery in progress.
Do not send arbitrary UDP probes to the office relay port: it remembers the
latest accepted Mac source port, so a probe can divert OpenVPN's replies.

Windows logs are under %LOCALAPPDATA%\VPNRelay\logs. Logs contain timestamps,
readiness states, selected endpoint metadata, counts and numeric socket errors;
no packet payloads or raw Tailscale status JSON are logged. Receive error 10054
is tolerated only on receive stages, counted by side, with its first occurrence
logged. The observed gateway_send InvalidArgument/native10022 now closes only
the upstream socket and retries with 2, 4, 8, then at most 10 seconds between
attempts. Successful sends reset the delay. The Mac listener/filter and fixed
gateway stay unchanged. Failed/waiting packets are counted and dropped; they
are never replayed. Only selected address/route failures during replacement
setup retry; unrelated errors remain fatal. GATEWAY_RECOVERING,
GATEWAY_RETRY_WAIT, GATEWAY_RETRY_FAILED and GATEWAY_SOCKET_READY describe the
state. GatewayRecoveries, GatewayReconnects and RecoveryDrops are counters.
Socket-ready does not prove gateway replies or VPN authentication. Retry the
VPN if its attempt expired during recovery. An old exited process needs its
office launcher; the Mac starter cannot restart a Windows process.

Disconnect OpenVPN before deliberate relay maintenance. On Mac:
  python3 mac-relay-control.py stop DEV
or use stop-dev-relay.command. Stop works even if the config was removed.
On Windows use Ctrl+C in the corresponding foreground relay console. Closing it
also stops that relay. Neither side automatically restarts the other.

Optional bounded runs, after stopping any existing run:
  python3 mac-relay-control.py start DEV --seconds 600
  powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-relay.ps1 -Environment DEV -Action Start -MaxMinutes 10

Mac --seconds accepts 1..28800; omission means until stopped. The direct Windows
script retains a 480-minute default without -RunUntilStopped. Its everyday CMD
launchers explicitly pass -RunUntilStopped. Supplying that switch and an explicit
-MaxMinutes together is rejected. Bounded timers measure runtime; do not treat
the Mac's no-sleep expiry estimate as a guaranteed wall-clock deadline.

7. CLEANUP

After disconnecting the VPN and stopping both relays, remove an unused exact rule
from an elevated Windows PowerShell:
  powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Remove -Environment DEV

Repeat for LIVE if applicable. Remove refuses a conflicting rule instead of
deleting arbitrary firewall rules. Restore the prior Tailscale DNS/route-acceptance
preferences deliberately if you want them back. The kit does not remove devices
from your tailnet or delete VPN profiles. Runtime logs/config copies remain for
diagnosis; you can delete the kit's runtime directory after both jobs are stopped.

UPGRADE OR ROLL BACK

Disconnect OpenVPN and preserve current diagnosis/logs. Explicitly stop each
running Mac relay through its existing controller and each Windows relay with
Ctrl+C; confirm the listener is gone. Keep the old folder as a backup. Extract
the new kit into a separate folder on each computer, then copy your private
relay-config.json into each new folder. Do not include that edited config in
bug reports or public uploads. Review/unblock the new scripts, check Windows
readiness and ports, and start office first, Mac second from the new folders.
Check local_ready, then connect and verify routes, private DNS and work HTTPS.
Unchanged addresses/ports need neither a broader firewall rule nor a new VPN
profile. To roll back, stop the new processes before using the old launchers.

DEVELOPER VERIFICATION

Portable tests (Python 3.10+):
  python3 -B -m unittest discover -s tests -v
Native Windows PowerShell 5.1 parser and isolated configuration/scope tests:
  powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\tests\validate-powershell.ps1
Native Windows gateway-recovery fault tests:
  powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\tests\test-office-gateway-recovery.ps1

The Python suite uses temporary files inside tests/ and sockets bound only to
loopback. It checks binary forwarding, rejection of an unrelated upstream sender,
timer expiry, cleanup, source-route failure and useful diagnostics. A second
loopback-source integration case skips on systems without that source address;
the source guard still has direct checks. Controller tests use fixtures, not
real launchd operations. PowerShell tests parse scripts and use synthetic objects;
they do not invoke Tailscale or real firewall operations.

Recovery tests inject missing/changed routes, socket failures, and Windows10022
to check retry/backoff, rejected senders, preserved listeners and fatal unrelated
errors. The Windows recovery harness must run on Windows because the synthetic
SocketException native code maps differently on macOS/Linux. These tests do not
reproduce the original OS event, a real VPN renewal, or overnight uptime.

SHA256SUMS covers the distributed source files (not itself or the ZIP). It detects
content differences against the supplied manifest, not independent authenticity.
This kit uses the repository's MIT license; see LICENSE.
