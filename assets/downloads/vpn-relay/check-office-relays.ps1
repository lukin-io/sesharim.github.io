#requires -Version 5.1
# Parse/validate the configured environments and run read-only Plan for each.
[CmdletBinding()]
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'relay-config.json'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'relay-config.ps1')
$profiles = Get-RelayConfig $ConfigPath
$failed = $false
foreach ($name in @('DEV', 'LIVE')) {
    if (-not $profiles.ContainsKey($name)) { Write-Host "$name is not configured; skipping."; continue }
    try {
        & (Join-Path $PSScriptRoot 'office-relay.ps1') -Environment $name -ConfigPath $ConfigPath -Action Plan -RunUntilStopped
        Write-Host "$name Plan completed. Inspect readiness and port findings above."
    }
    catch { Write-Error -ErrorRecord $_ -ErrorAction Continue; $failed = $true }
}
if ($failed) { exit 1 }
exit 0
