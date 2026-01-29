#!/usr/bin/env python3
"""
CAVA -> terminal palette + foreground + background "hue rotation"

Updates:
- Adds OSC 10 default foreground modulation (so your bash prompt changes).
- Keeps OSC 11 background modulation.
- Keeps OSC 4 palette rotation for ANSI 0–15.
- Cursor/VSCode terminal friendly: FPS cap + RGB delta thresholding.
- Writes OSC to /dev/tty so it works in the background.
- Logs to file.

Notes:
- Your PS1 is plain (no ANSI), so it uses the terminal *default foreground*.
  That is controlled by OSC 10 / OSC 110 (reset).
"""

import os
import sys
import time
import argparse
import colorsys
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Set

# --- OSC helpers -------------------------------------------------------------

def _osc(seq: str, terminator: str) -> bytes:
    if terminator == "st":
        return (seq + "\x1b\\").encode("ascii")
    return (seq + "\x07").encode("ascii")

def osc_set_palette(index: int, r: int, g: int, b: int, terminator: str) -> bytes:
    # OSC 4 ; idx ; rgb:RR/GG/BB
    return _osc(f"\x1b]4;{index};rgb:{r:02x}/{g:02x}/{b:02x}", terminator)

def osc_set_background(r: int, g: int, b: int, terminator: str) -> bytes:
    # OSC 11 ; #RRGGBB
    return _osc(f"\x1b]11;#{r:02x}{g:02x}{b:02x}", terminator)

def osc_set_foreground(r: int, g: int, b: int, terminator: str) -> bytes:
    # OSC 10 ; #RRGGBB   (default foreground)
    return _osc(f"\x1b]10;#{r:02x}{g:02x}{b:02x}", terminator)

def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

def hsl_to_rgb255(h_deg: float, s: float, l: float) -> Tuple[int, int, int]:
    h = (h_deg % 360.0) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)  # HLS: (h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)

def rgb255_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    h, l, s = colorsys.rgb_to_hls(rf, gf, bf)
    return (h * 360.0), s, l

def rotate_hue_rgb(r: int, g: int, b: int, delta_deg: float,
                   sat_scale: float = 1.0, light_scale: float = 1.0) -> Tuple[int, int, int]:
    h, s, l = rgb255_to_hsl(r, g, b)
    s = clamp01(s * sat_scale)
    l = clamp01(l * light_scale)
    return hsl_to_rgb255(h + delta_deg, s, l)

# --- Smoothing ---------------------------------------------------------------

@dataclass
class Smooth:
    value: float = 0.0
    alpha: float = 0.12

    def update(self, x: float) -> float:
        self.value = (1.0 - self.alpha) * self.value + self.alpha * x
        return self.value

# --- Robust FIFO reading -----------------------------------------------------

def open_fifo_blocking(path: str) -> int:
    return os.open(path, os.O_RDONLY)

def read_frames(fd: int, bars: int, log: logging.Logger) -> Iterable[bytes]:
    """
    Yield frames of `bars` bytes (8-bit values). Ignore newlines if present.
    """
    buf = bytearray()
    last_log = 0.0

    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            time.sleep(0.05)
            continue

        for b in chunk:
            if b == 10:  # '\n'
                continue
            buf.append(b)

        now = time.time()
        if now - last_log > 5.0:
            log.debug("fifo: read=%d bytes, buffered=%d", len(chunk), len(buf))
            last_log = now

        while len(buf) >= bars:
            frame = bytes(buf[:bars])
            del buf[:bars]
            yield frame

def band_energy(frame: bytes, lo: int, hi: int) -> float:
    lo = max(0, lo)
    hi = min(len(frame), hi)
    if hi <= lo:
        return 0.0
    s = 0
    for v in frame[lo:hi]:
        s += v
    return (s / (hi - lo)) / 255.0

# --- Utilities ----------------------------------------------------------------

def parse_band(spec: str) -> Tuple[float, float]:
    a, b = spec.split(":")
    return float(a), float(b)

def parse_protect(spec: str) -> Set[int]:
    out: Set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            aa, bb = int(a), int(b)
            for i in range(min(aa, bb), max(aa, bb) + 1):
                out.add(i)
        else:
            out.add(int(part))
    return out

def curve(x: float) -> float:
    x = clamp01(x)
    return x * x * (3 - 2 * x)  # smoothstep

