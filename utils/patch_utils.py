"""Utilities for working with code patches."""

from typing import Mapping

REQUIRED_KEYS = {"type", "target_file", "patch", "reason"}


def validate_patch_format(patch: Mapping[str, object]) -> bool:
    """Return True if the mapping has all required patch keys."""
    if not isinstance(patch, Mapping):
        return False
    return REQUIRED_KEYS.issubset(patch.keys())
