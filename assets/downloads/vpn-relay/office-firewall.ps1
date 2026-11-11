#requires -Version 5.1
# Plan reads only. Add/Remove require an elevated Windows PowerShell window.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Plan', 'Add', 'Remove')][string] $Action = 'Plan',
    [Parameter(Mandatory = $true)][ValidateSet('DEV', 'LIVE')][string] $Environment,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'relay-config.json')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run on native Windows.' }
. (Join-Path $PSScriptRoot 'relay-config.ps1')
$relayProfile = Select-RelayProfile (Get-RelayConfig $ConfigPath) $Environment
$ruleName = "VPNRelay-Kit-$Environment-UDP"
$group = 'VPNRelayKit'
$marker = 'Manual VPN relay kit: exact office IPv4, client IPv4, UDP port and Windows PowerShell executable.'
$program = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$office = $relayProfile.OfficeIp.ToString()
$mac = $relayProfile.MacIp.ToString()
$port = $relayProfile.OfficePort
$rules = @(Get-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -ErrorAction SilentlyContinue)
if ($rules.Count -gt 1) { throw 'Multiple rules have the reserved name; review them manually.' }

function Test-SingleValue($Values, [string] $Expected, [switch] $Address) {
    $items = @($Values)
    if ($items.Count -ne 1) { return $false }
    $actual = [string]$items[0]
    if ($Address) { $actual = $actual -replace '/32$', '' }
    return $actual -ieq $Expected
}

function Assert-OwnedScope($Rule, [string] $ExpectedInterface) {
    $portFilter = $Rule | Get-NetFirewallPortFilter -ErrorAction Stop
    $addressFilter = $Rule | Get-NetFirewallAddressFilter -ErrorAction Stop
    $appFilter = $Rule | Get-NetFirewallApplicationFilter -ErrorAction Stop
    $interfaceFilter = $Rule | Get-NetFirewallInterfaceFilter -ErrorAction Stop
    $aliases = @($interfaceFilter.InterfaceAlias)
    $actualProgram = [Environment]::ExpandEnvironmentVariables([string]$appFilter.Program)
    $matches = ($Rule.Group -eq $group -and $Rule.Description -eq $marker -and
        [string]$Rule.Direction -eq 'Inbound' -and [string]$Rule.Action -eq 'Allow' -and
        [string]$Rule.Enabled -eq 'True' -and [string]$Rule.Profile -eq 'Any' -and
        [string]$Rule.EdgeTraversalPolicy -eq 'Block' -and
        [string]$portFilter.Protocol -in @('UDP', '17') -and
        (Test-SingleValue $portFilter.LocalPort ([string]$port)) -and
        (Test-SingleValue $portFilter.RemotePort 'Any') -and
        (Test-SingleValue $addressFilter.LocalAddress $office -Address) -and
        (Test-SingleValue $addressFilter.RemoteAddress $mac -Address) -and
        $actualProgram -ieq $program -and $aliases.Count -eq 1 -and
        [string]$aliases[0] -ne 'Any' -and [string]$aliases[0] -ne '*')
    if ($ExpectedInterface) { $matches = $matches -and (Test-SingleValue $aliases $ExpectedInterface) }
    if (-not $matches) {
        throw 'An existing rule with this name differs from the exact kit scope. Refusing to replace, widen or remove it.'
    }
}

$interface = $null
if ($Action -ne 'Remove') {
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -eq $office -and $_.AddressState -eq 'Preferred' })
    if ($addresses.Count -ne 1) { throw 'Expected office Tailscale IPv4 is not assigned once in Preferred state. Connect Tailscale first.' }
    $adapter = Get-NetAdapter -InterfaceIndex $addresses[0].InterfaceIndex -IncludeHidden -ErrorAction Stop
    if ($adapter.InterfaceDescription -notmatch 'Tailscale') {
        throw 'The configured office IPv4 is not on a recognized Tailscale adapter; review the configuration.'
    }
    $interface = $addresses[0].InterfaceAlias
}
if ($rules.Count -eq 1) { Assert-OwnedScope $rules[0] $interface }
[pscustomobject]@{
    Action = $Action; RuleName = $ruleName; ExistingExactRule = ($rules.Count -eq 1)
    LocalAddress = $office; LocalPort = $port; Protocol = 'UDP'
    RemoteAddress = $mac; RemotePort = 'Any (Mac uses an ephemeral source port)'
    InterfaceAlias = $interface; Program = $program; Profile = 'Any'; EdgeTraversal = 'Block'
}
if ($Action -eq 'Plan') { return }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Add/Remove require an elevated Windows PowerShell window. Plan is read-only.'
}
if ($Action -eq 'Remove') {
    if ($rules.Count -eq 0) { Write-Output 'Rule is already absent.'; return }
    if ($PSCmdlet.ShouldProcess($ruleName, 'Remove this exact kit firewall rule')) {
        Remove-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -ErrorAction Stop
        Write-Output 'Removed the exact kit rule.'
    }
    return
}
if ($rules.Count -eq 1) { Write-Output 'Exact rule already exists; no changes.'; return }
if ($PSCmdlet.ShouldProcess($ruleName, 'Create the displayed narrowly scoped inbound UDP rule')) {
    New-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -DisplayName $ruleName -Group $group `
        -Description $marker -Direction Inbound -Action Allow -Enabled True -Protocol UDP `
        -LocalAddress $office -LocalPort $port -RemoteAddress $mac -InterfaceAlias $interface `
        -Program $program -Profile Any -EdgeTraversalPolicy Block -ErrorAction Stop |
        Select-Object Name, Enabled, Direction, Action
}
