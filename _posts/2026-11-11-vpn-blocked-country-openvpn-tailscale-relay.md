---
layout: post
title: "VPN Blocked? Restore OpenVPN Access with a Tailscale Relay"
date: 2026-11-11
last_modified_at: 2026-11-23
author: Max Lukin
tags: [vpn, openvpn, wireguard, tailscale, networking, troubleshooting, macos, windows]
categories: [engineering, networking, devops]
description: "Work VPN timing out abroad? Set up an OpenVPN UDP relay through a trusted remote PC with Tailscale, complete scripts, checks, and troubleshooting."
image:
  path: /assets/images/vpn-tailscale-relay.png
  width: 1200
  height: 630
  alt: "OpenVPN on a Mac reaches its work gateway through Tailscale and a trusted remote Windows PC."
---

## TL;DR

If your work VPN times out on your current network but works from a trusted PC elsewhere, that PC can forward the VPN's encrypted traffic for you.

My working path became:

~~~text
Mac: OpenVPN → local UDP relay
             → Tailscale → remote Windows PC: UDP relay
                         → work OpenVPN gateway
~~~

**This guide includes the complete scripts**, configuration, firewall setup, verification, daily commands, and fixes for the failures I encountered. It uses macOS, native Windows PowerShell, and an existing **OpenVPN-over-UDP** profile. No WSL installation or work VPN server change is needed.

Tailscale uses WireGuard, but it can also carry encrypted traffic through its DERP relays when a direct connection is unavailable. That alternative path worked in my case. It does not guarantee access on every restricted network.

