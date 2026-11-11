# Shared read-only configuration validation. Dot-sourcing this file changes no settings.
Set-StrictMode -Version Latest

function Get-RequiredProperty($Object, [string] $Name) {
    if ($null -eq $Object -or $null -eq $Object.PSObject.Properties[$Name]) {
        throw "Configuration is missing '$Name'."
    }
    return $Object.PSObject.Properties[$Name].Value
}

function Convert-RelayIPv4($Value, [string] $Name, [switch] $Tailscale) {
    $address = $null
    if ($Value -isnot [string] -or $Value -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
        -not [Net.IPAddress]::TryParse($Value, [ref]$address) -or
        $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw "$Name must be an IPv4 address; replace the example placeholder."
    }
    if ($address.ToString() -cne $Value) {
        throw "$Name must use canonical dotted-decimal IPv4 notation, without leading zeroes."
    }
    $bytes = $address.GetAddressBytes()
    if ($Tailscale) {
        if ($bytes[0] -ne 100 -or $bytes[1] -lt 64 -or $bytes[1] -gt 127) {
            throw "$Name must be the device's Tailscale IPv4 address (100.64.0.0/10)."
        }
    }
    else {
        # Public unicast IPv4 only; reject private, special-use and documentation ranges.
        $blocked = ($bytes[0] -eq 0 -or $bytes[0] -eq 10 -or $bytes[0] -eq 127 -or $bytes[0] -ge 224 -or
            ($bytes[0] -eq 100 -and $bytes[1] -ge 64 -and $bytes[1] -le 127) -or
            ($bytes[0] -eq 169 -and $bytes[1] -eq 254) -or
            ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
            ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
            ($bytes[0] -eq 192 -and $bytes[1] -eq 0 -and ($bytes[2] -eq 0 -or $bytes[2] -eq 2)) -or
            ($bytes[0] -eq 192 -and $bytes[1] -eq 88 -and $bytes[2] -eq 99) -or
            ($bytes[0] -eq 198 -and ($bytes[1] -eq 18 -or $bytes[1] -eq 19)) -or
            ($bytes[0] -eq 198 -and $bytes[1] -eq 51 -and $bytes[2] -eq 100) -or
            ($bytes[0] -eq 203 -and $bytes[1] -eq 0 -and $bytes[2] -eq 113))
        if ($blocked) { throw "$Name must be the actual public IPv4 of your authorized VPN gateway." }
    }
    return $address
}

function Convert-RelayPort($Value, [string] $Name, [int] $Minimum = 1) {
    if (($Value -isnot [int] -and $Value -isnot [long]) -or $Value -lt $Minimum -or $Value -gt 65535) {
        throw "$Name must be an integer from $Minimum through 65535."
    }
    return [int]$Value
}

function Get-RelayConfig([string] $Path) {
    try { $config = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop }
    catch { throw 'Cannot read relay-config.json. Copy and edit relay-config.example.json first.' }
    $configured = Get-RequiredProperty $config 'configured'
    if ($configured -isnot [bool] -or -not $configured) {
        throw 'Edit all placeholders and gateway IPs, then set configured to true.'
    }
    $office = Convert-RelayIPv4 (Get-RequiredProperty $config 'office_tailscale_ip') 'office_tailscale_ip' -Tailscale
    $mac = Convert-RelayIPv4 (Get-RequiredProperty $config 'mac_tailscale_ip') 'mac_tailscale_ip' -Tailscale
    if ($office.Equals($mac)) { throw 'Office and Mac must have different Tailscale IPv4 addresses.' }
    $profiles = Get-RequiredProperty $config 'profiles'
    $names = @($profiles.PSObject.Properties.Name)
    if ('DEV' -notin $names -or @($names | Where-Object { $_ -cnotin @('DEV', 'LIVE') }).Count) {
        throw 'profiles must contain DEV; LIVE is optional; other names are not supported.'
    }
    $result = @{}
    foreach ($name in @('DEV', 'LIVE')) {
        if ($name -cnotin $names) { continue }
        $relayProfile = Get-RequiredProperty $profiles $name
        $result[$name] = [pscustomobject]@{
            OfficeIp = $office; MacIp = $mac
            GatewayIp = (Convert-RelayIPv4 (Get-RequiredProperty $relayProfile 'gateway_ip') "$name.gateway_ip")
            GatewayPort = (Convert-RelayPort (Get-RequiredProperty $relayProfile 'gateway_port') "$name.gateway_port")
            OfficePort = (Convert-RelayPort (Get-RequiredProperty $relayProfile 'office_port') "$name.office_port" 1024)
            MacPort = (Convert-RelayPort (Get-RequiredProperty $relayProfile 'mac_port') "$name.mac_port" 1024)
        }
    }
    if ($result.ContainsKey('LIVE') -and
        ($result.DEV.OfficePort -eq $result.LIVE.OfficePort -or $result.DEV.MacPort -eq $result.LIVE.MacPort)) {
        throw 'DEV and LIVE must use different office_port and mac_port values.'
    }
    return $result
}

function Select-RelayProfile($Profiles, [string] $Environment) {
    if (-not $Profiles.ContainsKey($Environment)) {
        throw "$Environment is not configured; use DEV or add its profile to relay-config.json."
    }
    return $Profiles[$Environment]
}
