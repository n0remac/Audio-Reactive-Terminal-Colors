from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Iterable, Tuple, List

from .types import Signals
from .color import clamp01


def open_fifo_blocking(path: str) -> int:
    return os.open(path, os.O_RDONLY)


def read_cava_frames(fd: int, bars: int) -> Iterable[bytes]:
    buf = bytearray()
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            time.sleep(0.02)
            continue
        for b in chunk:
            if b == 10:  # '\n'
                continue
            buf.append(b)
        while len(buf) >= bars:
            frame = bytes(buf[:bars])
            del buf[:bars]
            yield frame


def _band_energy(frame: bytes, lo: int, hi: int) -> float:
    lo = max(0, lo)
    hi = min(len(frame), hi)
    if hi <= lo:
        return 0.0
    s = 0
    for v in frame[lo:hi]:
        s += v
    return (s / (hi - lo)) / 255.0


def _range_from_frac(frac: Tuple[float, float], bars: int) -> Tuple[int, int]:
    a, b = frac
    lo = int(max(0.0, min(1.0, a)) * bars)
    hi = int(max(0.0, min(1.0, b)) * bars)
    if hi < lo:
        lo, hi = hi, lo
    return lo, max(lo + 1, hi)


@dataclass
class EMA:
    alpha: float = 0.12
    value: float = 0.0

    def update(self, x: float) -> float:
        self.value = (1.0 - self.alpha) * self.value + self.alpha * x
        return self.value


@dataclass
class SignalExtractor:
    bars: int
    bass_frac: Tuple[float, float] = (0.00, 0.18)
    mids_frac: Tuple[float, float] = (0.18, 0.55)
    treble_frac: Tuple[float, float] = (0.55, 1.00)
    smooth_alpha: float = 0.12
    beat_threshold: float = 0.78

    _bass: EMA = None  # type: ignore[assignment]
    _mids: EMA = None  # type: ignore[assignment]
    _treble: EMA = None  # type: ignore[assignment]
    _global: EMA = None  # type: ignore[assignment]
    _bands16: List[EMA] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._bass = EMA(alpha=self.smooth_alpha)
        self._mids = EMA(alpha=self.smooth_alpha)
        self._treble = EMA(alpha=self.smooth_alpha)
        self._global = EMA(alpha=self.smooth_alpha)
        self._bands16 = [EMA(alpha=self.smooth_alpha) for _ in range(16)]

    def from_frame(self, frame: bytes) -> Signals:
        # Collapse the full-resolution CAVA bars into 16 stable bands for mapping
        # directly across the available palette indices.
        bars = self.bars
        group = max(1, bars // 16)
        bands16: List[float] = []
        for i in range(16):
            lo = i * group
            hi = bars if i == 15 else (i + 1) * group
            bands16.append(_band_energy(frame, lo, hi))

        bass_lo, bass_hi = _range_from_frac(self.bass_frac, self.bars)
        mids_lo, mids_hi = _range_from_frac(self.mids_frac, self.bars)
        treb_lo, treb_hi = _range_from_frac(self.treble_frac, self.bars)

        bass = _band_energy(frame, bass_lo, bass_hi)
        mids = _band_energy(frame, mids_lo, mids_hi)
        treble = _band_energy(frame, treb_lo, treb_hi)
        global_ = (bass * 0.45 + mids * 0.35 + treble * 0.20)

        bass_s = self._bass.update(bass)
        mids_s = self._mids.update(mids)
        treble_s = self._treble.update(treble)
        global_s = self._global.update(global_)
        bands16_s = [clamp01(self._bands16[i].update(bands16[i])) for i in range(16)]

        beat = bass_s > self.beat_threshold and global_s > 0.40
        return Signals(
            bands16=bands16_s,
            bass=clamp01(bass_s),
            mids=clamp01(mids_s),
            treble=clamp01(treble_s),
            global_=clamp01(global_s),
            beat=beat,
        )
