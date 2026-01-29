from __future__ import annotations

from typing import Optional

from . import color
from .types import Constraints, DesiredFrame, RGB


def _ensure_min_contrast(fg: RGB, bg: RGB, min_delta: float) -> RGB:
    if abs(color.luma(fg) - color.luma(bg)) >= min_delta:
        return fg
    h, s, l = color.rgb_to_hsl(fg)
    bg_l = color.luma(bg)
    fg_l = color.luma(fg)
    if fg_l >= bg_l:
        l = color.clamp01(l + 0.22)
    else:
        l = color.clamp01(l - 0.22)
    return color.hsl_to_rgb(h, s, l)


def _clamp_bg_dark(bg: RGB, max_lightness: float) -> RGB:
    h, s, l = color.rgb_to_hsl(bg)
    if l <= max_lightness:
        return bg
    return color.hsl_to_rgb(h, s, max_lightness)


def _limit_fg_saturation(fg: RGB, max_sat: float) -> RGB:
    h, s, l = color.rgb_to_hsl(fg)
    if s <= max_sat:
        return fg
    return color.hsl_to_rgb(h, max_sat, l)


def apply_constraints(
    desired: DesiredFrame,
    constraints: Constraints,
    *,
    baseline_fg: RGB,
    baseline_bg: RGB,
    prev_fg: Optional[RGB],
    prev_bg: Optional[RGB],
) -> DesiredFrame:
    fg = desired.fg
    bg = desired.bg

    if bg is not None:
        bg = _clamp_bg_dark(bg, constraints.max_bg_lightness)
        if prev_bg is not None:
            bg = color.limit_step(prev_bg, bg, constraints.delta_limit)

    if fg is not None:
        fg = _limit_fg_saturation(fg, constraints.max_fg_saturation)

    bg_for_contrast = bg or prev_bg or baseline_bg
    if fg is not None:
        fg = _ensure_min_contrast(fg, bg_for_contrast, constraints.min_contrast_delta)
        if prev_fg is not None:
            fg = color.limit_step(prev_fg, fg, constraints.delta_limit)

    out = DesiredFrame(fg=fg, bg=bg, palette_updates=dict(desired.palette_updates))
    for idx in list(out.palette_updates.keys()):
        if idx in constraints.protect_indices:
            out.palette_updates.pop(idx, None)
    return out

