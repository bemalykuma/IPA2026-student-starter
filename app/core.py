import yaml

def error(message):
    """return response dictionary for a given error message"""
    return {
        "status": "error",
        "result": message,
    }

def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    allow_router = ["10.0.29.101","10.0.29.102","10.0.29.103","10.0.29.104","10.0.29.105"]
    methods_action = {
        "restconf": {"status", "plan", "apply"},
        "netconf": {"status", "plan", "apply"},
        "ansible": {"apply"},
        "netmiko-textfsm": {"status","delete"},

    }

    if not isinstance(data, dict):
        return error("invalid_yaml")

    version = data.get("version")
    if type(version) is not int or version != 1:
        return error("invalid_version")

    if "router" not in data or data["router"] is None:
        return error("missing_router")
    if str(data["router"]) not in allow_router:
        return error("invalid_router")

    if "method" not in data or data["method"] is None:
        return error("missing_method")
    method = data["method"]
    if method not in methods_action:
        return error("invalid_method")

    if "action" not in data or data["action"] is None:
        return error("missing_action")
    action = data["action"]
    if action not in methods_action[method]:
        return error("invalid_action")

    desired = data.get("desired")
    if not isinstance(desired, dict):
        return error("missing_desired")
    interface = desired.get("interface")
    if not isinstance(interface, dict):
        return error("missing_interface")
    if not interface.get("name"):
        return error("missing_interface_name")

    if action in ("plan", "apply"):
        if not interface.get("ipv4"):
            return error("missing_ipv4")
        if not interface.get("description"):
            return error("missing_description")
        if "admin_state" not in interface or interface["admin_state"] is None:
            return error("missing_admin_state")
        if interface["admin_state"] not in ("up", "down"):
            return error("invalid_admin_state")
    return {"status": "ok", "result": "accepted"}

def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError):
        return error("invalid_yaml")
    return validate_request(data)
