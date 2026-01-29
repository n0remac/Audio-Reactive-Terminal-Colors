from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .color import rgb_distance
from .types import Baseline, Capabilities, DesiredFrame, RGB, Terminator


def _osc(seq: str, terminator: Terminator) -> bytes:
    if terminator == "st":
        return (seq + "\x1b\\").encode("ascii")
    return (seq + "\x07").encode("ascii")


def osc_set_default_fg(c: RGB, terminator: Terminator) -> bytes:
    return _osc(f"\x1b]10;{c.to_hex()}", terminator)


def osc_set_default_bg(c: RGB, terminator: Terminator) -> bytes:
    return _osc(f"\x1b]11;{c.to_hex()}", terminator)


def osc_set_palette(i: int, c: RGB, terminator: Terminator) -> bytes:
    return _osc(f"\x1b]4;{i};{c.to_osc_rgb_triplet()}", terminator)


def osc_reset_all(terminator: Terminator) -> bytes:
    return b"".join(
        [
            _osc("\x1b]104", terminator),
            _osc("\x1b]110", terminator),
            _osc("\x1b]111", terminator),
            _osc("\x1b]112", terminator),
        ]
    )


@dataclass
class OSCBackend:
    tty_path: str
    capabilities: Capabilities
    baseline: Baseline

    _tty_fd: Optional[int] = None
    _last_emit: float = 0.0
    _current_fg: RGB = None  # type: ignore[assignment]
    _current_bg: RGB = None  # type: ignore[assignment]
    _current_pal: Dict[int, RGB] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._current_fg = self.baseline.default_fg
        self._current_bg = self.baseline.default_bg
        self._current_pal = {i: c for i, c in enumerate(self.baseline.palette16)}

    def open(self) -> None:
        if self._tty_fd is None:
            self._tty_fd = os.open(self.tty_path, os.O_WRONLY | os.O_NOCTTY)

    def close(self) -> None:
        if self._tty_fd is not None:
            os.close(self._tty_fd)
            self._tty_fd = None

    def _write(self, payload: bytes) -> None:
        if not payload:
            return
        self.open()
        assert self._tty_fd is not None
        os.write(self._tty_fd, payload)

    def reset(self) -> None:
        self._write(osc_reset_all(self.capabilities.terminator))

    def apply(self, frame: DesiredFrame) -> None:
        now = time.time()
        if self.capabilities.fps_cap > 0:
            min_dt = 1.0 / self.capabilities.fps_cap
            if now - self._last_emit < min_dt:
                return

        term = self.capabilities.terminator
        out = bytearray()

        if "default_bg" in self.capabilities.channels and frame.bg is not None:
            if rgb_distance(self._current_bg, frame.bg) >= self.capabilities.min_rgb_delta:
                out.extend(osc_set_default_bg(frame.bg, term))
                self._current_bg = frame.bg

        if "default_fg" in self.capabilities.channels and frame.fg is not None:
            if rgb_distance(self._current_fg, frame.fg) >= self.capabilities.min_rgb_delta:
                out.extend(osc_set_default_fg(frame.fg, term))
                self._current_fg = frame.fg

        if "palette16" in self.capabilities.channels and frame.palette_updates:
            for idx, c in frame.palette_updates.items():
                cur = self._current_pal.get(idx)
                if cur is None or rgb_distance(cur, c) >= self.capabilities.min_rgb_delta:
                    out.extend(osc_set_palette(idx, c, term))
                    self._current_pal[idx] = c

        self._write(bytes(out))
        self._last_emit = now

