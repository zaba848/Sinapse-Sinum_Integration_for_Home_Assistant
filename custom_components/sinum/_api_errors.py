"""Shared Sinum API exception types."""

from __future__ import annotations


class SinumAuthError(Exception):
    pass


class SinumConnectionError(Exception):
    pass


class SinumNotSupportedError(Exception):
    """Raised when the hub firmware does not support a given endpoint."""
