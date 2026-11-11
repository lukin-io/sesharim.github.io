"""Validate the public relay kit's explicit, fixed IPv4 destinations."""

from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path


TAILSCALE_RANGE = ipaddress.ip_network("100.64.0.0/10")
DOCUMENTATION_RANGES = tuple(ipaddress.ip_network(value) for value in
                             ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))


@dataclass(frozen=True)
class RelaySettings:
    environment: str
    office_tailscale_ip: str
    mac_tailscale_ip: str
    gateway_ip: str
    gateway_port: int
    office_port: int
    mac_port: int


def _ip(value, name, tailscale=False):
    if not isinstance(value, str):
        raise ValueError(f"{name}: expected an IPv4 address string")
    try:
        address = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, TypeError):
        raise ValueError(f"{name}: replace the placeholder with an IPv4 address") from None
    if tailscale:
        if address not in TAILSCALE_RANGE:
            raise ValueError(f"{name}: expected the device's Tailscale IPv4 (100.64.0.0/10)")
    elif (not address.is_global or address.is_multicast or
          address in ipaddress.ip_network("192.0.0.0/24") or
          address in ipaddress.ip_network("192.88.99.0/24") or
          any(address in network for network in DOCUMENTATION_RANGES)):
        raise ValueError(f"{name}: use the actual public IPv4 of your authorized VPN gateway")
    return str(address)


def _port(value, name, minimum=1):
    if type(value) is not int or not minimum <= value <= 65535:
        raise ValueError(f"{name}: expected an integer from {minimum} through 65535")
    return value


def load_config(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read relay config: {type(error).__name__}. Copy/edit relay-config.example.json first") from None
    if not isinstance(data, dict) or data.get("configured") is not True:
        raise ValueError("Edit all placeholders and gateway IPs, then set configured to true")
    office = _ip(data.get("office_tailscale_ip"), "office_tailscale_ip", True)
    mac = _ip(data.get("mac_tailscale_ip"), "mac_tailscale_ip", True)
    if office == mac:
        raise ValueError("Office and Mac must have different Tailscale IPv4 addresses")
    profiles = data.get("profiles")
    if (not isinstance(profiles, dict) or "DEV" not in profiles or
            not set(profiles).issubset({"DEV", "LIVE"})):
        raise ValueError("profiles must contain DEV; LIVE is optional; other names are not supported")
    result = {}
    for name in ("DEV", "LIVE"):
        if name not in profiles:
            continue
        profile = profiles[name]
        if not isinstance(profile, dict):
            raise ValueError(f"{name}: expected an object")
        result[name] = RelaySettings(
            name, office, mac,
            _ip(profile.get("gateway_ip"), f"{name}.gateway_ip"),
            _port(profile.get("gateway_port"), f"{name}.gateway_port"),
            _port(profile.get("office_port"), f"{name}.office_port", 1024),
            _port(profile.get("mac_port"), f"{name}.mac_port", 1024),
        )
    for field in ("office_port", "mac_port"):
        if "LIVE" in result and getattr(result["DEV"], field) == getattr(result["LIVE"], field):
            raise ValueError(f"DEV and LIVE must use different {field} values")
    return result


def select_profile(profiles, environment):
    if environment not in profiles:
        raise ValueError(f"{environment} is not configured; use DEV or add its profile to relay-config.json")
    return profiles[environment]


def snapshot_config(profiles):
    """Only validated connection fields are copied to the private runtime directory."""
    first = profiles["DEV"]
    return json.dumps({
        "configured": True,
        "office_tailscale_ip": first.office_tailscale_ip,
        "mac_tailscale_ip": first.mac_tailscale_ip,
        "profiles": {name: {key: getattr(value, key) for key in
                            ("gateway_ip", "gateway_port", "office_port", "mac_port")}
                     for name, value in profiles.items()},
    }, indent=2).encode()
