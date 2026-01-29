from __future__ import annotations

import argparse
import os
import signal
import time
from typing import Optional, Tuple

from .backend import OSCBackend
from .baseline import fallback_baseline, query_baseline
from .engine import tick
from .scenes import SCENES
from .signals import SignalExtractor, open_fifo_blocking, read_cava_frames
from .types import Capabilities, EngineState


def _parse_frac_range(s: str) -> Tuple[float, float]:
    a, b = s.split(":")
    return float(a), float(b)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="V2: audio-reactive terminal colors (pure engine + OSC backend).",
    )

    ap.add_argument("--scene", default="mood", choices=sorted(SCENES.keys()), help="Select a scene (see --list-scenes).")
    ap.add_argument("--list-scenes", action="store_true", help="List available scenes and exit.")

    ap.add_argument("--fifo", default="/tmp/cava.fifo")
    ap.add_argument("--bars", type=int, default=64)

    ap.add_argument("--bass", default="0.00:0.18", help="Fractional band range 0..1 (lo:hi)")
    ap.add_argument("--mids", default="0.18:0.55")
    ap.add_argument("--treble", default="0.55:1.00")

    ap.add_argument("--smooth", type=float, default=0.22, help="EMA alpha. Higher = tighter sync, lower = smoother.")
    ap.add_argument("--beat-threshold", type=float, default=0.78)

    ap.add_argument("--tty", default="/dev/tty", help="TTY to write OSC to (works in background).")
    ap.add_argument("--terminator", default="auto", choices=["auto", "st", "bel"])
    ap.add_argument("--fps-cap", type=float, default=20.0)
    ap.add_argument("--min-rgb-delta", type=int, default=4)

    ap.add_argument(
        "--silence-threshold",
        type=float,
        default=0.04,
        help="If smoothed global energy stays below this, stop animating (and optionally reset).",
    )
    ap.add_argument(
        "--silence-seconds",
        type=float,
        default=0.6,
        help="How long energy must stay below --silence-threshold before entering silence mode.",
    )
    ap.add_argument(
        "--silence-mode",
        default="reset",
        choices=["reset", "hold"],
        help="On silence: reset terminal colors to defaults, or hold last colors.",
    )

    ap.add_argument("--no-fg", action="store_true")
    ap.add_argument("--no-bg", action="store_true")
    ap.add_argument("--no-palette", action="store_true")
    ap.add_argument("--no-baseline-query", action="store_true", help="Use fallback baseline (don’t query OSC 10/11/4).")

    args = ap.parse_args(argv)

    if args.list_scenes:
        for name in sorted(SCENES.keys()):
            print(name)
        return 0

    scene = SCENES[args.scene]

    if args.no_baseline_query:
        baseline, term_used = fallback_baseline(), "bel"
    else:
        baseline, term_used = query_baseline(args.tty, in_fd=0)

    terminator = term_used if args.terminator == "auto" else args.terminator
    channels = set()
    if not args.no_fg:
        channels.add("default_fg")
    if not args.no_bg:
        channels.add("default_bg")
    if not args.no_palette:
        channels.add("palette16")

    caps = Capabilities(
        channels=channels,
        terminator=terminator,  # type: ignore[arg-type]
        fps_cap=float(args.fps_cap),
        min_rgb_delta=int(args.min_rgb_delta),
        truecolor_likely=True,
    )

    backend = OSCBackend(tty_path=args.tty, capabilities=caps, baseline=baseline)

    extractor = SignalExtractor(
        bars=int(args.bars),
        bass_frac=_parse_frac_range(args.bass),
        mids_frac=_parse_frac_range(args.mids),
        treble_frac=_parse_frac_range(args.treble),
        smooth_alpha=float(args.smooth),
        beat_threshold=float(args.beat_threshold),
    )

    fifo_fd = open_fifo_blocking(args.fifo)
    frames = read_cava_frames(fifo_fd, int(args.bars))

    state = EngineState()
    t0 = time.time()
    last = t0
    silence_since: Optional[float] = None
    in_silence = False

    def _on_sigint(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    try:
        for raw in frames:
            now = time.time()
            t = now - t0
            dt = now - last
            last = now

            signals_ = extractor.from_frame(raw)

            if signals_.global_ < float(args.silence_threshold):
                if silence_since is None:
                    silence_since = now
                if (now - silence_since) >= float(args.silence_seconds):
                    if not in_silence:
                        in_silence = True
                        if args.silence_mode == "reset":
                            backend.reset()
                    continue
            else:
                silence_since = None
                in_silence = False

            desired, state = tick(
                dt=dt,
                signals=signals_,
                baseline=baseline,
                scene=scene,
                state=state,
                prev_fg=backend._current_fg,
                prev_bg=backend._current_bg,
            )
            backend.apply(desired)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            backend.reset()
        except Exception:
            pass
        try:
            backend.close()
        except Exception:
            pass
        try:
            os.close(fifo_fd)
        except Exception:
            pass

    return 0
