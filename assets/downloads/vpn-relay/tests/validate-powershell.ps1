#requires -Version 5.1
# Isolated parser/configuration/error-scope tests. No Tailscale or firewall calls.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$kit = Split-Path -Parent $PSScriptRoot

function Assert($Condition, [string] $Description) {
    if (-not $Condition) { throw "FAIL: $Description" }
    Write-Host "PASS: $Description"
}
function Assert-Throws([scriptblock] $Operation, [string] $Description) {
    $threw = $false
    try { & $Operation | Out-Null } catch { $threw = $true }
    Assert $threw $Description
}
function Read-Function([string] $File, [string] $Name) {
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($File, [ref]$tokens, [ref]$errors)
    $definitions = @($ast.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $Name
    }, $true))
    if ($definitions.Count -ne 1) { throw "Cannot isolate function $Name for its test." }
    return [scriptblock]::Create($definitions[0].Extent.Text)
}
foreach ($file in Get-ChildItem -LiteralPath $kit -Filter '*.ps1' -Recurse -File) {
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    Assert (@($errors).Count -eq 0) ("PowerShell parser: " + $file.Name)
}
. (Join-Path $kit 'relay-config.ps1')
Assert-Throws { Get-RelayConfig (Join-Path $kit 'relay-config.example.json') } 'Unedited example refuses use'
$testDir = Join-Path $PSScriptRoot ('.tmp-powershell-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $testDir)
$configPath = Join-Path $testDir 'relay-config.json'
function New-TestConfig {
    $config = Get-Content -LiteralPath (Join-Path $kit 'relay-config.example.json') -Raw | ConvertFrom-Json
    $config.configured = $true
    # Parser fixtures only: no packets are ever sent to these addresses.
    $config.office_tailscale_ip = '100.100.100.10'
    $config.mac_tailscale_ip = '100.100.100.11'
    $config.profiles.DEV.gateway_ip = '1.1.1.1'
    $config.profiles.LIVE.gateway_ip = '8.8.8.8'
    return $config
}
function Save-TestConfig($Config) {
    $Config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding UTF8
}
try {
    $config = New-TestConfig
    Save-TestConfig $config
    $profiles = Get-RelayConfig $configPath
    Assert ($profiles.Count -eq 2) 'Both configured environments accepted'
    $config.profiles.PSObject.Properties.Remove('LIVE')
    Save-TestConfig $config
    $profiles = Get-RelayConfig $configPath
    Assert ($profiles.Count -eq 1 -and $profiles.ContainsKey('DEV')) 'DEV-only configuration accepted'
    Assert-Throws { Select-RelayProfile $profiles 'LIVE' } 'Missing LIVE fails clearly'
    Assert-Throws {
        & (Join-Path $kit 'office-relay.ps1') -Environment DEV -ConfigPath $configPath -Action Plan -RunUntilStopped -MaxMinutes 1
    } 'Until-stopped and explicit duration are mutually exclusive before any Tailscale call'
    foreach ($bad in @('192.0.2.10', '10.0.0.1', '127.0.0.1', '224.0.0.1')) {
        $config.profiles.DEV.gateway_ip = $bad
        Save-TestConfig $config
        Assert-Throws { Get-RelayConfig $configPath } "Non-public/documentation gateway rejected: $bad"
    }
    $config = New-TestConfig
    $config.profiles.LIVE.office_port = $config.profiles.DEV.office_port
    Save-TestConfig $config
    Assert-Throws { Get-RelayConfig $configPath } 'Duplicate listener ports rejected'

    . (Read-Function (Join-Path $kit 'office-relay.ps1') 'Get-SocketFailure')
    $reset = [Net.Sockets.SocketException]::new(10054)
    $wrapped = [Exception]::new('fixture wrapper', $reset)
    Assert ((Get-SocketFailure $wrapped).NativeErrorCode -eq 10054) 'Nested socket error retains numeric code'
    Assert ($null -eq (Get-SocketFailure ([ArgumentException]::new('fixture')))) 'Non-socket exception stays non-socket'

    # Isolate comparison functions; never invoke NetSecurity cmdlets or the script's main body.
    . (Read-Function (Join-Path $kit 'office-firewall.ps1') 'Test-SingleValue')
    . (Read-Function (Join-Path $kit 'office-firewall.ps1') 'Assert-OwnedScope')
    $group = 'VPNRelayKit'; $marker = 'fixture marker'; $program = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    $office = '100.100.100.10'; $mac = '100.100.100.11'; $port = 11194
    $fakePorts = [pscustomobject]@{ Protocol = 'UDP'; LocalPort = '11194'; RemotePort = 'Any' }
    $fakeAddresses = [pscustomobject]@{ LocalAddress = $office; RemoteAddress = $mac }
    $fakeApplication = [pscustomobject]@{ Program = $program }
    $fakeInterface = [pscustomobject]@{ InterfaceAlias = 'Tailscale' }
    function Get-NetFirewallPortFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)] $InputObject) process { $fakePorts } }
    function Get-NetFirewallAddressFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)] $InputObject) process { $fakeAddresses } }
    function Get-NetFirewallApplicationFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)] $InputObject) process { $fakeApplication } }
    function Get-NetFirewallInterfaceFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)] $InputObject) process { $fakeInterface } }
    $rule = [pscustomobject]@{ Group = $group; Description = $marker; Direction = 'Inbound'; Action = 'Allow';
                             Enabled = 'True'; Profile = 'Any'; EdgeTraversalPolicy = 'Block' }
    Assert-OwnedScope $rule 'Tailscale'
    Write-Host 'PASS: Exact existing firewall scope accepted'
    $fakeAddresses.RemoteAddress = 'Any'
    Assert-Throws { Assert-OwnedScope $rule 'Tailscale' } 'Broad remote firewall address rejected'
    $fakeAddresses.RemoteAddress = $mac
    $fakePorts.LocalPort = 'Any'
    Assert-Throws { Assert-OwnedScope $rule 'Tailscale' } 'Broad local firewall port rejected'
    $fakePorts.LocalPort = '11194'
    $fakeInterface.InterfaceAlias = 'Any'
    Assert-Throws { Assert-OwnedScope $rule 'Tailscale' } 'Wildcard firewall interface rejected'
}
finally { Remove-Item -LiteralPath $testDir -Recurse -Force }
Write-Host 'All isolated PowerShell checks passed; no Tailscale/firewall/VPN operations were performed.'
