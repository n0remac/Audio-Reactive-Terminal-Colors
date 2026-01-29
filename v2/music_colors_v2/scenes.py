from __future__ import annotations

from .types import Constraints, Scene


SCENES = {
    "mood": Scene(
        name="mood",
        bg_effect="bass_pulse",
        fg_effect="spectrum_tint",
        palette_effect="spectrum_quantized",
        constraints=Constraints(
            min_contrast_delta=0.22,
            protect_indices={0, 7, 8, 15},
            max_bg_lightness=0.18,
            max_fg_saturation=0.85,
            delta_limit=18,
        ),
    ),
    "punchy": Scene(
        name="punchy",
        bg_effect="bass_impact_tint",
        fg_effect="contrast_locked",
        palette_effect="spectrum_quantized",
        constraints=Constraints(
            min_contrast_delta=0.26,
            protect_indices={0, 7, 8, 15},
            max_bg_lightness=0.17,
            max_fg_saturation=0.80,
            delta_limit=14,
        ),
    ),
    "spectrum": Scene(
        name="spectrum",
        bg_effect="bass_pulse",
        fg_effect="contrast_locked",
        palette_effect="spectrum_quantized",
        constraints=Constraints(
            min_contrast_delta=0.24,
            protect_indices=set(),  # map all indices for maximum “CAVA-like” color coverage
            max_bg_lightness=0.18,
            max_fg_saturation=0.85,
            delta_limit=18,
        ),
    ),
    "warmcool": Scene(
        name="warmcool",
        bg_effect="temperature_shift",
        fg_effect="saturation_gate",
        palette_effect="temperature_shift",
        constraints=Constraints(
            min_contrast_delta=0.24,
            protect_indices={0, 7, 8, 15},
            max_bg_lightness=0.20,
            max_fg_saturation=0.85,
            delta_limit=16,
        ),
    ),
    "focus": Scene(
        name="focus",
        bg_effect="inverted_loudness",
        fg_effect="monochrome_wash",
        palette_effect="gamma_wave",
        constraints=Constraints(
            min_contrast_delta=0.26,
            protect_indices={0, 7, 8, 15},
            max_bg_lightness=0.16,
            max_fg_saturation=0.75,
            delta_limit=14,
        ),
    ),
}
