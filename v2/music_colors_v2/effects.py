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


def bg_saturation_breath(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_bg
    h, s, l = color.rgb_to_hsl(base)
    lift = color.quantize01(color.smoothstep(signals.global_), levels=5)
    s = color.clamp01(s * (0.70 + 0.45 * lift))
    l = color.clamp01(l * 0.85 + 0.03 + 0.04 * lift)
    return color.hsl_to_rgb(h, s, l)


def bg_temperature_shift(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_bg
    h, s, l = color.rgb_to_hsl(base)
    warmth = (signals.bass - signals.treble) * 0.5 + 0.5  # 0..1 warm vs cool bias
    warmth_q = color.quantize01(warmth, levels=7)
    warm_hue = (h + 20.0) % 360.0
    cool_hue = (h - 40.0) % 360.0
    return color.mix_hsl(cool_hue, s, l, warm_hue, s, l, warmth_q)


def bg_inverted_loudness(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_bg
    h, s, l = color.rgb_to_hsl(base)
    damp = color.quantize01(color.smoothstep(signals.global_), levels=6)
    l = color.clamp01(l * (1.0 - 0.25 * damp))
    s = color.clamp01(s * (0.85 + 0.10 * damp))
    return color.hsl_to_rgb(h, s, l)


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


def fg_saturation_gate(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_fg
    h, s, l = color.rgb_to_hsl(base)
    gate = color.quantize01(color.smoothstep(signals.global_), levels=6)
    s = color.clamp01(s * (0.65 + 0.55 * gate))
    return color.hsl_to_rgb(h, s, l)


def fg_monochrome_wash(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_fg
    h, s, l = color.rgb_to_hsl(base)
    wash = 1.0 - color.quantize01(color.smoothstep(signals.global_), levels=7)
    s = color.clamp01(s * (0.25 + 0.75 * (1.0 - wash)))
    return color.hsl_to_rgb(h, s, l)


def fg_treble_swing(baseline: Baseline, signals: Signals, mods: color.Modulators) -> RGB:
    base = baseline.default_fg
    h, s, l = color.rgb_to_hsl(base)
    swing = 32.0 * color.quantize01(color.smoothstep(signals.treble), levels=8)
    hue = h + swing
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


def palette_temperature_shift(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    out: Dict[int, RGB] = {}
    tilt = color.quantize01((signals.bass - signals.treble) * 0.5 + 0.5, levels=7)  # 0 cool -> 1 warm
    for i, c in enumerate(baseline.palette16):
        if i in protect:
            continue
        h, s, l = color.rgb_to_hsl(c)
        warm_h = (h + 22.0) % 360.0
        cool_h = (h - 28.0) % 360.0
        out[i] = color.mix_hsl(cool_h, s, l, warm_h, s, l, tilt)
    return out


def palette_gamma_wave(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    out: Dict[int, RGB] = {}
    gamma = 0.90 + 0.35 * color.quantize01(color.smoothstep(signals.global_), levels=6)
    for i, c in enumerate(baseline.palette16):
        if i in protect:
            continue
        h, s, l = color.rgb_to_hsl(c)
        # gamma-like curve around mid gray
        l_adj = color.clamp01(pow(max(1e-4, l), gamma))
        out[i] = color.hsl_to_rgb(h, s, l_adj)
    return out


def palette_complement_sparkle(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    out: Dict[int, RGB] = {}
    sparkle = 0.18 * color.quantize01(color.smoothstep(signals.treble), levels=5)
    for i, c in enumerate(baseline.palette16):
        if i in protect:
            continue
        h, s, l = color.rgb_to_hsl(c)
        comp = color.hsl_to_rgb(h + 180.0, s, l)
        out[i] = color.mix_hsl(h, s, l, (h + 180.0) % 360.0, s, l, sparkle)
    return out


def palette_danger_success(
    baseline: Baseline, signals: Signals, mods: color.Modulators, protect: set[int]
) -> Dict[int, RGB]:
    out: Dict[int, RGB] = {}
    danger_boost = color.quantize01(color.smoothstep(signals.bass), levels=6)
    success_boost = color.quantize01(color.smoothstep(signals.mids), levels=6)
    for i, c in enumerate(baseline.palette16):
        if i in protect:
            continue
        h, s, l = color.rgb_to_hsl(c)
        if i in {1, 9}:  # reds
            s = color.clamp01(s * (0.80 + 0.50 * danger_boost))
            l = color.clamp01(l * (0.90 + 0.25 * danger_boost))
        elif i in {2, 10}:  # greens
            s = color.clamp01(s * (0.80 + 0.40 * success_boost))
            l = color.clamp01(l * (0.92 + 0.22 * success_boost))
        out[i] = color.hsl_to_rgb(h, s, l)
    return out


BG_EFFECTS = {
    "bass_pulse": bg_bass_pulse,
    "bass_impact_tint": bg_bass_impact_tint,
    "saturation_breath": bg_saturation_breath,
    "temperature_shift": bg_temperature_shift,
    "inverted_loudness": bg_inverted_loudness,
}

FG_EFFECTS = {
    "spectrum_tint": fg_spectrum_tint,
    "contrast_locked": None,  # special: depends on bg
    "saturation_gate": fg_saturation_gate,
    "monochrome_wash": fg_monochrome_wash,
    "treble_swing": fg_treble_swing,
}

PALETTE_EFFECTS = {
    "spectrum_quantized": palette_spectrum_quantized,
    "role_hue_rotate": palette_role_preserving_hue_rotation,  # alias -> spectrum_quantized
    "sat_bloom": palette_saturation_bloom_on_peaks,  # alias -> spectrum_quantized
    "temperature_shift": palette_temperature_shift,
    "gamma_wave": palette_gamma_wave,
    "complement_sparkle": palette_complement_sparkle,
    "danger_success": palette_danger_success,
}
