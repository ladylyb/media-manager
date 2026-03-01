from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CanonicalContext:
    """Optional policy context; values are deterministic inputs only."""

    preferred_roots: tuple[Path, ...] = ()
    created_at_weight: float = 1.0
    path_depth_weight: float = 1.0

