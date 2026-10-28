from ipaddress import IPv4Interface
import json
import os
from pathlib import Path
import subprocess

ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"
PLAYBOOK = ANSIBLE_DIR / "apply_interface.yml"
INVENTORY = ANSIBLE_DIR / "inventory.ini"

TIMEOUT = 15

def _error(code):
    return {
        "status": "error",
        "result": code,
    }
# ใช้ตอนส่งบอท
def _real_run_playbook(variables):
    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

    cmd = [
        "ansible-playbook",
        "-i", str(INVENTORY),
        str(PLAYBOOK),
        "-e", json.dumps(variables),
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise ConnectionError("ansible-playbook timed out")

    if proc.returncode == 0:
        return

    output = (proc.stdout + proc.stderr).lower()
    if "authentication" in output or "permission denied" in output:
        raise PermissionError(output)
    if "unreachable" in output or "timed out" in output or "timeout" in output:
        raise ConnectionError(output)
    raise RuntimeError(output)

def _map_exception(e):
    if isinstance(e, PermissionError):
        return _error("authentication_failed")
    if isinstance(e, ConnectionError):
        return _error("connection_failed")
    return _error("backend_failed")

def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    run_playbook = run_playbook or _real_run_playbook
    shutdown = True if desired_interface.get("admin_state") == "down" else False
    variables = {
        "router": router,
        "interface_name": desired_interface["name"],
        "description": desired_interface["description"],
        "ipv4_address": desired_interface["ipv4"].split("/")[0],
        "netmask": str(IPv4Interface(desired_interface["ipv4"]).netmask),
        "shutdown": shutdown,
    }
    try:
        run_playbook(variables)
    except Exception as e:
        return _map_exception(e)

    return {
        "status": "ok",
        "result": "applied",
    }
