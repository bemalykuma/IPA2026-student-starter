"""Part 4 student implementation."""

from app.backends import ansible, netconf, netmiko_textfsm, restconf

def dispatch_request(data):
    method =data["method"]
    action = data["action"]
    router = data["router"]
    interface = data["desired"]["interface"]
    name = interface["name"]

    if method == "restconf" and action == "status":
        return restconf.get_interface_state(router, name)
    if method == "restconf" and action == "plan":
        return restconf.plan_interface(router, interface)
    if method == "restconf" and action == "apply":
        return restconf.apply_interface(router, interface)
    if method == "netconf" and action == "status":
        return netconf.get_interface_state(router, name)
    if method == "netconf" and action == "plan":
        return netconf.plan_interface(router, interface)
    if method == "netconf" and action == "apply":
        return netconf.apply_interface(router, interface)
    if method == "ansible" and action == "apply":
        return ansible.apply_interface(router, interface)
    if method == "netmiko-textfsm" and action == "status":
        return netmiko_textfsm.get_interface_state(router, name)
    if method == "netmiko-textfsm" and action == "delete":
        return netmiko_textfsm.delete_interface(router, name)
    return {
        "status": "error",
        "result": "invalid_action",
    }