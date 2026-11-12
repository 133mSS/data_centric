"""Policy Enforcement Point for document/chunk access."""
from pdp import decide


def enforce_access(subject, resource, action="read"):
    return decide(subject, resource, action=action)


def is_allowed(subject, resource, action="read"):
    return enforce_access(subject, resource, action=action).effect == "ALLOW"
