import os

from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException, ReadTimeout

TIMEOUT = 8

def _error(code):
    return {
        "status": "error",
        "result": code,
    }

def _not_found():
    return {
        "status": "ok",
        "result": "not_found",
        "interface": None,
    }

def _auth():
    return (os.environ.get("ROUTER_USER", ""), os.environ.get("ROUTER_PASS", ""))

# netmiko connect
def _connect(router):
    user, password = _auth()
    return ConnectHandler(
        device_type="cisco_ios",
        host=router,
        username=user,
        password=password,
        conn_timeout=TIMEOUT,
        auth_timeout=TIMEOUT,
        banner_timeout=TIMEOUT,
    )

def _read(conn, interface_name):
    """ให้ TextFSM แปลง output ของ show interface เป็น dict"""
    ip_info = conn.send_command(
        f"show ip interface {interface_name}", use_textfsm=True
    )
    descriptions = conn.send_command(
        f"show interfaces description", use_textfsm=True
    )

    if not isinstance(ip_info, list):
        ip_info = []
    if not isinstance(descriptions, list):
        descriptions = []
    return ip_info, descriptions

# ใช้ตอนส่งบอท
def _real_get(router, interface_name):
    with _connect(router) as conn:
        return _read(conn, interface_name)

def _real_delete(router, interface_name):
    with _connect(router) as conn:
        ip_info, descriptions = _read(conn, interface_name)
        if _parse(interface_name, ip_info, descriptions) is None:
            return "not_found"

        conn.send_config_set([f"no interface {interface_name}"])

        ip_info, descriptions = _read(conn, interface_name)
        if _parse(interface_name, ip_info, descriptions) is not None:
            raise RuntimeError("interface still present after delete")
        return "deleted"

def _map_exception(e):
    if isinstance(e, (PermissionError, NetmikoAuthenticationException)):
        return _error("authentication_failed")
    if isinstance(e, (ConnectionError, NetmikoTimeoutException, OSError, ReadTimeout)):
        return _error("connection_failed")
    return _error("backend_failed")

def _lo_name(port):
    if port.startswith("Lo") and not port.startswith("Loopback"):
        return "Loopback" + port[2:]
    return port

def _parse(interface_name, ip_info, descriptions):
    """แปลง TextFSM เป็น dict"""
    for i in ip_info:
        if i.get("interface") != interface_name:
            continue
        ipv4 = None
        if i.get("ip_address") and i.get("prefix_length"):
            ipv4 = f"{i['ip_address'][0]}/{i['prefix_length'][0]}"
        if i.get("link_status") == "administratively down":
            admin_state = "down"
        else:
            admin_state = "up"

        description = None
        for d in descriptions:
            if _lo_name(d.get("port", "")) == interface_name:
                description = d.get("description") or None
                break

        return {
            "name": interface_name,
            "ipv4": ipv4,
            "description": description,
            "admin_state": admin_state,
        }
    return None

def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    netmiko_get = netmiko_get or _real_get
    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
    except Exception as e:
        return _map_exception(e)
    
    try:
        interface = _parse(interface_name, ip_info, descriptions)
        if interface is None:
            return _not_found()
    except Exception:
        return _error("backend_failed")
    return {
        "status": "ok",
        "result": "found",
        "interface": interface,
    }
    


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    netmiko_delete = netmiko_delete or _real_delete
    try:
        status = netmiko_delete(router, interface_name)
    except Exception as e:
        return _map_exception(e)
    
    if status == "not_found":
        return _not_found()
    if status == "deleted":
        return {"status": "ok", "result": "deleted"}
    return _error("backend_failed")
