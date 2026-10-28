def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    managed_fields = ["ipv4", "description", "admin_state"]

    changes = {}

    if current_interface is None:
        for field in managed_fields:
            changes[field] = {"to": desired_interface[field]}
        return {
            "status": "ok",
            "result": "planned",
            "operation": "create",
            "changes": changes,
        }

    for field in managed_fields:
        old = current_interface.get(field)
        new = desired_interface[field]
        if old != new:
            changes[field] = {"from": old, "to": new}

    if not changes:
        operation = "no_change"
    else:
        operation = "update"
    return {
        "status": "ok",
        "result": "planned",
        "operation": operation,
        "changes": changes,
    }