from __future__ import annotations

from typing import Dict

from . import color
from .types import RGB, Baseline, Signals


def bg_bass_pulse(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_bg
    h, s, l = color.rgb_to_hsl(base)
    amp = color.smoothstep(signals.bass) * (0.65 + 0.35 * mods.impact)
    # Keep background in a dark band; brighten directly with bass.
    l = color.clamp01(l * 0.70 + 0.04 + 0.12 * amp)
    l = min(l, 0.20)
    s = color.clamp01(s * (0.85 + 0.55 * amp))
    return color.hsl_to_rgb(h, s, l)


def bg_bass_impact_tint(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_bg
    h, s, l = color.rgb_to_hsl(base)
    impact = color.smoothstep(signals.bass) * (0.55 + 0.45 * mods.impact)
    s = color.clamp01(s * (0.90 + 1.00 * impact))
    l = color.clamp01(l * 0.80 + 0.03 + 0.10 * impact)
    return color.hsl_to_rgb(h, s, min(l, 0.22))


def fg_spectrum_tint(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_fg
    h, s, l = color.rgb_to_hsl(base)
    # Hue follows spectral “centroid” (low→high = 0..1), with mild quantization for clarity.
    weights = signals.bands16
    total = sum(weights) + 1e-9
    centroid = sum((i / 15.0) * w for i, w in enumerate(weights)) / total
    centroid_q = color.quantize01(centroid, levels=12)
    hue = 300.0 * centroid_q  # sweep most of the visible wheel
    # Saturation increases with treble so sharp sounds pop.
    s = color.clamp01(s * (0.85 + 0.55 * color.smoothstep(signals.treble)))
    return color.hsl_to_rgb(hue, s, l)


def fg_contrast_locked(baseline: Baseline, signals: Signals, mods: color.Modulators, bg: RGB) -> RGB:
    base = baseline.default_fg
    _h, s, _l = color.rgb_to_hsl(base)
    # Hue follows centroid to keep it audio-driven, not time-driven.
    weights = signals.bands16
    total = sum(weights) + 1e-9
    centroid = sum((i / 15.0) * w for i, w in enumerate(weights)) / total
    hue = 300.0 * color.quantize01(centroid, levels=12)
    intensity = color.smoothstep(signals.global_)
    bg_l = color.luma(bg)
    l = color.clamp01(0.62 + (bg_l - 0.12) * 0.35 + 0.10 * intensity)
    s = color.clamp01(s * (0.90 + 0.15 * intensity))
    return color.hsl_to_rgb(hue, s, l)


def palette_role_preserving_hue_rotation(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    # Deprecated in favor of direct spectrum mapping (kept for compatibility).
    return palette_spectrum_quantized(baseline, signals, mods, protect)


def palette_saturation_bloom_on_peaks(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    # Deprecated in favor of direct spectrum mapping (kept for compatibility).
    return palette_spectrum_quantized(baseline, signals, mods, protect)


def palette_spectrum_quantized(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    """
    Map the 16 spectrum bands directly onto palette indices 0..15 (low→high frequency),
    with quantized brightness so changes read clearly and remain tied to the beat.
    """
    out: Dict[int, RGB] = {}
    # Fixed hue assignment per index ensures we “cover” the spectrum at all times.
    # Energy only controls brightness (quantized), with mild saturation boost on impact.
    for i in range(16):
        if i in protect:
            continue
        amp = signals.bands16[i]
        amp_q = color.quantize01(amp, levels=7)
        hue = (i / 15.0) * 300.0
        sat = 0.80 + 0.18 * mods.impact
        light = 0.18 + 0.52 * amp_q
        out[i] = color.hsl_to_rgb(hue, sat, light)
    return out


BG_EFFECTS = {
    "bass_pulse": bg_bass_pulse,
    "bass_impact_tint": bg_bass_impact_tint,
}

FG_EFFECTS = {
    "spectrum_tint": fg_spectrum_tint,
    "contrast_locked": None,  # special: depends on bg
}

PALETTE_EFFECTS = {
    "spectrum_quantized": palette_spectrum_quantized,
    "role_hue_rotate": palette_role_preserving_hue_rotation,  # alias -> spectrum_quantized
    "sat_bloom": palette_saturation_bloom_on_peaks,  # alias -> spectrum_quantized
}
