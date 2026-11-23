#requires -Version 5.1
# Fault injection only: imports selected AST definitions, never starts a relay,
# changes settings, sends packets, or contacts the office/VPN gateway.
[CmdletBinding()]
param([string] $RelayDirectory = (Split-Path $PSScriptRoot -Parent))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'Run these Winsock-code tests on native Windows; other platforms translate SocketException native codes.'
}

function Assert-Equal($actual, $expected, [string] $message) {
    if ($actual -ne $expected) { throw "$message (actual=$actual expected=$expected)" }
}
function Assert-Throws([scriptblock] $body, [string] $message) {
    $thrown = $false
    try { & $body } catch { $thrown = $true }
    if (-not $thrown) { throw $message }
}
function New-TestState($udp) {
    return [pscustomobject]@{
        Socket = $udp; RetryAt = 0.0; RetryDelay = 2.0
        Recoveries = 0L; Reconnects = 0L; DroppedPackets = 0L
    }
}

Add-Type -TypeDefinition @'
using System;
using System.Net;
using System.Net.Sockets;
public sealed class RelayTestClient {
    public IPEndPoint LocalEndPoint = new IPEndPoint(IPAddress.Parse("192.0.2.10"), 50000);
    public IPEndPoint RemoteEndPoint = new IPEndPoint(IPAddress.Parse("192.0.2.20"), 1194);
}
public sealed class RelayTestUdp {
    public RelayTestClient Client = new RelayTestClient();
    public int SendFailure, Sends, Receives, Closes;
    public IPEndPoint Sender = new IPEndPoint(IPAddress.Parse("127.0.0.2"), 51000);
    public IPEndPoint LastDestination;
    public int Send(byte[] packet, int length) {
        Sends++;
        if (SendFailure != 0) { throw new SocketException(SendFailure); }
        return length;
    }
    public int Send(byte[] packet, int length, IPEndPoint destination) {
        LastDestination = destination;
        return Send(packet, length);
    }
    public byte[] Receive(ref IPEndPoint sender) {
        Receives++;
        if (Closes != 0) { throw new ObjectDisposedException("stale selected socket"); }
        sender = Sender;
        return new byte[54];
    }
    public void Close() { Closes++; }
}
'@

$names = @('Get-SocketFailure', 'Get-EndpointText', 'New-GatewaySocket',
           'Set-GatewayRetry', 'Send-GatewayPacket', 'Update-GatewaySocket')
