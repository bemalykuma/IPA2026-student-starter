import os
from ipaddress import IPv4Interface

import requests

from app.backends import planning


HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}
TIMEOUT = 8

def _error(code):
    return {
        "status": "error",
        "result": code,
    }

def _auth():
    return (os.environ.get("ROUTER_USER", ""), os.environ.get("ROUTER_PASS", ""))

# ใช้ตอนส่งบอท
def _real_get(url):
    return requests.get(url, auth=_auth(), headers=HEADERS, verify=False, timeout=TIMEOUT,)
def _real_put(url, json):
    return requests.put(url, json=json, auth=_auth(), headers=HEADERS, verify=False, timeout=TIMEOUT)

# แปลง exception เป็น error code
def _map_exception(e):
    if isinstance(e, PermissionError):
        return _error("authentication_failed")
    if isinstance(e, (ConnectionError, requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return _error("connection_failed")
    return _error("backend_failed")

def _map_http_error(status_code):
    if status_code in (401, 403):
        return _error("authentication_failed")
    return _error("backend_failed")

def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    http_get = http_get or _real_get
    url = f"https://{router}/restconf/data/ietf-interfaces:interfaces/interface={interface_name}"

    try:
        response = http_get(url)
    except Exception as e:
        return _map_exception(e)

    if response.status_code == 404:
        return {
            "status": "ok",
            "result": "not_found",
            "interface": None,
        }

    if response.status_code != 200:
        return _map_http_error(response.status_code)

    try:
        raw = response.json()["ietf-interfaces:interface"]
        addresses = raw.get("ietf-ip:ipv4", {}).get("address", [])
        ipv4 = None
        if addresses:
            first = addresses[0]
            ipv4 = str(IPv4Interface(f"{first['ip']}/{first['netmask']}"))
        interface = {
            "name": raw["name"],
            "ipv4": ipv4,
            "description": raw.get("description"),
            "admin_state": "up" if raw.get("enabled", True) else "down",
        }
    except Exception as e:
        return _error("backend_failed")

    return {
        "status": "ok",
        "result": "found",
        "interface": interface,
    }

def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    def status(r, name):
        return get_interface_state(r, name, http_get)
    return planning.plan_interface(router, desired_interface, status)


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    http_put = http_put or _real_put

    number = int(desired_interface["name"][len("Loopback"):])
    ipv4 = IPv4Interface(desired_interface["ipv4"])

    loopback = {
        "name": number,
        "description": desired_interface["description"],
        "ip": {
            "address": {
                "primary": {
                    "address": str(ipv4.ip),
                    "mask": str(ipv4.network.netmask),
                }
            }
        },
    }
    if desired_interface["admin_state"] == "down":
        loopback["shutdown"] = [None]

    url = (f"https://{router}/restconf/data/"
           f"Cisco-IOS-XE-native:native/interface/Loopback={number}")

    try:
        response = http_put(url, json={"Cisco-IOS-XE-native:Loopback": loopback})
    except Exception as e:
        return _map_exception(e)

    if response.status_code in (200, 201, 204):
        return {
            "status": "ok",
            "result": "applied",
        }
    return _map_http_error(response.status_code)