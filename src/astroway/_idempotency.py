"""Idempotency-Key generation + policy.

Mirrors the TypeScript SDK's behaviour: every credit-costing POST gets a fresh
UUIDv4 by default, so a network-blip retry never double-bills. Server-side
deduplication uses the header to short-circuit the duplicate.
"""

from __future__ import annotations

import uuid
from typing import Callable, Union

# Policy: 'auto' (default — generate UUIDv4 per POST), 'off' (caller-controlled),
# or a callable that returns a string (custom generator: deterministic test keys, ULIDs, ...).
IdempotencyMode = Union[str, Callable[[], str]]


def generate_idempotency_key() -> str:
    """RFC 4122 v4 UUID generated via the standard library `uuid` module."""
    return str(uuid.uuid4())


def should_attach_idempotency(mode: IdempotencyMode | None, method: str) -> bool:
    """True when the SDK should auto-attach an Idempotency-Key for this request."""
    if mode == "off":
        return False
    return method.upper() == "POST"


def resolve_key_generator(mode: IdempotencyMode | None) -> Callable[[], str]:
    """Callable used to mint keys when the policy is 'auto' or a custom callable."""
    if callable(mode):
        return mode
    return generate_idempotency_key


__all__ = [
    "IdempotencyMode",
    "generate_idempotency_key",
    "resolve_key_generator",
    "should_attach_idempotency",
]