[Download the complete relay kit]({{ '/assets/downloads/vpn-relay/vpn-relay-kit.zip' | relative_url }}) · [Read every source file](https://github.com/lukin-io/sesharim.github.io/tree/master/assets/downloads/vpn-relay)

**Updated November 23:** the kit also handles the socket failures found during everyday use: a Mac relay retaining the wrong network address, and a Windows gateway socket failing after nearly twelve days. Recovery happens inside the running relays. Starting after a reboot and restarting an exited process still require the launchers. Existing users should follow the [upgrade steps](#upgrade-an-existing-kit) before expecting the new behavior.

After moving to another country, both my DEV and LIVE work VPN profiles timed out. Searching for “WireGuard blocked in your country” was a starting point, but my profiles actually used **OpenVPN UDP/1194**. A successful comparison from a trusted office PC in another location gave me a usable route. It did **not** prove nationwide blocking or deep packet inspection.

The useful result was a working connection and a way to identify which part failed the next time.

Jump to [setup](#2-install-tailscale-and-verify-the-private-link), [daily use](#10-daily-use-and-stopping-cleanly), [troubleshooting](#troubleshooting-find-the-first-broken-link), or [Option B: ClearVPN](#option-b-a-managed-outer-vpn-such-as-clearvpn).

## What the pieces do

![OpenVPN on the Mac passes through a local relay, Tailscale, and a remote Windows relay to the work VPN gateway.]({{ '/assets/images/vpn-tailscale-relay.png' | relative_url }})

| Piece | Its job |
| --- | --- |
| **OpenVPN Connect** | Authenticates to your work VPN and encrypts its traffic, using your existing profile and credentials. |
| **Mac relay** | Listens only on `127.0.0.1`, then forwards those UDP packets to the remote PC. |
| **Tailscale** | Provides a private, encrypted connection between your two computers. Its private network is called a *tailnet*. |
| **Office relay** | Accepts packets only from your configured Mac and sends them only to the configured VPN gateway. |
| **TeamViewer, RDP, or another remote desktop** | Lets you administer the remote PC. It is not part of the VPN packet path. |

**Loopback** (`127.0.0.1`) means “this Mac.” A UDP relay forwards individual encrypted packets. **DERP** is Tailscale’s fallback relay when a direct peer connection is unavailable.

The relays do not log in to the work VPN or decrypt its payload. Keep the VPN profile, client private key, and password on the Mac. The remote PC needs the relay kit and gateway address.

Why can this help if WireGuard is blocked? The **outer transport is different**: Tailscale's direct WireGuard path uses UDP; DERP can carry its encrypted packets over HTTPS/TCP 443. DERP cannot decrypt them. Tailscale's coordination/relay services must still be reachable, and relayed traffic can be slower. [Firewall and transport documentation](https://tailscale.com/docs/reference/faq/firewall-ports), [DERP](https://tailscale.com/docs/reference/derp-servers).

## 1. Check that this approach fits your problem

You need:

- A Mac with an existing work OpenVPN profile and its normal login.
- A Windows PC in a location where that VPN gateway is reachable, with reliable internet and power.
- Permission to use that PC and connection for your work VPN.
- Tailscale installed on both computers, in the same tailnet.
- Python 3.10 or newer on the Mac; Windows PowerShell 5.1 is already included in the Windows setup used here.
- Administrator access on Windows for the narrow firewall rule.

**The supplied kit forwards IPv4 UDP.** It does not convert an OpenVPN TCP profile into UDP, and it is not a complete configuration guide for a standalone WireGuard client.

Check your profile without dumping its embedded keys:

~~~bash
awk '/^(proto|remote)[[:space:]]/ {print}' "$HOME/Downloads/work.ovpn"
~~~

A simple compatible profile looks like:

~~~text
proto udp
remote vpn.example.com 1194
~~~

Use your real profile path and actual port. If it has multiple `remote` entries, `<connection>` blocks, mixed transports, or managed settings, identify the intended UDP gateway with your VPN administrator before editing it.

Before building a relay, do the cheap comparisons:

1. Try the same profile on another local network, such as a phone hotspot.
2. Check that the hostname resolves and that the client reaches the network stage rather than failing to load the profile.
3. Confirm that the same account/profile can connect from the remote location, with the Mac session disconnected during the comparison.
4. Read the client log: a local configuration error, certificate error, and authentication rejection are different from a server timeout.

A client update or a second OpenVPN client can distinguish a client problem from a path problem. **Tunnelblick**, for example, is another macOS OpenVPN client. Changing clients was a useful diagnostic comparison in this investigation, but it did not replace the working remote route.

If the profile fails from the remote location too, fix that failure first. A relay cannot repair an expired certificate or rejected password.

## 2. Install Tailscale and verify the private link

Install [Tailscale on macOS](https://tailscale.com/docs/install/mac) and [Windows](https://tailscale.com/docs/install/windows) from its official distribution. Sign in to the same tailnet on both devices and approve the required network extension/VPN permissions.

On the Mac, with the standalone Tailscale app:

~~~bash
TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
"$TS" status
"$TS" ip -4
~~~

On Windows, in **PowerShell**:

~~~powershell
& "$env:ProgramFiles\Tailscale\tailscale.exe" status
& "$env:ProgramFiles\Tailscale\tailscale.exe" ip -4
~~~

Record the Mac's and remote PC's Tailscale IPv4 addresses. These are the `100.x.y.z` node addresses, not public IPs or home Wi-Fi addresses.

On the Mac, replace the placeholder with the remote PC's actual Tailscale address:

~~~bash
OFFICE_TS_IP="REPLACE_WITH_OFFICE_TAILSCALE_IPV4"
"$TS" ping --c=3 --until-direct=false "$OFFICE_TS_IP"
~~~

A reply via `DERP(region)` is a working relayed path. A reply marked `direct` is a direct path. Tailscale's default ping can keep trying for a direct connection; inspect the replies instead of treating “direct connection not established” as proof that no connection works. [Connection types](https://tailscale.com/docs/reference/connection-types), [CLI reference](https://tailscale.com/docs/reference/tailscale-cli).

Before connecting the work VPN, record the current route to the office PC:

~~~bash
route -n get "$OFFICE_TS_IP"
~~~

Keep this output for comparison in step 9. Interface numbers can change after a restart.

This checks the Tailscale peer path. It does **not** prove that Windows allows the relay's UDP port or that a relay process is listening.

For this setup, leave Tailscale connected but select **no exit node**. We also used `accept-dns=false` and `accept-routes=false` so Tailscale did not supply competing DNS or subnet routes. On a dedicated relay PC:

~~~powershell
& "$env:ProgramFiles\Tailscale\tailscale.exe" set --accept-dns=false --accept-routes=false --exit-node=
~~~

On the Mac:

~~~bash
"$TS" set --accept-dns=false --accept-routes=false --exit-node=
~~~

These preferences persist. If you already depend on Tailscale DNS, subnet routes, or an exit node, record the current settings and resolve that requirement before applying this arrangement. Disconnect other full-tunnel VPNs while establishing this baseline.

If your organization manages tailnet access, it must permit the Mac to reach the remote PC's selected UDP ports. Tailnet access and Windows Firewall are separate controls. Grants are additive: adding a narrow grant does not cancel an existing broad grant. Keep any policy changes scoped to the intended devices and review the existing policy. [Tailscale grants](https://tailscale.com/docs/reference/syntax/grants).

## 3. Download the files and keep them together

Download [vpn-relay-kit.zip]({{ '/assets/downloads/vpn-relay/vpn-relay-kit.zip' | relative_url }}) on both computers. It contains a `vpn-relay` folder, including all source code and an MIT license. Review the source before running it.

On the Mac, if the ZIP is in Downloads:

~~~bash
unzip "$HOME/Downloads/vpn-relay-kit.zip" -d "$HOME"
cd "$HOME/vpn-relay"
python3 --version
chmod +x ./*.command
~~~

If Python is missing or older than 3.10, install a current [Python macOS package](https://www.python.org/downloads/macos/) and reopen Terminal. The relay uses Python's standard library; it does not need `pip install`.

On Windows:

~~~powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\vpn-relay-kit.zip" -DestinationPath "$env:USERPROFILE\Documents"
Set-Location "$env:USERPROFILE\Documents\vpn-relay"
~~~

Use a fresh destination if a folder from an older kit already exists. Do not overwrite running relay code.

After reviewing the downloaded PowerShell source, clear its downloaded-file marker from this folder:

~~~powershell
Get-ChildItem . -Filter *.ps1 | Unblock-File
~~~

The Windows commands and launchers below use `-ExecutionPolicy RemoteSigned` for that **one process**. This permits reviewed local scripts without changing your computer's permanent execution policy. Unblocking alone is insufficient when the default policy is `Restricted`. An organization's Group Policy still takes precedence; do not override it. [PowerShell execution policies](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies).

| File | What is inside |
| --- | --- |
| [relay-config.example.json]({{ '/assets/downloads/vpn-relay/relay-config.example.json' | relative_url }}) | Address and port template. You create `relay-config.json` from it. |
| [mac-relay.py]({{ '/assets/downloads/vpn-relay/mac-relay.py' | relative_url }}) / [mac_relay_core.py]({{ '/assets/downloads/vpn-relay/mac_relay_core.py' | relative_url }}) | Local UDP forwarder, Tailscale source/interface checks, socket recovery, and counters. |
| [mac-relay-control.py]({{ '/assets/downloads/vpn-relay/mac-relay-control.py' | relative_url }}) | Start, stop, status, diagnosis, and explicit macOS `launchd` job management. |
| [office-relay.ps1]({{ '/assets/downloads/vpn-relay/office-relay.ps1' | relative_url }}) | Tailscale readiness checks, restricted forwarding, gateway-socket recovery, and Windows diagnostics. |
| [office-firewall.ps1]({{ '/assets/downloads/vpn-relay/office-firewall.ps1' | relative_url }}) | Plan, add, or remove the narrow Windows firewall rule. |
| `relay_config.py` / `relay-config.ps1` | Shared configuration validation; included beside the relay scripts. |
| `start-*.command` / `stop-*.command` / `check-*.command` | Mac shortcuts to the controller. |
| `start-office-dev.cmd` / `start-office-live.cmd` | Windows starters; full contents are shown below. |
| `check-office-relays.cmd` | Read-only checks for configured Windows relays. |

[Browse the whole directory](https://github.com/lukin-io/sesharim.github.io/tree/master/assets/downloads/vpn-relay) for every launcher and test. There is no private helper file to obtain separately.

## 4. Fill in one configuration

On the Mac:

~~~bash
cp relay-config.example.json relay-config.json
~~~

On Windows:

~~~powershell
Copy-Item .\relay-config.example.json .\relay-config.json
~~~

Edit `relay-config.json` as plain-text JSON on both computers:

~~~json
{
  "configured": false,
  "office_tailscale_ip": "CHANGE_ME_OFFICE_TAILSCALE_IPV4",
  "mac_tailscale_ip": "CHANGE_ME_MAC_TAILSCALE_IPV4",
  "profiles": {
    "DEV": {
      "gateway_ip": "192.0.2.10",
      "gateway_port": 1194,
      "office_port": 11194,
      "mac_port": 11195
    },
    "LIVE": {
      "gateway_ip": "192.0.2.20",
      "gateway_port": 1194,
      "office_port": 11196,
      "mac_port": 11197
    }
  }
}
~~~

The `192.0.2.x` values are documentation examples, **not working gateways**. The kit deliberately rejects unconfigured examples.

Replace:

1. `office_tailscale_ip` with the remote PC's address from step 2.
2. `mac_tailscale_ip` with the Mac's Tailscale address.
3. Each `gateway_ip` with an actual public IPv4 address of the authorized OpenVPN gateway.
4. `gateway_port` if the profile uses another UDP port.
5. `configured` with `true` after completing those values.

Keep the local ports as shown unless they conflict with another application. They are different on purpose.

If your original profile contains a hostname, resolve it **on the remote Windows PC**:

~~~powershell
Resolve-DnsName vpn.example.com -Type A
~~~

Use the actual hostname from your profile. For multiple answers, select an address confirmed to serve that profile. This kit pins that address; it does not implement discovery or automatic failover. If the provider changes its addresses, revalidate and update the configuration.

**Only one work VPN?** Delete the `LIVE` object and use the DEV launchers. The names label two independent configurations; they do not require two subscriptions or servers.

Use identical configuration values on both machines. The config contains addresses and ports, not VPN passwords or key material.

## 5. Allow only the intended traffic on Windows

The firewall helper is separate from the relay. Starting a relay does not silently open firewall access.

From the kit folder, inspect the proposed DEV rule:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Plan -Environment DEV
~~~

The rule should allow only inbound UDP on the selected office port, the remote PC's exact Tailscale address/interface, the configured Mac source address, and the Windows PowerShell executable.

Then open **PowerShell as Administrator**, return to the same folder, and add it:

~~~powershell
Set-Location "$env:USERPROFILE\Documents\vpn-relay"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Add -Environment DEV
~~~

For a configured LIVE profile, repeat with `-Environment LIVE`.

Do not add a router port-forward, bind to `0.0.0.0`, disable Windows Firewall, or enable a Tailscale exit node for this guide. None is needed for this packet path.

## 6. Start the remote relay

Return to an ordinary, non-administrator PowerShell window:

~~~powershell
Set-Location "$env:USERPROFILE\Documents\vpn-relay"
.\check-office-relays.cmd
.\start-office-dev.cmd
~~~

Wait for **`LISTENING`**. A printed configuration block is only a plan; it does not prove that a socket was acquired.

This is the complete `start-office-dev.cmd`:

~~~bat
@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0office-relay.ps1" -Environment DEV -Action Start -RunUntilStopped
set "vpnRelayExit=%ERRORLEVEL%"
echo.
echo Relay stopped. Exit code: %vpnRelayExit%
pause
exit /b %vpnRelayExit%
~~~

And `start-office-live.cmd`:

~~~bat
@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0office-relay.ps1" -Environment LIVE -Action Start -RunUntilStopped
set "vpnRelayExit=%ERRORLEVEL%"
echo.
echo Relay stopped. Exit code: %vpnRelayExit%
pause
exit /b %vpnRelayExit%
~~~

Both files are included in the ZIP. Run them in separate windows if you need both relay pairs available.

`%~dp0` means “the folder containing this CMD file,” so the launcher works without a hard-coded Windows username.

**Leave the relay window open.** Disconnecting remote desktop does not require closing it. Keep the PC awake and online. Automatic Windows login or an unlocked desktop is not a prerequisite; those are separate remote-administration choices.

If Tailscale is still becoming ready, the script waits briefly. If it cannot acquire the expected address, it reports service/backend/address state instead of an unexplained `Get-NetIPAddress` exception.

## 7. Start the Mac relay

From the Mac kit directory:

~~~bash
cd "$HOME/vpn-relay"
python3 mac-relay-control.py start DEV
python3 mac-relay-control.py diagnose DEV --human
~~~

Or double-click `start-dev-relay.command`, followed by `check-dev.command`.

Expect a local listener at `127.0.0.1:11195` and **until-stopped** mode. For LIVE, use `LIVE` or its launchers; its local port is `11197`.

The updated check also verifies the upstream socket's source address and route. **`local_ready` means the Mac side is ready**; the remote relay and VPN gateway still need to return traffic. If it reports `waiting_for_tailscale`, keep Tailscale connected and let the running relay wait for the expected address and interface. Repeating Start does not replace an already-running process.

The controller loads an explicit `launchd` job. An early “detached” relay still died when its parent application was force-quit. A different PID, parent PID of 1, or separate process group had not been enough. Moving ownership to `launchd` gave us the intended lifecycle.

The launcher window can close after a successful Mac start. **The job does not automatically start at login/reboot or restart after a crash.** That is separate from having no expiry timer.

If macOS asks you to review a downloaded executable file, inspect the source and use the normal system approval flow. You can also run the Python controller directly as above; no global security setting needs to be disabled.

## 8. Create a relay copy of your OpenVPN profile

Keep the original profile unchanged. Copy it to a clearly named local file, such as `DEV-via-relay.ovpn`.

For a simple UDP profile, replace its original remote line:

~~~text
remote vpn.example.com 1194
~~~

with:

~~~text
remote 127.0.0.1 11195
~~~

For LIVE:

~~~text
remote 127.0.0.1 11197
~~~

Keep `proto udp` (or the original compatible UDP setting) and retain the original certificate authority, client certificate/key, `tls-crypt`/`tls-auth` settings, server-certificate verification, ciphers, routes, and DNS behavior.

Do not replace an expected server certificate name with `localhost`. The authenticated peer is still the real work gateway. Do not disable certificate verification to accommodate the relay. OpenVPN distinguishes the transport endpoint from certificate verification settings. [OpenVPN configuration reference](https://openvpn.net/community-docs/community-articles/openvpn-2-6-manual/).

For profiles with multiple remotes or connection blocks, ensure the relay copy cannot fall back to a direct endpoint. Get an administrator-reviewed equivalent if the profile is generated or managed.

Import the copy into OpenVPN Connect. Connect **only one work VPN profile at a time** and enter your normal work credentials there. The office relay never needs that password.

The VPN gateway will see the remote PC's internet source address. The relay does not change the account, certificate, or server-side authorization rules.

## 9. Verify useful traffic, not just “Connected”

There are three separate successes:

1. Tailscale can reach the remote PC.
2. OpenVPN authenticates and establishes a tunnel.
3. Work traffic actually follows that tunnel and gets replies.

Check OpenVPN's log for a successful connection and its assigned tunnel address. Then inspect routes on the Mac:

~~~bash
route -n get "$OFFICE_TS_IP"
route -n get REPLACE_WITH_WORK_PRIVATE_DNS_IPV4
~~~

Compare the office route with the baseline from step 2. The office Tailscale address should still use the Tailscale path. The private work DNS should use the work VPN path. On this Mac, those were two **different `utun` interfaces**. The numeric interface names can change.

Do not accidentally route the remote PC through the work VPN that depends on that PC. If the work VPN captures the Tailscale path, stop and fix that route conflict with your administrator. The exact routes depend on full versus split tunneling; adding a guessed route is not a general fix. [Tailscale and other VPNs](https://tailscale.com/docs/reference/faq/other-vpns).

Get the private DNS address from the VPN’s pushed DNS settings or your administrator, and use an internal hostname you normally access. Do not guess either value. If your VPN supplies no private DNS, use a known authorized private resource for the route and traffic checks instead.

Test the private DNS server supplied by your work VPN:

~~~bash
WORK_DNS="REPLACE_WITH_WORK_PRIVATE_DNS_IPV4"
WORK_NAME="REPLACE_WITH_KNOWN_INTERNAL_HOSTNAME"

dig @"$WORK_DNS" "$WORK_NAME" A +time=3 +tries=1 +notcp +ignore
dig @"$WORK_DNS" "$WORK_NAME" A +time=3 +tries=1 +tcp
~~~

Expect the correct internal answer over both transports. A public DNS lookup alone does not prove access to private work resources.

Next, test a harmless, known work HTTPS endpoint:

~~~bash
curl -q --noproxy '*' --head --connect-timeout 5 --max-time 10 \
  "https://REPLACE_WITH_KNOWN_WORK_HOST/"
~~~

Use an endpoint that supports HEAD, or perform its normal read-only request. A `401`/`403` may establish transport reachability; successful application access is a separate check. Keep TLS verification enabled—do not add `-k`.

For a **full-tunnel** profile, an additional public HTTPS probe is useful after confirming its route:

~~~bash
route -n get 1.1.1.1
curl -q --noproxy '*' --head --connect-timeout 5 --max-time 10 https://1.1.1.1/
route -n get 1.1.1.1
~~~

If that address uses your normal internet interface, this request is not evidence about VPN forwarding. Split-tunnel users should test a destination routed through their work VPN instead.

Finally, leave the connection in use long enough to cross its ordinary authentication/credential-renewal interval. Watch for reconnects or password prompts. A five-second test does not establish reliable renewal or all-day uptime.

## 10. Daily use and stopping cleanly

Start in this order:

1. Tailscale connected on both machines.
2. Matching Windows relay reporting `LISTENING`.
3. Matching Mac relay reporting `local_ready`.
4. OpenVPN connected with the relay profile.
5. A known private resource working.

The everyday Windows commands are:

~~~powershell
.\start-office-dev.cmd
.\start-office-live.cmd
~~~

The Mac starters are `start-dev-relay.command` and `start-live-relay.command`. Both relay pairs can run; connect only the work VPN you need.

**The eight-hour trap:** an old command containing `-MaxMinutes 480` explicitly requests an eight-hour limit. The supplied daily starters pass `-RunUntilStopped`. The Windows script's direct bounded mode remains available for tests; use the starters for everyday work. On the Mac, omitting `--seconds` means no scheduled expiry.

To stop DEV:

1. Disconnect DEV in OpenVPN.
2. On the Mac, run `python3 mac-relay-control.py stop DEV` or `stop-dev-relay.command`.
3. In the DEV office relay window, press **Ctrl+C** and confirm that it actually stopped.

Use the equivalent LIVE commands for LIVE. If remote-desktop keyboard shortcuts are not forwarded correctly, verify the process/window state rather than assuming the shortcut worked.

After a reboot, start the relay processes again. “Run until stopped” removes a timer; it does not make a laptop stay awake, keep a PC powered on, or install a background service.

### Upgrade an existing kit

Downloading new files does not change code already loaded in a running process. The Mac controller also keeps a private runtime copy, so both ends need an explicit stop/start when upgrading.

1. Save the current diagnosis and logs, then disconnect the work VPN. Stop each running Mac relay with its existing `stop-*.command`; stop each office relay with Ctrl+C and confirm that its console returns.
2. Keep the old kit as a rollback copy. Extract the new ZIP into a separate folder on both computers. Copy your existing `relay-config.json` into each new folder; keep those real addresses private.
3. Review the new scripts and unblock the reviewed PowerShell files as in step 3. Keep the shared modules beside the launchers. Run `check-office-relays.cmd` and confirm the expected addresses and free ports. An unchanged configuration does not need a wider firewall rule.
4. Start the matching office launcher from the new folder, then the Mac launcher from the new folder. Confirm `LISTENING` on Windows and `local_ready` on the Mac before connecting OpenVPN.
5. Repeat the route, private DNS, and HTTPS checks in step 9. Keep the backup until the updated path works. To roll back, stop the new processes first, then use the old folder's launchers.

There is no need to reimport the VPN profile or change its credentials when its loopback endpoint and the relay configuration remain the same.

## Troubleshooting: find the first broken link

On the Mac:

~~~bash
cd "$HOME/vpn-relay"
python3 mac-relay-control.py diagnose DEV --human
~~~

On Windows, from the kit folder:

~~~powershell
.\check-office-relays.cmd
~~~

Use `LIVE` for the corresponding Mac diagnosis. The Mac output includes current process/listener state, log paths, and a suggested next action. Windows writes timestamped relay events to the log path printed at startup. Neither check confuses “Tailscale says online” with “the work VPN is usable.”

| Symptom | What to check | What to do next |
| --- | --- | --- |
| OpenVPN times out, but Tailscale and the remote PC are online | Check the Mac process, source/route, and reply counters, then the matching Windows relay window. | Start the missing or stopped relay on the correct computer. An online PC does not prove its forwarding process is alive. |
| Mac check reports `stale_upstream` | Compare the socket's source with the configured Mac Tailscale address. | Disconnect OpenVPN, then explicitly stop/start the updated Mac relay. Starting an already-running relay does not replace its old code. |
| Mac check reports `waiting_for_tailscale` or `recovering_upstream` | The current Tailscale address/interface and latest recovery event. | Restore Tailscale and let the updated relay recreate its upstream socket. Retry OpenVPN if its own connection attempt timed out. |
| Mac reports `local_ready`, but gets no replies | Matching office process, counters, gateway, and access rules. | Continue with office-side diagnosis; local readiness is not an end-to-end test. |
| `Get-NetIPAddress` cannot find the expected IP | Tailscale service/backend state, `tailscale ip -4`, and Windows interface addresses. | Wait for readiness, sign in if needed, or correct a changed node address. The exception alone does not distinguish those causes. |
| Port already occupied | Read the current socket owner's PID and address. | Keep the correct existing relay or stop it deliberately. Do not launch duplicates or kill an old PID copied from notes. |
| Tailscale ping replies, office counters stay at zero | Configured source/destination IPs and ports, Windows rule, and tailnet policy. | Fix the UDP access path. Tailscale's own ping does not test the application's UDP listener. |
| Office sent packets, but no gateway replies | Correct gateway IPv4/UDP port and reachability from the office network. | Revalidate the destination and server status. A pinned IP can become stale. |
| Gateway replies arrive, but OpenVPN cannot connect | Relay return counters, then OpenVPN TLS/authentication logs. | Diagnose the client/server error at the stage it reports. |
| “Authentication failed” | Correct profile, username, password, keyboard layout, and server policy. | Correct the login. Transport has progressed further than a silent timeout. |
| Windows receive error `10054` | The reported operation and side. | The kit records and tolerates this specific receive-stage reset. Do not extend that handler to unrelated errors. |
| Windows `gateway_send` fails with `InvalidArgument/10022` | Recovery events and whether the process is still running. | The updated kit recreates that gateway socket with backoff. An older exited process needs the office starter. Repeated recovery without replies still needs gateway/network diagnosis. |
| Mac relay stops with `upstream_send errno=49` | Preserve the log, check the current Tailscale address/route, and identify which kit is running. | Upgrade and restart an old stopped process. The updated running relay retries recoverable upstream errors; the code alone does not identify the original trigger. |
| Connected label, unusable work apps | Routes, private DNS over UDP/TCP, and a real work endpoint. | Fix the failed layer; the label alone is insufficient. |
| Works until a later password/renewal prompt | Client authentication settings and server renewal policy. | Remove temporary diagnostic overrides you introduced; preserve organization requirements. |
| Stops after closing a terminal or controlling app | Which process owns the relay and how it was started. | Use the Mac controller/launchers; leave the Windows relay window running. |

### The failure that looked like blocking—but was a timer

One later outage was particularly misleading. The office PC was online, its relay was running, and OpenVPN kept timing out.

The Mac relay log showed:

~~~text
STOPPED reason=time_limit elapsed_s=28800.1
~~~

`28,800` seconds is eight hours. The process had exited normally; no program was left to forward OpenVPN's loopback traffic.

Restarting the Mac relay restored authentication and useful traffic. We then changed everyday operation to run until stopped **on both ends**, with explicit bounded modes retained for diagnostics.

The old Mac timer used a monotonic clock that excluded system sleep. A displayed wall-clock expiry was only an estimate. The terminal log event and missing listener were stronger evidence than a predicted time.

### November 12: Tailscale connected, Mac relays absent

The next incident had a different cause. Both Tailscale devices appeared online and a live probe received a DERP reply, but neither Mac relay job was loaded and neither local UDP listener existed. The previous DEV process had ended on a signal before a recorded Mac boot; the signal's sender was not established. Removing the timer had not installed reboot autostart.

Restarting the Mac relays restored DEV authentication. Route checks, private DNS over UDP/TCP, and certificate-verified HTTPS then passed. No office-PC restart or relay change was needed. LIVE's local relay was restarted, but its VPN authentication and traffic were not retested that day.

For the same missing-listener case:

1. Keep Tailscale connected on both machines and confirm that the matching office relay reports `LISTENING`.
2. Disconnect the affected OpenVPN profile. From the Mac kit folder, preserve the diagnosis and its reported log paths:

~~~bash
cd "$HOME/vpn-relay"
python3 mac-relay-control.py diagnose DEV --human
~~~

3. If there is no running managed relay and no conflicting socket owner, start it and check again:

~~~bash
python3 mac-relay-control.py start DEV
python3 mac-relay-control.py diagnose DEV --human
~~~

4. Confirm that the managed job owns its expected local listener. Use `LIVE` instead for that environment; do not launch duplicate processes.
5. Reconnect OpenVPN and repeat the route, DNS, and HTTPS checks in step 9. A local listener proves only the local relay is ready.

A separate earlier LIVE run had stopped at `upstream_send errno=49`, which this Mac mapped to `EADDRNOTAVAIL`: the requested local address was unavailable. It occurred after sleep/resume, but we did not establish what triggered it. Preserve the error, verify the current Tailscale path, and restart the stopped relay; do not treat it as a password error or proof of filtering. [Apple's error definition](https://developer.apple.com/documentation/foundation/posixerror/eaddrnotavail).

### November 16: two separate stopped layers

A later LIVE timeout exposed two blockers: Tailscale was disconnected, and the Mac LIVE relay had no running process or UDP listener. Its `launchd` job definition was still loaded, which did not mean the process was alive. The latest relay log showed an unlimited run ending on November 13 with `upstream_send errno=49`, not a timer expiry. The disconnected Tailscale state observed on November 16 does not establish what caused that earlier crash.

The recovery order matters: cancel the failed OpenVPN attempt, reconnect Tailscale, confirm a peer reply, then use the existing starter for the stopped Mac relay. Recheck its listener before connecting OpenVPN and repeating step 9's traffic tests. Leave an already-running relay for the other environment alone.

After those steps, LIVE authenticated and passed private DNS over UDP/TCP and certificate-verified HTTPS, with routes checked before and after. No office-PC restart or relay change was needed, and DEV was left untouched. This was a short recovery check, not a new uptime or renewal test.

### Windows UDP resets need narrow handling

Windows can report `WSAECONNRESET/10054` during UDP receive following an ICMP Port Unreachable response to an earlier send. That does not mean a TCP-style connection was established and then closed. [Microsoft UDP receive documentation](https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-recvfrom).

We initially limited recovery to that receive error and counted it. Later evidence justified a separate handler for one gateway-send failure, described below. Other errors remain visible with their operation and numeric code.

Silently catching every exception would have recreated the original problem: a script that appears alive while traffic is broken.

### November 19: a listener on the wrong network path

DEV timed out while LIVE worked. Both Mac relays had a local listener, but DEV's upstream socket still used a Wi-Fi source address; LIVE used the Tailscale address. DEV sent connection packets and received no replies. Creating a fresh DEV socket selected the correct source and restored authentication and useful traffic.

The fix was to make that requirement explicit in the shared Python core: verify the expected Tailscale address and `utun` interface, bind to both, and check again when the interface changes or a recoverable socket error occurs. While Tailscale is unavailable, the relay keeps its loopback listener but drops waiting packets instead of forwarding them through the physical interface. OpenVPN may need a retry if its attempt has already expired.

The diagnostic now distinguishes a missing process, a stale upstream socket, a relay waiting for Tailscale, and `local_ready`. This is why “the process is running” was too weak a check. The event that originally selected the wrong source was not captured; the observed source mismatch and successful recovery were.

### November 23: the Mac was ready, but the office relay had crashed

The next timeout survived restarting the Mac launcher. Tailscale could reach the remote PC directly, and the Mac used the correct source and route. The missing piece was on Windows: its DEV relay had exited after almost twelve days of continuous runtime.

The useful part of the error was:

~~~text
FATAL stage=gateway_send socket_error=InvalidArgument native_code=10022 packet_bytes=54
STOPPED reason=error duration_mode=until_stopped
~~~

Those are the relevant fields from the original log, with endpoint and machine metadata omitted. `until_stopped` ruled out the old eight-hour timer. Restarting **only the office relay** restored DEV; the Mac process stayed unchanged. Authentication, queries to the work VPN's private DNS server over UDP/TCP, and certificate-verified public HTTPS routed through the work tunnel all passed. Those probes establish forwarding; an internal application still needs its own check.

Microsoft defines `10022` as an invalid argument error, which can also reflect socket state. That identifies the failed operation; it does not tell us which earlier Windows or network event caused it. [Winsock error reference](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2).

The PowerShell fix keeps the Mac-facing listener and replaces only the failed gateway socket. It retries after 2, 4, 8, then at most 10 seconds, resetting the delay only after a successful send. Failed and waiting packets are counted and dropped, not queued for later replay. The destination stays fixed, and the allowed Mac address and firewall scope stay the same.

Logs now show `GATEWAY_RECOVERING`, `GATEWAY_RETRY_WAIT`, `GATEWAY_RETRY_FAILED`, and `GATEWAY_SOCKET_READY`, alongside recovery/drop counters. A new UDP socket is not a handshake with the server: check returning packets and work traffic before declaring success. Unrelated exceptions still stop the relay visibly.

The complete generic implementation and its tests are in the downloadable kit. The download contains placeholders, not my real hostnames, device addresses, account details, or VPN credentials. Supply your own approved configuration.

**If this happens on an older installation:** preserve the error, run the matching `start-office-dev.cmd` or `start-office-live.cmd` on the remote PC, then retry OpenVPN. The Mac's similarly named starter cannot restart the Windows process. Upgrade afterward to gain the recovery handler.

### Avoid adding unrelated changes

Slack Huddles also failed on one of the networks, while browser-based Google Meet worked. That was a clue about different network paths, not proof of the VPN's cause. Speaker tests could not establish whether UDP/1194 reached the work gateway.

Likewise, weakening OpenVPN's security setting did not become the solution. Preserve the cryptographic settings required by the work server and diagnose transport separately.

## What was actually verified

On the original Mac/Windows setup, both DEV and LIVE authenticated through the remote relay. After the timer change, both passed:

- queries through the private work DNS server over UDP and TCP;
- public HTTPS routed through the work VPN, with certificate verification enabled;
- route checks before and after the probes;
- forwarding in both directions, with DEV restored as the active session afterward.

A separate Tailscale probe returned through DERP. That establishes a working relayed connection at that time, not a diagnosis of the country's filtering equipment.

The downloadable kit is a **sanitized, configurable adaptation** of those scripts. Its checks and tests are documented in [README.txt]({{ '/assets/downloads/vpn-relay/README.txt' | relative_url }}). The real-session results above belong to the original configured deployment; they do not substitute for checking your addresses, firewall, routes, authentication, and resources.

For the November recovery changes, tests exercise route changes, missing addresses, socket replacement, backoff, and errors that must remain fatal. The Windows gateway recovery was tested with injected faults on native Windows PowerShell 5.1. After deployment, DEV authenticated and passed the route/DNS/HTTPS checks again. Specifically, the DNS probe queried a public name through the private work DNS server, and the HTTPS probe reached a public endpoint through the full work tunnel. Neither proves access to every internal application. The updated LIVE office listener was verified, but LIVE authentication and traffic were not retested during that repair.

No new all-day soak test or credential-renewal test was performed after these recovery changes. The original operating-system failure was not reproduced. Automatic restart after reboot/process exit and gateway failover are not included; recovery inside a running process is a separate capability.

## What if Tailscale cannot connect either?

First distinguish sign-in/extension setup from a network failure. If the private link itself cannot work, these UDP relays have no transport to use.

An alternative worth evaluating is [wstunnel](https://github.com/erebe/wstunnel), which can carry UDP through a WebSocket/HTTP-based tunnel. It requires a reachable server counterpart and a reviewed TLS/access configuration. Installing only its client on the Mac is not a complete solution.

We did not need to deploy wstunnel once the Tailscale path worked, so it is not presented as a tested drop-in replacement. Likewise, simply changing an OpenVPN profile to TCP/443 works only if the server actually offers that transport. Port 443 alone does not turn OpenVPN into ordinary HTTPS or guarantee that filtering will allow it.

## Option B: a managed outer VPN, such as ClearVPN

The remote-PC route solved access, but it also added processes to maintain and a computer that must stay online. A simpler path is worth testing:

~~~text
Mac: work OpenVPN → ClearVPN → work OpenVPN gateway
~~~

If this combination works, ClearVPN could replace Tailscale, both custom relays, and the remote-PC dependency. It would still be a second tunnel carrying the work VPN. OpenVPN would continue to handle the employer's authentication, encryption, and private-network access.

The ClearVPN build I inspected offered Hysteria2. That makes it a reasonable candidate for a restricted network: Hysteria2 carries TCP and UDP through QUIC. It still depends on UDP reaching its server, so a network that drops that traffic can defeat it too. A protocol option in a menu is not evidence that two VPN clients will coexist correctly on macOS. [Hysteria2 protocol](https://v2.hysteria.network/docs/developers/Protocol/), [transport configuration](https://v2.hysteria.network/docs/advanced/Full-Client-Config/#transport).

**This alternative has not been verified with the work profiles used in this guide.** I would evaluate it in a separate trial:

1. Keep the working relay configuration as a fallback. Disconnect the work VPN, Tailscale, and other outer VPNs for this isolated trial. Use a separate copy of the **original profile targeting the real work gateway**. The relay copy pointing to `127.0.0.1` cannot work without its local forwarder.
2. Connect ClearVPN using the candidate protocol, then try the original work profile. Verify that packets to the work gateway actually use ClearVPN and that the outer tunnel's server remains reachable outside the work tunnel. Recheck after OpenVPN applies its routes; two connected icons are insufficient.
3. Repeat the private DNS and HTTPS checks from step 9 for each work profile independently. Stop if routing or DNS from one client breaks the other; resolve that configuration rather than weakening certificate checks or the employer's VPN policy.
4. Test sleep/wake, Wi-Fi-to-hotspot changes, reconnects, a reboot, and a normal credential-renewal cycle. Use it through the next morning before retiring the existing fallback.

To return to the relay path, disconnect the work VPN and ClearVPN, reconnect Tailscale, check both relays, then select the original relay profile. Keep the two paths separate while comparing them.

Compare latency to the **same work resource** over both complete paths. Removing the office detour might improve it; a distant provider server or TCP fallback might make it worse. Ping to ClearVPN's server alone does not answer that question.

If the UDP-based candidate fails, a different transport is more useful than repeatedly selecting similar ones. [Proton's Stealth protocol](https://protonvpn.com/blog/stealth-vpn-protocol), for example, uses obfuscated TLS over TCP. It would need the same coexistence and work-traffic checks; this is another candidate, not a tested substitute.

For a relay I intended to depend on every day, the other improvement would be a dedicated, always-on host with supervised services, startup after reboot, and useful failure alerts. That removes the desktop's power, login, and terminal-window dependency, but still needs maintenance and a tested fallback. The manual kit above does not install that infrastructure. An employer-supported reachable VPN endpoint would remove more moving parts, if the employer can provide one.

## Remove the setup when you no longer need it

Disconnect the work VPN and stop both sides of each relay first. The Mac controller's `stop` command unloads its job.

Then, in administrator PowerShell from the Windows kit folder:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Remove -Environment DEV
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\office-firewall.ps1 -Action Remove -Environment LIVE
~~~

Run the LIVE command only if you configured it. Remove the relay copies of the OpenVPN profiles, retaining your originals. Restore any recorded Tailscale preferences you changed; disconnect or remove the devices from your tailnet if that private link is no longer needed.

The practical lesson is to check the whole chain in order: **local relay → private link → remote relay → VPN authentication → work traffic**. An online remote PC tells you about one piece. A working, verified route tells you considerably more.
