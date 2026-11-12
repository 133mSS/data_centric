"""Backward-compatible policy API delegated to the PDP."""
from pdp import decide


def check_access(user, document):
    return decide(user, document).effect
