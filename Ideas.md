Below is a “full menu” you can build **given your probe**: Apple Terminal, **OSC 10/11 + OSC 4 palette 0–15 confirmed**, 256-color depth, **no truecolor guarantee**, and ST terminator works. I’m grouping by channel and then by “scene” combos.

I’m also writing these as *effect primitives* (pure functions) you can mix.

---

## A) Default Background effects (OSC 11)

### 1) Breathing lightness

* Oscillate background lightness within a dark band (baseline-centered).
* Variants: slow / medium / “double-breath” (inhale long, exhale short).

### 2) Bass pulse / impact flash

* Fast attack + decay envelope on bass or global.
* Variants: “thump” (quick), “swell” (slower), “heartbeat” (two pulses).

### 3) Narrow hue drift

* Hue drifts within a small window around baseline hue (±5–20°).
* Keeps it subtle; great always-on.

### 4) Wide hue cycle (still dark)

* Hue loops 0–360 with fixed low lightness.
* Variants: slow ambient, faster “club mode”.

### 5) Saturation breathing

* Keep hue/lightness mostly stable; modulate saturation 0.2–0.7.
* Makes the background feel like it has “color fog” without getting brighter.

### 6) Temperature shift (warm↔cool)

* Interpolate between two hues (e.g., 30° ↔ 210°) over time or music energy.

### 7) Beat-locked toggles (A/B)

* Alternate between two background states on each beat.
* Variants: subtle (tiny delta), bold (bigger hue delta).

### 8) Envelope-following darkness

* Background darkens on loudness instead of brightening (inverted impact).
* Feels “compression” / “ducking”.

### 9) “Storm cloud” randomness (bounded)

* Low-frequency noise + clamp; looks organic.
* Must be heavily smoothed to avoid flicker.

### 10) “Vignette illusion” (terminal-safe version)

* Since you can’t truly vignette per-pixel, approximate by keeping bg stable and using palette grays (7/8) to create perceived depth in text-heavy output.
* This is more of a “scene” constraint than a pure BG effect.

---

## B) Default Foreground effects (OSC 10)

### 1) Prompt breathing (lightness only)

* Oscillate foreground lightness around baseline.
* Variants: slow, medium, “inhale/exhale shape”.

### 2) Hue drift with fixed lightness

* Keep text brightness stable; shift hue.
* Great for readability + vibe.

### 3) Hue swing tied to mids/treble

* Hue motion increases with musical “interest” (mids/treble), not bass.

### 4) Saturation gating

* Saturation rises with energy; hue stays near baseline.
* Gives “excited text” without changing brightness much.

### 5) Contrast-locked foreground

* Foreground is derived from background + min-contrast constraint.
* Variants:

  * always lighten vs bg
  * always darken vs bg
  * choose side based on baseline fg

### 6) “Attention spotlight”

* If activity increases (keypresses), briefly boost fg saturation/brightness.
* Decays when idle.

### 7) “Idle fade”

* When idle, slowly desaturate and dim fg; when active, return to baseline.

### 8) “Monochrome wash”

* Pull fg toward grayscale on low energy; restore color on high energy.
* This is a very controllable “focus mode.”

---

## C) ANSI 16 palette effects (OSC 4 indices 0–15)

> These affect a *ton* of CLI output. Your probe confirms you can query baseline palette entries — huge win: you can be **theme-relative**, not hardcoded.

### Core palette transforms (apply to many indices)

#### 1) Global hue rotation (role-preserving)

* Rotate hue of each color around its own hue, keep lightness close to baseline.
* Variants: small swing, big swing, slow vs reactive.

#### 2) Palette “bloom” (saturation scale)

* Scale saturation up/down with an envelope; keep hue.

#### 3) Gamma wave (lightness scale)

* Scale lightness of non-protected colors:

  * brights get brighter, darks get slightly darker (or vice versa).
* Very punchy while preserving “what’s bright vs dark”.

#### 4) Temperature shift palette

* Pull all hues slightly warmer/cooler (like a color temperature slider).

#### 5) Two-state palette morph (A/B)

* Precompute two transformed palettes from baseline, then interpolate or toggle.
* Beat-locked toggles feel amazing.

#### 6) Complement shimmer (careful)

* Nudge some hues toward their complement on peaks (small amount).
* Must keep role brightness stable or it gets chaotic.

### Semantics-aware palette transforms (still “shotgun”)

#### 7) Danger/Success emphasis

* Only modulate red & green families (1/9 and 2/10) strongly.
* Others get subtle motion.

