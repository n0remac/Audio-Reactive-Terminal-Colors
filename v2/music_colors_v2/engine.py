from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from . import color
from .constraints import apply_constraints
from .effects import BG_EFFECTS, FG_EFFECTS, PALETTE_EFFECTS, fg_contrast_locked
from .types import Baseline, DesiredFrame, EngineState, Scene, Signals, RGB


def _update_impact_env(prev: float, x: float, dt: float, attack: float = 0.08, release: float = 0.30) -> float:
    x = color.clamp01(x)
    if dt <= 0:
        return max(prev, x)
    if x > prev:
        alpha = 1.0 - pow(2.718281828, -dt / max(1e-6, attack))
    else:
        alpha = 1.0 - pow(2.718281828, -dt / max(1e-6, release))
    return prev + (x - prev) * alpha


def tick(
    *,
    dt: float,
    signals: Signals,
    baseline: Baseline,
    scene: Scene,
    state: EngineState,
    prev_fg: Optional[RGB],
    prev_bg: Optional[RGB],
) -> Tuple[DesiredFrame, EngineState]:
    impact_env = _update_impact_env(state.impact_env, signals.global_, dt)
    mods = color.make_modulators(impact_env)

    desired = DesiredFrame()

    bg_fn = BG_EFFECTS.get(scene.bg_effect)
    if bg_fn is not None:
        desired.bg = bg_fn(baseline, signals, mods)

    fg_name = scene.fg_effect
    if fg_name == "contrast_locked":
        bg_for_fg = desired.bg or prev_bg or baseline.default_bg
        desired.fg = fg_contrast_locked(baseline, signals, mods, bg_for_fg)
    else:
        fg_fn = FG_EFFECTS.get(fg_name)
        if fg_fn is not None:
            desired.fg = fg_fn(baseline, signals, mods)

    pal_fn = PALETTE_EFFECTS.get(scene.palette_effect)
    if pal_fn is not None:
        desired.palette_updates = pal_fn(baseline, signals, mods, set(scene.constraints.protect_indices))

    desired = apply_constraints(
        desired,
        scene.constraints,
        baseline_fg=baseline.default_fg,
        baseline_bg=baseline.default_bg,
        prev_fg=prev_fg,
        prev_bg=prev_bg,
    )
    return desired, replace(state, impact_env=impact_env)
