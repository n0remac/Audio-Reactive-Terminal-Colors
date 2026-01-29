from __future__ import annotations

import errno
import fcntl
import os
import re
import termios
import time
from select import select
from typing import List, Optional, Tuple

from .types import Baseline, RGB, Terminator


def _osc(seq: str, terminator: Terminator) -> bytes:
    if terminator == "st":
        return (seq + "\x1b\\").encode("ascii")
    return (seq + "\x07").encode("ascii")


def _set_nonblocking(fd: int, enable: bool) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    if enable:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    else:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


class _RawMode:
    def __init__(self, fd: int):
        self.fd = fd
        self._old = None

    def __enter__(self):
        if not os.isatty(self.fd):
            return self
        self._old = termios.tcgetattr(self.fd)
        new = termios.tcgetattr(self.fd)
        new[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK |
                    termios.ISTRIP | termios.INLCR | termios.IGNCR |
                    termios.ICRNL | termios.IXON)
        new[1] &= ~termios.OPOST
        new[2] |= termios.CS8
        new[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON |
                    termios.ISIG | termios.IEXTEN)
        new[6][termios.VMIN] = 0
        new[6][termios.VTIME] = 1
        termios.tcsetattr(self.fd, termios.TCSANOW, new)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._old is not None and os.isatty(self.fd):
            termios.tcsetattr(self.fd, termios.TCSANOW, self._old)


def _read_available(fd: int, timeout: float, max_bytes: int = 8192) -> bytes:
    buf = bytearray()
    end = time.time() + timeout
    while time.time() < end and len(buf) < max_bytes:
        r, _, _ = select([fd], [], [], max(0.0, end - time.time()))
        if not r:
            break
        try:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buf.extend(chunk)
        except BlockingIOError:
            break
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                break
            break
    return bytes(buf)


def _parse_osc_rgb_reply(payload: str) -> Optional[RGB]:
    m = re.search(r"rgb:(?P<r>[0-9a-fA-F]{2,4})/(?P<g>[0-9a-fA-F]{2,4})/(?P<b>[0-9a-fA-F]{2,4})", payload)
    if not m:
        return None

    def norm(x: str) -> int:
        if len(x) == 4:
            return int(x, 16) >> 8
        return int(x, 16)

    return RGB(norm(m.group("r")), norm(m.group("g")), norm(m.group("b"))).clamped()


def _query(out_fd: int, in_fd: int, seq: bytes, timeout: float) -> str:
    # Best-effort drain so replies from prior probes don’t leak/mix.
    _read_available(in_fd, timeout=0.01)
    os.write(out_fd, seq)
    raw = _read_available(in_fd, timeout=timeout)
    try:
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def _osc_query_default_fg(term: Terminator) -> bytes:
    return _osc("\x1b]10;?", term)


def _osc_query_default_bg(term: Terminator) -> bytes:
    return _osc("\x1b]11;?", term)


def _osc_query_palette(i: int, term: Terminator) -> bytes:
    return _osc(f"\x1b]4;{i};?", term)


def query_baseline(tty_path: str, *, in_fd: int = 0) -> Tuple[Baseline, Terminator]:
    fallback = fallback_baseline()

    try:
        out_fd = os.open(tty_path, os.O_WRONLY | os.O_NOCTTY)
    except Exception:
        return fallback, "bel"

    try:
        with _RawMode(in_fd):
            _set_nonblocking(in_fd, True)

            for term in ("st", "bel"):
                fg_s = _query(out_fd, in_fd, _osc_query_default_fg(term), timeout=0.12)
                bg_s = _query(out_fd, in_fd, _osc_query_default_bg(term), timeout=0.12)

                fg = _parse_osc_rgb_reply(fg_s)
                bg = _parse_osc_rgb_reply(bg_s)
                if fg is None or bg is None:
                    continue

                pal: List[RGB] = []
                ok = True
                for i in range(16):
                    s = _query(out_fd, in_fd, _osc_query_palette(i, term), timeout=0.10)
                    c = _parse_osc_rgb_reply(s)
                    if c is None:
                        ok = False
                        break
                    pal.append(c)
                if not ok:
                    continue

                return Baseline(default_fg=fg, default_bg=bg, palette16=pal), term
    finally:
        try:
            _set_nonblocking(in_fd, False)
        except Exception:
            pass
        try:
            os.close(out_fd)
        except Exception:
            pass

    return fallback, "bel"


def fallback_baseline() -> Baseline:
    return Baseline(
        default_fg=RGB(0xD0, 0xD0, 0xD0),
        default_bg=RGB(0x12, 0x12, 0x12),
        palette16=[
            RGB(0x00, 0x00, 0x00), RGB(0xcd, 0x00, 0x00), RGB(0x00, 0xcd, 0x00), RGB(0xcd, 0xcd, 0x00),
            RGB(0x00, 0x00, 0xee), RGB(0xcd, 0x00, 0xcd), RGB(0x00, 0xcd, 0xcd), RGB(0xe5, 0xe5, 0xe5),
            RGB(0x7f, 0x7f, 0x7f), RGB(0xff, 0x00, 0x00), RGB(0x00, 0xff, 0x00), RGB(0xff, 0xff, 0x00),
            RGB(0x5c, 0x5c, 0xff), RGB(0xff, 0x00, 0xff), RGB(0x00, 0xff, 0xff), RGB(0xff, 0xff, 0xff),
        ],
    )