def luma(r: int, g: int, b: int) -> float:
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0

def ensure_contrast(fg: Tuple[int, int, int], bg: Tuple[int, int, int], min_delta: float) -> Tuple[int, int, int]:
    """
    If fg and bg luminance are too close, nudge fg lightness away.
    Heuristic for Cursor readability when rotating lots of colors.
    """
    fr, fg_, fb = fg
    br, bg_, bb = bg
    if abs(luma(fr, fg_, fb) - luma(br, bg_, bb)) >= min_delta:
        return fg

    h, s, l_ = rgb255_to_hsl(fr, fg_, fb)
    bg_l = luma(br, bg_, bb)
    fg_l = luma(fr, fg_, fb)

    if fg_l >= bg_l:
        l_new = clamp01(l_ + 0.18)
    else:
        l_new = clamp01(l_ - 0.18)
    return hsl_to_rgb255(h, s, l_new)

# --- Baselines ---------------------------------------------------------------
# Terminals don't reliably expose current palette/fg/bg values, so we define baselines.
# You can later replace these with your actual Cursor theme colors.

BASE16_XTERM: List[Tuple[int, int, int]] = [
    (0x00, 0x00, 0x00), (0xcd, 0x00, 0x00), (0x00, 0xcd, 0x00), (0xcd, 0xcd, 0x00),
    (0x00, 0x00, 0xee), (0xcd, 0x00, 0xcd), (0x00, 0xcd, 0xcd), (0xe5, 0xe5, 0xe5),
    (0x7f, 0x7f, 0x7f), (0xff, 0x00, 0x00), (0x00, 0xff, 0x00), (0xff, 0xff, 0x00),
    (0x5c, 0x5c, 0xff), (0xff, 0x00, 0xff), (0x00, 0xff, 0xff), (0xff, 0xff, 0xff),
]

# Default foreground baseline (for PS1 / normal text)
# Pick something neutral & readable; will be contrast-adjusted vs bg anyway.
FG_BASE: Tuple[int, int, int] = (0xD0, 0xD0, 0xD0)

