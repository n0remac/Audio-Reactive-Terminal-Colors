from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Tuple

from .types import RGB


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def luma(c: RGB) -> float:
    r, g, b = c.r / 255.0, c.g / 255.0, c.b / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rgb_to_hsl(c: RGB) -> Tuple[float, float, float]:
    r, g, b = c.r / 255.0, c.g / 255.0, c.b / 255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return (h * 360.0), s, l


def hsl_to_rgb(h_deg: float, s: float, l: float) -> RGB:
    h = (h_deg % 360.0) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, clamp01(l), clamp01(s))
    return RGB(int(r * 255), int(g * 255), int(b * 255)).clamped()


def rotate_hue(c: RGB, delta_deg: float, sat_scale: float = 1.0, light_scale: float = 1.0) -> RGB:
    h, s, l = rgb_to_hsl(c)
    return hsl_to_rgb(h + delta_deg, clamp01(s * sat_scale), clamp01(l * light_scale))


def limit_step(prev: RGB, target: RGB, max_delta: int) -> RGB:
    if max_delta <= 0:
        return target
    dr = max(-max_delta, min(max_delta, target.r - prev.r))
    dg = max(-max_delta, min(max_delta, target.g - prev.g))
    db = max(-max_delta, min(max_delta, target.b - prev.b))
    return RGB(prev.r + dr, prev.g + dg, prev.b + db).clamped()


def rgb_distance(a: RGB, b: RGB) -> int:
    return max(abs(a.r - b.r), abs(a.g - b.g), abs(a.b - b.b))


def smoothstep(x: float) -> float:
    x = clamp01(x)
    return x * x * (3.0 - 2.0 * x)


@dataclass(frozen=True)
class Modulators:
    # No time-based LFOs: keep modulation tightly synced to audio.
    impact: float


def make_modulators(impact: float) -> Modulators:
    return Modulators(impact=clamp01(impact))


def quantize01(x: float, levels: int) -> float:
    """
    Quantize x in [0..1] to `levels` evenly spaced steps (including endpoints).
    levels<=1 returns 0 or 1 via clamp.
    """
    x = clamp01(x)
    if levels <= 1:
        return 1.0 if x >= 0.5 else 0.0
    q = round(x * (levels - 1)) / (levels - 1)
    return clamp01(q)