$tested = 0
foreach ($filename in @('office-relay.ps1')) {
    $path = Join-Path $RelayDirectory $filename
    $tokens = $null; $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref] $tokens, [ref] $parseErrors)
    if ($parseErrors.Count) { throw "PowerShell parse failure in ${filename}: $parseErrors" }
    foreach ($name in $names) {
        $definition = @($ast.FindAll({ param($node)
            $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
        }, $true))
        Assert-Equal $definition.Count 1 "Exactly one $name definition"
        . ([scriptblock]::Create($definition[0].Extent.Text))
    }
    $dispatch = @($ast.FindAll({ param($node)
        $node -is [Management.Automation.Language.ForEachStatementAst] -and
        $node.Variable.VariablePath.UserPath -eq 'socket'
    }, $true))
    Assert-Equal $dispatch.Count 1 'Find actual relay socket dispatch loop'
    $dispatchCode = [scriptblock]::Create($dispatch[0].Extent.Text)
    $script:events = [Collections.Generic.List[string]]::new()
    function Write-RelayEvent([string] $eventName, [string] $details) {
        $script:events.Add("$eventName $details")
    }
    # The only real socket operation in this harness is UDP Connect to loopback,
    # without Send; verify factory keeps the requested fixed endpoint.
    $gatewayIp = [Net.IPAddress]::Loopback; $gatewayPort = 51994
    $realCandidate = New-GatewaySocket
    try {
        Assert-Equal $realCandidate.Client.RemoteEndPoint.ToString() '127.0.0.1:51994' 'Fixed endpoint retained'
        Assert-Equal $realCandidate.Client.ReceiveTimeout 1000 'Receive timeout retained'
        Assert-Equal $realCandidate.Client.SendTimeout 1000 'Send timeout retained'
    }
    finally { $realCandidate.Close() }

    $script:factoryCalls = 0; $script:factoryFailure = 0
    $script:replacement = [RelayTestUdp]::new()
    function New-GatewaySocket {
        $script:factoryCalls++
        if ($script:factoryFailure) { throw [Net.Sockets.SocketException]::new($script:factoryFailure) }
        return $script:replacement
    }
    $old = [RelayTestUdp]::new(); $old.SendFailure = 10022
    $gatewayState = New-TestState $old
    $packet = [byte[]]::new(54)
    Assert-Equal (Send-GatewayPacket $gatewayState $packet 0.0) $false '10022 drops failed packet'
    Assert-Equal $old.Closes 1 'Old upstream closed once'
    Assert-Equal $gatewayState.Socket $null 'No stale upstream retained'
    Assert-Equal $gatewayState.DroppedPackets 1 'Failed packet counted'
    Assert-Equal $gatewayState.Recoveries 1 'Recovery counted'
    Assert-Equal $gatewayState.RetryAt 2.0 'Initial two-second backoff'
    Assert-Equal (Send-GatewayPacket $gatewayState $packet 1.0) $false 'Packets during recovery dropped'
    Assert-Equal $gatewayState.DroppedPackets 2 'Waiting packet counted'
    Update-GatewaySocket $gatewayState 1.0
    Assert-Equal $script:factoryCalls 0 'No retry before deadline'
    $script:factoryFailure = 10051
    Update-GatewaySocket $gatewayState 2.0
    Assert-Equal $gatewayState.RetryAt 6.0 'Failed connect backs off four seconds'
    $script:factoryFailure = 10049
    Update-GatewaySocket $gatewayState 6.0
    Assert-Equal $gatewayState.RetryAt 14.0 'Failed connect backs off eight seconds'
    $script:factoryFailure = 10022
    Update-GatewaySocket $gatewayState 14.0
    Assert-Equal $gatewayState.RetryAt 24.0 'Backoff capped at ten seconds'
    $script:factoryFailure = 0
    Update-GatewaySocket $gatewayState 24.0
    Assert-Equal $gatewayState.Socket $script:replacement 'Fresh socket installed'
    Assert-Equal $gatewayState.Reconnects 1 'Only successful replacement counted'
    Assert-Equal $gatewayState.RetryDelay 10.0 'UDP Connect alone does not reset backoff'
    $script:replacement.SendFailure = 10022
    Assert-Equal (Send-GatewayPacket $gatewayState $packet 25.0) $false 'New socket 10022 still recoverable'
    Assert-Equal $gatewayState.RetryAt 35.0 'Repeated bad sockets retain capped backoff'
    $script:replacement = [RelayTestUdp]::new()
    Update-GatewaySocket $gatewayState 35.0
    Assert-Equal (Send-GatewayPacket $gatewayState $packet 36.0) $true 'Later packet forwarded'
    Assert-Equal $gatewayState.RetryDelay 2.0 'Successful Send resets backoff'
    Assert-Equal $script:replacement.Sends 1 'Failed packet was not replayed'
    Assert-Equal (@($script:events | Where-Object { $_ -like 'GATEWAY_RECOVERING *native_code=10022*' }).Count) 2 'Recovery diagnostics include native code'

    $bad = [RelayTestUdp]::new(); $bad.SendFailure = 10013
    $badState = New-TestState $bad
    Assert-Throws { Send-GatewayPacket $badState $packet 0.0 } 'Unrelated Send failures must remain fatal'
    Assert-Equal $badState.Recoveries 0 'Unrelated error not hidden as recovery'
    $badState.Socket = $null; $script:factoryFailure = 10013
    Assert-Throws { Update-GatewaySocket $badState 0.0 } 'Unrelated Connect failures must remain fatal'
    $script:factoryFailure = 0

    # Execute the actual dispatcher with both listener and old upstream selected.
    # The listener's packet closes the bad upstream; its stale entry must be skipped.
    $listener = [RelayTestUdp]::new()
    $old = [RelayTestUdp]::new(); $old.SendFailure = 10022
    $gatewayState = New-TestState $old
    $RunUntilStopped = $true; $MaxMinutes = 480
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $macIp = [Net.IPAddress]::Parse('127.0.0.2')
    $latestMac = $null; $sentPackets = 0L; $sentBytes = 0L
    $replyPackets = 0L; $replyBytes = 0L; $rejectedPackets = 0L
    $macReceiveResets = 0L; $gatewayReceiveResets = 0L
    $ready = @($listener.Client, $old.Client)
    . $dispatchCode
    Assert-Equal $listener.Closes 0 'Recovery keeps Mac listener alive'
    Assert-Equal $old.Receives 0 'Stale Select entry never receives'
    Assert-Equal $sentPackets 0 'Failed Send not counted as forwarded'
    Assert-Equal $gatewayState.DroppedPackets 1 'Dispatcher records dropped handshake'
    Assert-Equal $latestMac.ToString() '127.0.0.2:51000' 'Accepted Mac reply address preserved'

    $listener.Sender = [Net.IPEndPoint]::new([Net.IPAddress]::Parse('192.0.2.99'), 51001)
    $fresh = [RelayTestUdp]::new(); $gatewayState = New-TestState $fresh
    $ready = @($listener.Client)
    . $dispatchCode
    Assert-Equal $rejectedPackets 1 'Non-Mac sender rejected'
    Assert-Equal $fresh.Sends 0 'Rejected sender never forwarded'
    Assert-Equal $latestMac.ToString() '127.0.0.2:51000' 'Rejected sender cannot replace return destination'

    # After replacement, only replies from the configured gateway can return
    # to the latest accepted Mac endpoint; no old sender or arbitrary source wins.
    $fresh.Sender = [Net.IPEndPoint]::new([Net.IPAddress]::Parse('127.0.0.3'), $gatewayPort)
    $ready = @($fresh.Client)
    . $dispatchCode
    Assert-Equal $rejectedPackets 2 'Wrong gateway address rejected after recovery'
    Assert-Equal $listener.Sends 0 'Wrong gateway reply never reaches Mac'
    $fresh.Sender = [Net.IPEndPoint]::new($gatewayIp, $gatewayPort + 1)
    . $dispatchCode
    Assert-Equal $rejectedPackets 3 'Wrong gateway port rejected after recovery'
    Assert-Equal $listener.Sends 0 'Wrong gateway port never reaches Mac'
    $fresh.Sender = [Net.IPEndPoint]::new($gatewayIp, $gatewayPort)
    . $dispatchCode
    Assert-Equal $listener.Sends 1 'Fixed gateway reply reaches Mac after recovery'
    Assert-Equal $listener.LastDestination.ToString() '127.0.0.2:51000' 'Reply returns only to latest accepted Mac port'
    Assert-Equal $replyPackets 1 'Successful reply counted'
    Assert-Equal $replyBytes 54 'Successful reply bytes counted'
    $timer.Stop()
    Write-Host "PASS $filename gateway recovery, backoff, fatal errors, stale selection, sender filters, return path"
    $tested++
}
Write-Host "PASS $tested relay scripts. No production relay started, no settings changed, no packets sent."