# --- Main --------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="CAVA->OSC: rotate ANSI palette 0–15 + modulate default foreground/background (OSC 10/11)."
    )

    ap.add_argument("--fifo", default="/tmp/cava.fifo")
    ap.add_argument("--bars", type=int, default=64)

    ap.add_argument("--smooth", type=float, default=0.12, help="EMA alpha. Lower = smoother.")
    ap.add_argument("--fps-cap", type=float, default=20.0, help="Cursor-safe default. Try 15–25.")
    ap.add_argument("--tty", default="/dev/tty", help="TTY to write OSC to (critical for background).")

    ap.add_argument("--log-file", default=os.path.expanduser("~/Library/Logs/palette_swapper.log"))
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    ap.add_argument("--terminator", default="st", choices=["st", "bel"],
                    help="OSC terminator. If Cursor ever acts weird, try --terminator bel.")

    # Band splits
    ap.add_argument("--bass", default="0.00:0.20")
    ap.add_argument("--mids", default="0.20:0.65")
    ap.add_argument("--treble", default="0.65:1.00")

    # Rotate palette 0–15
    ap.add_argument("--rotate-all", action="store_true", default=True,
                    help="Rotate hue of all ANSI colors 0–15 (default: on).")
    ap.add_argument("--all-swing", type=float, default=14.0,
                    help="Max hue rotation degrees at full global energy.")
    ap.add_argument("--protect", default="0,7,8,15",
                    help="Palette indices to NOT change (comma list and/or ranges like '0,7-8,15').")
    ap.add_argument("--sat-scale", type=float, default=1.0,
                    help="Scale saturation of rotated palette colors (1.0 = keep).")
    ap.add_argument("--light-scale", type=float, default=1.0,
                    help="Scale lightness of rotated palette colors (1.0 = keep).")

    # Background (OSC 11)
    ap.add_argument("--background", action="store_true", default=True,
                    help="Modulate terminal background (OSC 11) using bass.")
    ap.add_argument("--bg-hue", type=float, default=220.0, help="Base hue for background.")
    ap.add_argument("--bg-swing", type=float, default=10.0, help="Hue swing for background.")
    ap.add_argument("--bg-l-min", type=float, default=0.08, help="Min background lightness (dark).")
    ap.add_argument("--bg-l-max", type=float, default=0.14, help="Max background lightness (dark).")
    ap.add_argument("--bg-sat", type=float, default=0.55, help="Background saturation (0..1).")

   # Foreground (OSC 10)
    ap.add_argument("--foreground", action="store_true", default=True,
                    help="Modulate default foreground (OSC 10) (affects PS1 / default text).")
    ap.add_argument("--fg-hue", type=float, default=190.0, help="Base hue for foreground.")
    ap.add_argument("--fg-swing", type=float, default=70.0, help="Hue swing for foreground.")
    ap.add_argument("--fg-sat", type=float, default=0.90, help="Foreground saturation (0..1).")
    ap.add_argument("--fg-light", type=float, default=0.70, help="Foreground lightness (0..1).")
    ap.add_argument("--fg-light-swing", type=float, default=0.18,
                    help="Lightness swing for foreground (0..1).")
    ap.add_argument("--fg-force-interval", type=float, default=1.0,
                    help="Force foreground OSC update at least every N seconds.")

    # Safety / stability
    ap.add_argument("--min-rgb-delta", type=int, default=2,
                    help="Only send updates when any RGB channel changes by >= this amount.")
    ap.add_argument("--min-contrast", type=float, default=0.10,
                    help="Minimum luminance delta vs background for non-protected indices and foreground (0..1).")

    args = ap.parse_args()

    # Logging
    os.makedirs(os.path.dirname(args.log_file), exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.log_file), logging.StreamHandler(sys.stderr)],
    )
    log = logging.getLogger("palette")

    def parse_hex_color(s: str) -> Tuple[int, int, int]:
        s = s.strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) != 6:
            raise ValueError("Expected #RRGGBB")
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)

    # Open TTY for OSC output
    try:
        tty_fd = os.open(args.tty, os.O_WRONLY)
        log.info("writing OSC to %s (terminator=%s)", args.tty, args.terminator)
    except Exception as e:
        log.error("failed to open tty %s: %s", args.tty, e)
        log.error("fallback to stdout (will NOT work if stdout redirected)")
        tty_fd = None

    # Open FIFO
    if not os.path.exists(args.fifo):
        log.error("FIFO not found: %s", args.fifo)
        return 2
    try:
        fifo_fd = open_fifo_blocking(args.fifo)
        log.info("opened FIFO %s", args.fifo)
    except Exception as e:
        log.error("failed to open FIFO: %s", e)
        return 2

    # Band indices
    bars = args.bars
    bass_f = parse_band(args.bass)
    mids_f = parse_band(args.mids)
    treb_f = parse_band(args.treble)

    bass_idx = (int(bass_f[0] * bars), int(bass_f[1] * bars))
    mids_idx = (int(mids_f[0] * bars), int(mids_f[1] * bars))
    treb_idx = (int(treb_f[0] * bars), int(treb_f[1] * bars))

    log.info("bands: bass=%s mids=%s treb=%s (bars=%d)", bass_idx, mids_idx, treb_idx, bars)

    s_bass = Smooth(alpha=clamp01(args.smooth))
    s_mids = Smooth(alpha=clamp01(args.smooth))
    s_treb = Smooth(alpha=clamp01(args.smooth))

    protect = parse_protect(args.protect)
    log.info("protect indices: %s", sorted(protect))

    min_dt = 1.0 / max(1.0, args.fps_cap)
    last_emit = 0.0

    # Cache last sent values to reduce spam & Cursor glitches
    last_sent_palette: List[Tuple[int, int, int]] = [(-1, -1, -1)] * 16
    last_bg: Tuple[int, int, int] = (-1, -1, -1)
    last_fg: Tuple[int, int, int] = (-1, -1, -1)
    last_fg_emit = 0.0

    def should_send_rgb(prev: Tuple[int, int, int], cur: Tuple[int, int, int]) -> bool:
        pr, pg, pb = prev
        cr, cg, cb = cur
        d = args.min_rgb_delta
        return (abs(cr - pr) >= d) or (abs(cg - pg) >= d) or (abs(cb - pb) >= d)

    frames = 0
    last_stats = time.time()

    try:
        for frame in read_frames(fifo_fd, bars, log):
            frames += 1

            bass = band_energy(frame, *bass_idx)
            mids = band_energy(frame, *mids_idx)
            treb = band_energy(frame, *treb_idx)

            bass_s = s_bass.update(bass)
            mids_s = s_mids.update(mids)
            treb_s = s_treb.update(treb)

            now = time.time()
            if now - last_emit < min_dt:
                continue
            last_emit = now

            bass_c = curve(bass_s)
            mids_c = curve(mids_s)
            treb_c = curve(treb_s)

            # Global energy mix
            global_e = clamp01(0.45 * bass_c + 0.35 * mids_c + 0.20 * treb_c)

            # Hue rotation delta centered around 0
            delta = (global_e - 0.5) * 2.0 * args.all_swing

            # Background from bass
            bg_rgb: Optional[Tuple[int, int, int]] = None
            if args.background:
                bg_h = args.bg_hue + (bass_c - 0.5) * 2.0 * args.bg_swing
                bg_l = args.bg_l_min + (args.bg_l_max - args.bg_l_min) * bass_c
                bg_rgb = hsl_to_rgb255(bg_h, clamp01(args.bg_sat), clamp01(bg_l))

            # Foreground from mids + global (so prompt reacts nicely to "musical content")
            fg_rgb: Optional[Tuple[int, int, int]] = None
            if args.foreground:
                # Use mids as "interest" driver + global for smooth motion
                # (centered around 0; then scaled)
                fg_h = args.fg_hue + (mids_c - 0.5) * 2.0 * args.fg_swing + delta
                fg_l = args.fg_light + (mids_c - 0.5) * 2.0 * args.fg_light_swing
                fg_rgb = hsl_to_rgb255(fg_h, clamp01(args.fg_sat), clamp01(fg_l))

                if bg_rgb is not None:
                    fg_rgb = ensure_contrast(fg_rgb, bg_rgb, args.min_contrast)

            payload_parts: List[bytes] = []

            # Apply background
            if bg_rgb is not None and should_send_rgb(last_bg, bg_rgb):
                payload_parts.append(osc_set_background(*bg_rgb, terminator=args.terminator))
                log.debug("OSC11 bg=%s", bg_rgb)
                last_bg = bg_rgb

            # Apply foreground
            if fg_rgb is not None and (
                should_send_rgb(last_fg, fg_rgb) or (now - last_fg_emit) >= args.fg_force_interval
            ):
                payload_parts.append(osc_set_foreground(*fg_rgb, terminator=args.terminator))
                log.debug("OSC10 fg=%s", fg_rgb)
                last_fg = fg_rgb
                last_fg_emit = now


            # Apply palette rotation
            if args.rotate_all:
                base = BASE16_XTERM
                for idx, (r0, g0, b0) in enumerate(base):
                    if idx in protect:
                        continue

                    r1, g1, b1 = rotate_hue_rgb(
                        r0, g0, b0,
                        delta_deg=delta,
                        sat_scale=args.sat_scale,
                        light_scale=args.light_scale,
                    )

                    if bg_rgb is not None:
                        r1, g1, b1 = ensure_contrast((r1, g1, b1), bg_rgb, args.min_contrast)

                    cur = (r1, g1, b1)
                    if should_send_rgb(last_sent_palette[idx], cur):
                        payload_parts.append(osc_set_palette(idx, r1, g1, b1, terminator=args.terminator))
                        last_sent_palette[idx] = cur

            if payload_parts:
                payload = b"".join(payload_parts)
                try:
                    if tty_fd is not None:
                        os.write(tty_fd, payload)
                    else:
                        sys.stdout.buffer.write(payload)
                        sys.stdout.buffer.flush()
                except Exception as e:
                    log.error("failed writing OSC: %s", e)

            if now - last_stats > 2.0:
                log.debug(
                    "frames=%d bass=%.3f mids=%.3f treb=%.3f smoothed=(%.3f %.3f %.3f) "
                    "global=%.3f delta=%.2f",
                    frames, bass, mids, treb, bass_s, mids_s, treb_s, global_e, delta
                )
                last_stats = now

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt: exiting")
        return 0
    finally:
        try:
            os.close(fifo_fd)
        except Exception:
            pass
        if tty_fd is not None:
            try:
                os.close(tty_fd)
            except Exception:
                pass

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
