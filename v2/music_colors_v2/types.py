from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Literal, List

Terminator = Literal["st", "bel"]


@dataclass(frozen=True)
class RGB:
    r: int
    g: int
    b: int

    def clamped(self) -> "RGB":
        return RGB(
            r=max(0, min(255, int(self.r))),
            g=max(0, min(255, int(self.g))),
            b=max(0, min(255, int(self.b))),
        )

    def to_hex(self) -> str:
        c = self.clamped()
        return f"#{c.r:02x}{c.g:02x}{c.b:02x}"

    def to_osc_rgb_triplet(self) -> str:
        c = self.clamped()
        return f"rgb:{c.r:02x}/{c.g:02x}/{c.b:02x}"


@dataclass(frozen=True)
class Capabilities:
    channels: Set[str]  # {"default_fg","default_bg","palette16"}
    terminator: Terminator
    fps_cap: float
    min_rgb_delta: int
    truecolor_likely: bool = True


@dataclass(frozen=True)
class Baseline:
    default_fg: RGB
    default_bg: RGB
    palette16: List[RGB]  # len=16


@dataclass(frozen=True)
class Signals:
    # 16-band spectrum (low→high) derived from the CAVA frame, normalized to [0..1].
    # This is the primary driver for “direct” audio→color mapping.
    bands16: List[float]
    bass: float
    mids: float
    treble: float
    global_: float
    beat: bool = False
    activity: float = 0.0
    idle_seconds: float = 0.0


@dataclass
class DesiredFrame:
    fg: Optional[RGB] = None
    bg: Optional[RGB] = None
    palette_updates: Dict[int, RGB] = field(default_factory=dict)


@dataclass(frozen=True)
class Constraints:
    min_contrast_delta: float = 0.22
    protect_indices: Set[int] = field(default_factory=lambda: {0, 7, 8, 15})
    max_bg_lightness: float = 0.18
    max_fg_saturation: float = 0.85
    delta_limit: int = 18  # max per-channel delta per tick (0..255)


@dataclass(frozen=True)
class Scene:
    name: str
    bg_effect: str
    fg_effect: str
    palette_effect: str
    constraints: Constraints


@dataclass
class EngineState:
    impact_env: float = 0.0
