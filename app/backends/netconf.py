from xml.sax.saxutils import escape
from ipaddress import IPv4Interface
import os

from ncclient.transport import AuthenticationError, SSHError, TransportError
from ncclient.operations.errors import TimeoutExpiredError

from ncclient import manager as manage

import xml.etree.ElementTree as ET

from app.backends import planning

Timeout = 8

NS = {
    "if": "urn:ietf:params:xml:ns:yang:ietf-interfaces",
    "ip": "urn:ietf:params:xml:ns:yang:ietf-ip",
}

def _error(code):
    return {
        "status": "error",
        "result": code,
    }
def _auth():
    return (os.environ.get("ROUTER_USER", ""), os.environ.get("ROUTER_PASS", ""))

def _connect(router):
    user, password = _auth()
    return manage.connect(
        host=router,
        port=830,
        username=user,
        password=password,
        hostkey_verify=False,
        device_params={"name": "iosxe"},
        timeout=Timeout,
        allow_agent=False,
        look_for_keys=False,
    )

# ใช้ตอนส่งบอท
def _real_get_config(router, filter_xml):
    with _connect(router) as m:
        reply = m.get_config(source="running", filter=("subtree", filter_xml))
        return reply.xml
def _real_edit_config(router, config_xml):
    with _connect(router) as m:
        m.edit_config(target="running", config=config_xml)

# แปลง exception เป็น error code
def _map_exception(e):
    if isinstance(e, (PermissionError, AuthenticationError)):
        return _error("authentication_failed")
    if isinstance(e, (ConnectionError, SSHError, TransportError, TimeoutExpiredError, OSError)):
            return _error("connection_failed")
    return _error("backend_failed")

def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    netconf_get_config = netconf_get_config or _real_get_config
    
    filter_xml =f"""
    <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">
        <interface>
            <name>{interface_name}</name>
        </interface>
    </interfaces>"""

    try:
        xml = netconf_get_config(router, filter_xml)
    except Exception as e:
        return _map_exception(e)

    try:
        root = ET.fromstring(xml)

        iface = None
        for item in root.iter(f"{{{NS['if']}}}interface"):
            if item.findtext("if:name", namespaces=NS) == interface_name:
                iface = item
                break

        if iface is None:
            return {
                "status": "ok",
                "result": "not_found",
                "interface": None,
            }

        ipv4 = None
        address = iface.find("ip:ipv4/ip:address", NS)
        if address is not None:
            ip = address.findtext("ip:ip", namespaces=NS)
            netmask = address.findtext("ip:netmask", namespaces=NS)
            ipv4 = str(IPv4Interface(f"{ip}/{netmask}"))

        enabled = iface.findtext("if:enabled", default="true", namespaces=NS)

        interface = {
            "name": iface.findtext("if:name", namespaces=NS),
            "ipv4": ipv4,
            "description": iface.findtext("if:description", namespaces=NS),
            "admin_state": "up" if enabled.strip() == "true" else "down",
        }

    except Exception:
        return _error("backend_failed")

    return {
            "status": "ok",
            "result": "found",
            "interface": interface,
        }

def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    def status(r, name):
        return get_interface_state(r, name, netconf_get_config)
    return planning.plan_interface(router, desired_interface, status)


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    netconf_edit_config = netconf_edit_config or _real_edit_config

    number = int(desired_interface["name"][len("Loopback"):])
    ipv4 = IPv4Interface(desired_interface["ipv4"])
    description = escape(desired_interface["description"])

    shutdown = "<shutdown/>" if desired_interface["admin_state"] == "down" else ""

    config_xml = f"""
    <config
        xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
        xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">

      <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
        <interface>
            <Loopback nc:operation="replace">
                <name>{number}</name>
                <description>{description}</description>
                <ip>
                    <address>
                        <primary>
                            <address>{ipv4.ip}</address>
                            <mask>{ipv4.network.netmask}</mask>
                        </primary>
                    </address>
                </ip>
                {shutdown}
            </Loopback>
        </interface>
      </native>
    </config>"""

    try:
        netconf_edit_config(router, config_xml)
    except Exception as e:
        return _map_exception(e)

    return {
        "status": "ok",
        "result": "applied",
    }
