"""Profile-scoped secret lookup.

One Hermes process can serve several profiles, so ``os.environ.get`` is the wrong way to read a
provider key: it may hand a tool the key belonging to a different profile. ``agent.secret_scope``
resolves the value for the profile that is actually running; when that module is unavailable
(standalone use, tests, older host) we fall back to the environment.
"""

from __future__ import annotations

import os


def get_secret(name: str, default: str | None = None) -> str | None:
    """Return the running profile's secret ``name``, falling back to the environment."""
    try:
        from agent.secret_scope import get_secret as scoped  # type: ignore
    except ImportError:
        return os.environ.get(name, default)
    # Once the scope module exists it decides: a miss returns ``default`` and an
    # unbound profile raises UnscopedSecretError. Falling back to os.environ here
    # would hand the tool the launch profile's key — the leak this wrapper exists
    # to stop.
    return scoped(name, default)
