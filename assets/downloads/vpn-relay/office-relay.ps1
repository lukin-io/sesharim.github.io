#requires -Version 5.1
# Native, single-client UDP relay over the existing authenticated Tailscale path.
# Plan is read-only. Start also disables Tailscale DNS/subnet-route acceptance.
# Start writes scoped per-user diagnostic logs; no credentials/payloads, firewall or service changes.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Plan', 'Start')][string] $Action = 'Plan',
    [Parameter(Mandatory = $true)][ValidateSet('DEV', 'LIVE')][string] $Environment,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'relay-config.json'),
    [ValidateRange(1, 480)][int] $MaxMinutes = 480,
    [switch] $RunUntilStopped
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'relay-config.ps1')
$profiles = Get-RelayConfig $ConfigPath
$relayProfile = Select-RelayProfile $profiles $Environment
$officeIp = $relayProfile.OfficeIp
$macIp = $relayProfile.MacIp
$gatewayIp = $relayProfile.GatewayIp
$listenPort = $relayProfile.OfficePort
$gatewayPort = $relayProfile.GatewayPort
$tailscaleExe = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
if ($env:OS -ne 'Windows_NT') { throw 'Run on native Windows.' }
$relayName = $Environment
$script:relayLogPath = $null
$listener = $null; $upstream = $null; $latestMac = $null; $timer = $null
$sentPackets = 0L; $sentBytes = 0L
$replyPackets = 0L; $replyBytes = 0L; $rejectedPackets = 0L
$macReceiveResets = 0L; $gatewayReceiveResets = 0L
$stage = 'preflight'; $stopReason = 'startup_failure'; $packetBytes = -1
$limitMode = if ($RunUntilStopped) { 'until_stopped' } else { 'bounded' }
$limitText = if ($RunUntilStopped) { 'until explicitly stopped' } else { "$MaxMinutes minutes" }
if ($RunUntilStopped -and $PSBoundParameters.ContainsKey('MaxMinutes')) {
    throw 'Choose -RunUntilStopped OR an explicit -MaxMinutes, not both.'
}
function Write-RelayEvent([string] $eventName, [string] $details) {
    $line = "$([DateTime]::UtcNow.ToString('o')) $relayName PID=$PID $eventName $details"
    Write-Host $line
    if ($null -ne $script:relayLogPath) {
        try { [IO.File]::AppendAllText($script:relayLogPath, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false)) }
        catch {
            $script:relayLogPath = $null
            Write-Warning 'Diagnostic file write failed; continuing with console diagnostics only.'
        }
    }
}
function Invoke-TsCommand([string] $arguments, [int] $timeoutMs = 5000) {
    $process = [Diagnostics.Process]::new()
    try {
        $process.StartInfo.FileName = $tailscaleExe
        $process.StartInfo.Arguments = $arguments
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        if (-not $process.Start()) { throw 'Could not start the Tailscale CLI.' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($timeoutMs)) {
            $process.Kill()
            [void] $process.WaitForExit(1000)
            throw 'Tailscale CLI exceeded its bounded response timeout.'
        }
        # Never print/store raw CLI output: status JSON may contain account information.
        return [pscustomobject]@{ ExitCode = $process.ExitCode; Output = $stdout.Result }
    }
    finally { $process.Dispose() }
}
function Get-TsSetting([string] $name) {
    $result = Invoke-TsCommand "get $name"
    if ($result.ExitCode -ne 0) { throw "Could not read Tailscale setting $name (exit $($result.ExitCode))." }
    return $result.Output.Trim()
}
function Get-Readiness([int] $timeoutMs = 5000) {
    $service = Get-Service -Name 'Tailscale' -ErrorAction SilentlyContinue
    $serviceState = if ($null -eq $service) { 'not_found' } else { $service.Status.ToString() }
    # Query then filter: a missing expected address is a diagnosable state, not ObjectNotFound.
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop)
    $expected = @($addresses | Where-Object { $_.IPAddress -eq $officeIp.ToString() })
    $states = @($expected | ForEach-Object { $_.AddressState.ToString() })
    $windowsIps = @($addresses | Where-Object { $_.InterfaceAlias -like '*Tailscale*' } | ForEach-Object { $_.IPAddress })
    $backend = 'unavailable'; $reportedIps = @()
    try {
        $result = Invoke-TsCommand 'status --json' $timeoutMs
        if ($result.ExitCode -eq 0) {
            $status = $result.Output | ConvertFrom-Json -ErrorAction Stop
            $backendProperty = $status.PSObject.Properties['BackendState']
            if ($null -ne $backendProperty -and [string]$backendProperty.Value -match '^[A-Za-z]+$') {
                $backend = [string]$backendProperty.Value
            }
            $ipProperty = $status.PSObject.Properties['TailscaleIPs']
            if ($null -ne $ipProperty) {
                foreach ($value in $ipProperty.Value) {
                    $parsedIp = $null
                    if ([Net.IPAddress]::TryParse([string]$value, [ref]$parsedIp) -and
                        $parsedIp.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
                        $reportedIps += $parsedIp.ToString()
                    }
                }
            }
        }
        else { $backend = "cli_exit_$($result.ExitCode)" }
    }
    catch { $backend = 'cli_unavailable_or_invalid_response' }
    return [pscustomobject]@{
        Service = $serviceState; Backend = $backend; ExpectedCount = $expected.Count
        AddressStates = ($states -join ','); WindowsIps = ($windowsIps -join ',')
        ReportedIps = ($reportedIps -join ',')
        Ready = ($expected.Count -eq 1 -and $states[0] -eq 'Preferred' -and
                 $backend -eq 'Running' -and $serviceState -eq 'Running')
    }
}
function Show-Readiness($snapshot, [int] $waitedSeconds) {
    Write-RelayEvent 'READINESS' "waited_s=$waitedSeconds expected_ip=$officeIp assigned_count=$($snapshot.ExpectedCount) address_state=$($snapshot.AddressStates) service=$($snapshot.Service) backend=$($snapshot.Backend) windows_tailscale_ipv4=$($snapshot.WindowsIps) reported_ipv4=$($snapshot.ReportedIps)"
}
function Get-SocketFailure([Exception] $failure) {
    while ($null -ne $failure -and -not ($failure -is [Net.Sockets.SocketException])) {
        $failure = $failure.InnerException
    }
    return $failure
}
function Get-EndpointText($udp, [string] $property) {
    try {
        if ($null -ne $udp -and $null -ne $udp.Client) {
            $endpoint = $udp.Client.$property
            if ($null -ne $endpoint) { return $endpoint.ToString() }
        }
    }
    catch { }
    return 'unavailable'
}
if ($Action -eq 'Start') {
    if (-not $PSCmdlet.ShouldProcess("${officeIp}:${listenPort} -> ${gatewayIp}:${gatewayPort}", "Write local diagnostics; wait for Tailscale; disable DNS/subnet-route acceptance; run relay $limitText")) { return }
    try {
        $logDir = Join-Path $env:LOCALAPPDATA 'VPNRelay\logs'
        [void] (New-Item -ItemType Directory -Path $logDir -Force -ErrorAction Stop)
        $logPath = Join-Path $logDir ("{0}-{1}-{2}.log" -f $relayName.ToLower(), [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'), $PID)
        [void] (New-Item -ItemType File -Path $logPath -ErrorAction Stop)
        $script:relayLogPath = $logPath
    }
    catch { Write-Warning 'Could not create diagnostic file; console diagnostics remain enabled.' }
}
try {
    Write-RelayEvent 'PREFLIGHT' "action=$Action duration_mode=$limitMode limit=$limitText log=$script:relayLogPath"
    $stage = 'preflight_readiness'
    $waitClock = [Diagnostics.Stopwatch]::StartNew()
    $snapshot = Get-Readiness
    Show-Readiness $snapshot 0
    if ($Action -eq 'Start') {
        while (-not $snapshot.Ready -and $waitClock.Elapsed.TotalSeconds -lt 30) {
            if ($snapshot.Backend -eq 'NeedsLogin' -or $snapshot.Backend -eq 'NeedsMachineAuth') { break }
            $remainingMs = [int][Math]::Max(0, 30000 - $waitClock.Elapsed.TotalMilliseconds)
            if ($remainingMs -le 0) { break }
            Start-Sleep -Milliseconds ([Math]::Min(2000, $remainingMs))
            $remainingMs = [int][Math]::Max(0, 30000 - $waitClock.Elapsed.TotalMilliseconds)
            if ($remainingMs -le 0) { break }
            $snapshot = Get-Readiness ([Math]::Min(5000, $remainingMs))
            Show-Readiness $snapshot ([int]$waitClock.Elapsed.TotalSeconds)
        }
        if (-not $snapshot.Ready) {
            Write-RelayEvent 'NOT_READY' "Expected office IP $officeIp must be assigned once in Preferred state, with Tailscale service/backend Running. Check Tailscale on this Windows host; no listener or preference change was made."
            throw 'Office Tailscale interface is not ready; see timestamped READINESS diagnostics.'
        }
    }
    $waitClock.Stop()
    $stage = 'preflight_settings'
    $dnsBefore = Get-TsSetting 'accept-dns'
    $routesBefore = Get-TsSetting 'accept-routes'
    $exitNode = Get-TsSetting 'exit-node'
    $stage = 'preflight_port'
    $occupied = @(Get-NetUDPEndpoint -LocalPort $listenPort -ErrorAction SilentlyContinue)
    [pscustomobject]@{
        Action = $Action; Listener = "${officeIp}:${listenPort}/UDP"
        AllowedClient = "$macIp (latest accepted source port)"
        OnlyDestination = "${gatewayIp}:${gatewayPort}/UDP"
        DurationMode = $limitMode
        MaximumMinutes = $(if ($RunUntilStopped) { $null } else { $MaxMinutes })
        FirewallChanges = 'None'; TailscaleAcceptDns = $dnsBefore
        TailscaleAcceptRoutes = $routesBefore; ExitNodeSelected = [bool]$exitNode
        ExistingUdpListener = $occupied.Count
        FirewallProgramIfNeeded = (Get-Process -Id $PID).Path
    }
    foreach ($binding in $occupied) {
        Write-RelayEvent 'PORT_OCCUPIED' "address=$($binding.LocalAddress) port=$($binding.LocalPort) owner_pid=$($binding.OwningProcess)"
    }
    if ($Action -eq 'Plan') { return }
    if ($exitNode) { throw 'An exit node is selected; no listener or preference change was made.' }
    if ($occupied.Count -gt 0) { throw "UDP$listenPort is occupied; no listener or preference change was made." }
    $stage = 'tailscale_preferences'
    $setResult = Invoke-TsCommand 'set --accept-dns=false --accept-routes=false'
    if ($setResult.ExitCode -ne 0) { throw "Tailscale preference update failed (exit $($setResult.ExitCode)); no relay started." }
    Write-RelayEvent 'PREFERENCES' "accept_dns=false accept_routes=false previous_dns=$dnsBefore previous_routes=$routesBefore; these preferences remain false after cleanup"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $nextReport = 30
    $stage = 'mac_bind'
    $listener = [Net.Sockets.UdpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
    $listener.Client.ExclusiveAddressUse = $true
    $listener.Client.ReceiveTimeout = 1000
    $listener.Client.SendTimeout = 1000
    $listener.Client.Bind([Net.IPEndPoint]::new($officeIp, $listenPort))
    $stage = 'gateway_connect'
    $upstream = [Net.Sockets.UdpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
    $upstream.Client.ReceiveTimeout = 1000
    $upstream.Client.SendTimeout = 1000
    # Connected UDP accepts/sends only the fixed gateway endpoint.
    $upstream.Connect($gatewayIp, $gatewayPort)
    $stopReason = 'interrupted_or_stopped'
    Write-RelayEvent 'LISTENING' "listener=${officeIp}:${listenPort} gateway=${gatewayIp}:${gatewayPort} duration_mode=$limitMode limit=$limitText; Ctrl+C stops"
    while ($RunUntilStopped -or $timer.Elapsed.TotalMinutes -lt $MaxMinutes) {
        $ready = New-Object System.Collections.ArrayList
        [void] $ready.Add($listener.Client)
        [void] $ready.Add($upstream.Client)
        # Select waits up to one second (microseconds), avoiding an idle busy loop.
        $stage = 'select'
        [Net.Sockets.Socket]::Select($ready, $null, $null, 1000000)
        foreach ($socket in $ready) {
            if (-not $RunUntilStopped -and $timer.Elapsed.TotalMinutes -ge $MaxMinutes) { break }
            $stage = 'prepare'; $packetBytes = -1
            try {
                $sender = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
                if ([object]::ReferenceEquals($socket, $listener.Client)) {
                    $stage = 'mac_receive'
                    [byte[]] $packet = $listener.Receive([ref] $sender)
                    if (-not $sender.Address.Equals($macIp) -or $sender.Port -le 0) {
                        $rejectedPackets++
                        continue
                    }
                    $latestMac = [Net.IPEndPoint]::new($macIp, $sender.Port)
                    $packetBytes = $packet.Length
                    $stage = 'gateway_send'
                    [void] $upstream.Send($packet, $packet.Length)
                    $sentPackets++; $sentBytes += $packet.Length
                }
                else {
                    $stage = 'gateway_receive'
                    [byte[]] $packet = $upstream.Receive([ref] $sender)
                    if (-not $sender.Address.Equals($gatewayIp) -or $sender.Port -ne $gatewayPort) {
                        $rejectedPackets++
                        continue
                    }
                    if ($null -ne $latestMac) {
                        $packetBytes = $packet.Length
                        $stage = 'mac_send'
                        [void] $listener.Send($packet, $packet.Length, $latestMac)
                        $replyPackets++; $replyBytes += $packet.Length
                    }
                }
            }
            catch {
                # PowerShell method calls can wrap SocketException in InnerException.
                $socketFailure = $_.Exception
                while ($null -ne $socketFailure -and -not ($socketFailure -is [Net.Sockets.SocketException])) {
                    $socketFailure = $socketFailure.InnerException
                }
                if (($stage -eq 'mac_receive' -or $stage -eq 'gateway_receive') -and
                    $null -ne $socketFailure -and
                    $socketFailure.SocketErrorCode -eq [Net.Sockets.SocketError]::ConnectionReset -and
                    $socketFailure.NativeErrorCode -eq 10054) {
                    if ($stage -eq 'mac_receive') {
                        $macReceiveResets++
                        $firstReset = ($macReceiveResets -eq 1)
                    }
                    else {
                        $gatewayReceiveResets++
                        $firstReset = ($gatewayReceiveResets -eq 1)
                    }
                    if ($firstReset) {
                        Write-RelayEvent 'UDP_RECEIVE_RESET' "stage=$stage socket_error=ConnectionReset native_code=10054; continuing"
                    }
                    continue
                }
                throw
            }
        }
        if ($timer.Elapsed.TotalSeconds -ge $nextReport) {
            Write-RelayEvent 'COUNTERS' "GatewayOut=$sentPackets/$sentBytes bytes; MacReplies=$replyPackets/$replyBytes bytes; Rejected=$rejectedPackets; MacReceiveResets=$macReceiveResets; GatewayReceiveResets=$gatewayReceiveResets"
            $nextReport += 30
        }
    }
    $stopReason = 'time_limit'
    Write-RelayEvent 'TIME_LIMIT_REACHED' "limit_minutes=$MaxMinutes elapsed_s=$([Math]::Round($timer.Elapsed.TotalSeconds, 1))"
}
catch {
    $stopReason = 'error'
    $socketFailure = Get-SocketFailure $_.Exception
    $errorType = $_.Exception.GetType().Name
    $socketCode = 'none'; $nativeCode = 'none'
    if ($null -ne $socketFailure) {
        $socketCode = $socketFailure.SocketErrorCode.ToString()
        $nativeCode = $socketFailure.NativeErrorCode
    }
    $side = 'preflight_or_control'; $failedUdp = $null
    if ($stage -like 'mac_*') { $side = 'mac'; $failedUdp = $listener }
    if ($stage -like 'gateway_*') { $side = 'gateway'; $failedUdp = $upstream }
    $localEndpoint = Get-EndpointText $failedUdp 'LocalEndPoint'
    $remoteEndpoint = Get-EndpointText $failedUdp 'RemoteEndPoint'
    Write-RelayEvent 'FATAL' "stage=$stage side=$side exception_type=$errorType socket_error=$socketCode native_code=$nativeCode packet_bytes=$packetBytes local_endpoint=$localEndpoint remote_endpoint=$remoteEndpoint"
    throw
}
finally {
    # No child listener process exists: process termination also closes both sockets.
    if ($null -ne $listener) { $listener.Close() }
    if ($null -ne $upstream) { $upstream.Close() }
    $elapsed = 0
    if ($null -ne $timer) { $timer.Stop(); $elapsed = [Math]::Round($timer.Elapsed.TotalSeconds, 1) }
    if ($Action -eq 'Start') {
        Write-RelayEvent 'STOPPED' "reason=$stopReason stage=$stage elapsed_s=$elapsed duration_mode=$limitMode GatewayOut=$sentPackets/$sentBytes bytes; MacReplies=$replyPackets/$replyBytes bytes; Rejected=$rejectedPackets; MacReceiveResets=$macReceiveResets; GatewayReceiveResets=$gatewayReceiveResets"
    }
}