#### 8) “Warnings shimmer”

* Make reds (and maybe yellow) oscillate saturation/lightness at faster rate.

#### 9) “Success glow”

* Greens get a slow bloom; everything else steady.

#### 10) “Info coolness”

* Blues/cyans drift; reds stay anchored.

### Grayscale and anchor strategies (readability tools)

#### 11) Protect-set anchoring

* Keep indices 0, 7, 8, 15 stable (or near grayscale).
* Modulate chromatic colors more.

#### 12) Adaptive protect indices

* Detect which indices are closest to background luminance and protect them automatically.

#### 13) Background-distance clamp

* If any palette entry approaches background luminance too closely, push it away (contrast clamp).

#### 14) Preserve ordering

* Maintain relative luminance ordering from baseline so apps don’t lose meaning.

### Micro-texture palette effects (subtle but rich)

#### 15) “Sparkle” on treble

* Small, quick saturation bumps on bright variants (9–14) only.

#### 16) “Breathing syntax”

* Slow palette hue drift; quick saturation bloom on peaks.
* A “two-layer” palette effect.

---

## D) 256-color mode effects (indices 16–255)

Given your recommendation `try_osc_4_palette_16_255: false`, treat these as **indirect**:

### 1) Encourage 256 usage (not rewriting it)

* Use configs/envs so apps choose 256 colors instead of truecolor.
* Then your ANSI palette changes still matter because many tools map semantics into 0–15 or rely heavily on those.

### 2) Theme choice effects

* Choose 256-based themes in apps (vim, ls, ripgrep, etc.) to reduce truecolor output.
* Not a runtime effect, but it increases how much your runtime palette modulation affects.

(If later you confirm a terminal supports redefining 16–255, you can add “256 palette warps,” but for Apple Terminal assume no.)

---

## E) Truecolor effects (24-bit)

Probe says `likely_truecolor: false` here, so don’t bet on it *in Apple Terminal*. But conceptually, your library could still include:

### 1) Truecolor rewrite filter (PTY)

* Intercept `38;2` / `48;2` and apply the same hue/sat/lightness modulation law.

### 2) “Truecolor downgrade” mode

* Encourage apps to output 256 colors (configuration-based), so palette modulation grabs more.

Keep these effects in the registry but mark them as **requires: truecolor_support OR pty_filter**.

---

## F) Cross-channel constraints and “meta-effects”

These aren’t “effects” that pick a color; they’re pure post-processing layers that make *any* effect usable.

1. **Min-contrast enforcement** (fg vs bg)
2. **Palette vs bg contrast enforcement**
3. **Protect indices** (static or adaptive)
4. **Rate limiting / slew** (limit per-frame color delta)
5. **Energy shaping** (smoothstep, compression/expansion)
6. **Scene timescales** (slow BG + medium FG + fast palette)
7. **Return-to-baseline blending**

   * on exit or when idle, fade back to baseline smoothly
8. **“Safe mode” readability cap**

   * clamp saturation and lightness swings harder when in “work mode”

---

## G) Scenes (prebuilt combinations)

These are just curated bundles of A+B+C plus constraints.

1. **Mood Layering**

* BG: breathing lightness + narrow hue drift
* FG: hue drift fixed lightness
* Palette: role-preserving hue rotation (small swing)

2. **Club Mode**

* BG: wide hue cycle + bass pulse
* FG: contrast-locked brightness
* Palette: bloom + sparkle on treble (protect 0/7/8/15)

3. **Minimal Focus**

* BG: almost static (tiny breathing)
* FG: prompt breathing only
* Palette: very subtle temperature shift

4. **High Contrast Debug**

* BG: stable
* FG: contrast-locked
* Palette: emphasize red/yellow for warnings, keep rest stable

5. **Heartbeat**

* BG: double-pulse envelope
* FG: slight brightness bump
* Palette: saturation bloom synced to pulse

6. **Storm**

* BG: low-frequency noise drift
* FG: stable
* Palette: slow hue drift + occasional sparkle

---

## What this output enables specifically

Because Apple Terminal **responds to OSC queries**, you can do two things that make the whole system feel “pro”:

* **Theme-relative modulation**: always start from the user’s actual palette/fg/bg and warp it.
* **Perfect restore**: capture baseline and restore on exit, no guessing.

---

If you want, next step is to turn this list into a formal **effect registry** format (pure metadata): name, channels touched, requirements, knobs (swing, speed), and default constraints. That makes “select candidates based on probe” automatic.
