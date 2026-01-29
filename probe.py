#!/usr/bin/env python3
"""
term_probe.py — best-effort terminal capability probe → prints JSON

Updates vs prior version:
- Fixes the big bug where probe replies (DA/OSC) can leak into the terminal by
  reading/draining from STDIN in raw/nonblocking mode while probing.
- Adds high-signal OSC query probes for:
    - default foreground (OSC 10;?)
    - default background (OSC 11;?)
    - palette indices (OSC 4;idx;?) for a few representative idx
  and tries both BEL and ST terminators.
- Keeps DA1/DA2 (now correctly captured when supported).
- Makes XTGETTCAP optional via --deep (kept, but de-emphasized).
- Adds useful session signals:
    - tty name, isatty flags, terminal size
    - more env keys commonly used for terminal identification (including VSCode)
- Adds a "recommended" block that suggests how to configure your color modulator.

Design constraints:
- Never hangs: all reads are timeout-bounded.
- Best-effort: many terminals do not support queries; we report unknown.
- Avoids printing visible junk: we drain probe replies so they don't appear before JSON.

Usage:
  ./term_probe.py
  ./term_probe.py --deep         # includes XTGETTCAP
  TERM_PROBE_TTY=/dev/tty ./term_probe.py   # override output TTY for sending probes
"""

import argparse
import errno
import fcntl
import json
import os
import platform
import re
import shlex
import struct
import subprocess
import sys
import termios
import time
from dataclasses import dataclass, asdict
from select import select
from typing import Dict, Optional, Tuple, Any, List


# ------------------------- helpers -------------------------

def getenv_keys(keys: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k in keys:
        v = os.environ.get(k)
        if v is not None:
            out[k] = v
    return out


def run_cmd(cmd: str, timeout: float = 0.35) -> Tuple[int, str, str]:
    """
    Run a small local command; return (rc, stdout, stderr).
    """
    try:
        p = subprocess.run(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 127, "", str(e)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def open_tty_w(path: str) -> Optional[int]:
    """
    Open TTY for writing probe escape sequences. Read replies from stdin (fd 0),
    which is where terminals generally deliver responses.
    """
    try:
        return os.open(path, os.O_WRONLY | os.O_NOCTTY)
    except Exception:
        return None


def write_bytes(fd: int, data: bytes) -> bool:
    try:
        os.write(fd, data)
        return True
    except Exception:
        return False


def set_nonblocking(fd: int, enable: bool) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    if enable:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    else:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


class RawMode:
    """
    Temporarily put a TTY fd into raw-ish mode so terminal replies can be read
    immediately without echo/canonical line buffering.
    """
    def __init__(self, fd: int):
        self.fd = fd
        self._old = None

    def __enter__(self):
        if not os.isatty(self.fd):
            return self
        self._old = termios.tcgetattr(self.fd)
        new = termios.tcgetattr(self.fd)

        # iflag
        new[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK |
                    termios.ISTRIP | termios.INLCR | termios.IGNCR |
                    termios.ICRNL | termios.IXON)
        # oflag
        new[1] &= ~termios.OPOST
        # cflag
        new[2] |= termios.CS8
        # lflag
        new[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON |
                    termios.ISIG | termios.IEXTEN)
        # cc: make reads return quickly
        new[6][termios.VMIN] = 0
        new[6][termios.VTIME] = 1  # tenths of seconds

        termios.tcsetattr(self.fd, termios.TCSANOW, new)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._old is not None and os.isatty(self.fd):
            termios.tcsetattr(self.fd, termios.TCSANOW, self._old)


def read_available(fd: int, timeout: float = 0.10, max_bytes: int = 16384) -> bytes:
    """
    Read whatever arrives within timeout; returns bytes (possibly empty).
    fd should usually be stdin (0) for terminal query replies.
    """
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


def drain_stdin(fd: int, drain_timeout: float = 0.08) -> bytes:
    """
    Drain any pending bytes from stdin quickly (nonblocking).
    This prevents probe replies from "leaking" into the user's terminal.
    """
    collected = bytearray()
    end = time.time() + drain_timeout
    while time.time() < end:
        chunk = read_available(fd, timeout=0.01)
        if not chunk:
            break
        collected.extend(chunk)
    return bytes(collected)


def get_tty_name(fd: int) -> Optional[str]:
    try:
        return os.ttyname(fd)
    except Exception:
        return None


def get_winsize(fd: int) -> Optional[Dict[str, int]]:
    try:
        s = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\x00" * 8)
        rows, cols, xpixels, ypixels = struct.unpack("HHHH", s)
        return {"rows": rows, "cols": cols, "xpixels": xpixels, "ypixels": ypixels}
    except Exception:
        return None


# ------------------------- active probes -------------------------

@dataclass
class ActiveProbeResult:
    supported: bool
    raw_reply: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    terminator_used: Optional[str] = None  # "bel" or "st"


def _decode_bytes(b: bytes) -> str:
    return b.decode("utf-8", "replace")


def probe_device_attributes(out_fd: int, in_fd: int) -> Dict[str, ActiveProbeResult]:
    """
    DA1: CSI c      -> reply CSI ? ... c
    DA2: CSI > c    -> reply CSI > ... c
    """
    out: Dict[str, ActiveProbeResult] = {}

    # DA1
    write_bytes(out_fd, b"\x1b[c")
    rep = read_available(in_fd, timeout=0.14)
    s = _decode_bytes(rep)
    m = re.search(r"\x1b\[(\?[\d;]+)c", s)
    if m:
        out["da1"] = ActiveProbeResult(
            supported=True,
            raw_reply=m.group(0),
            parsed={"params": m.group(1)},
            note=None,
        )
    else:
        out["da1"] = ActiveProbeResult(
            supported=False,
            raw_reply=s if s else None,
            note="No DA1 match captured (may still be supported; output racing or different reply form).",
        )

    # DA2
    write_bytes(out_fd, b"\x1b[>c")
    rep2 = read_available(in_fd, timeout=0.14)
    s2 = _decode_bytes(rep2)
    m2 = re.search(r"\x1b\[(>[\d;]+)c", s2)
    if m2:
        out["da2"] = ActiveProbeResult(
            supported=True,
            raw_reply=m2.group(0),
            parsed={"params": m2.group(1)},
            note=None,
        )
    else:
        out["da2"] = ActiveProbeResult(
            supported=False,
            raw_reply=s2 if s2 else None,
            note="No DA2 match captured (may still be supported; output racing or different reply form).",
        )

    return out


def _osc(seq: str, terminator: str) -> bytes:
    # terminator: "st" -> ESC \ , "bel" -> BEL
    if terminator == "st":
        return (seq + "\x1b\\").encode("ascii")
    return (seq + "\x07").encode("ascii")


def osc_query_default_fg(terminator: str) -> bytes:
    # OSC 10 ; ?  ST/BEL
    return _osc("\x1b]10;?", terminator)


def osc_query_default_bg(terminator: str) -> bytes:
    # OSC 11 ; ?  ST/BEL
    return _osc("\x1b]11;?", terminator)


def osc_query_palette(idx: int, terminator: str) -> bytes:
    # OSC 4 ; idx ; ?  ST/BEL
    return _osc(f"\x1b]4;{idx};?", terminator)


def parse_osc_color_reply(s: str) -> Optional[Dict[str, Any]]:
    """
    Parse typical OSC color replies.
    Common forms:
      OSC 10;rgb:RRRR/GGGG/BBBB ST
      OSC 11;rgb:... ST
      OSC 4;idx;rgb:... ST

    Many terminals use 16-bit-per-channel hex groups (RRRR), but sometimes 8-bit.
    We return raw plus parsed channels if possible.
    """
    # Example: ESC ] 10 ; rgb:ffff/ffff/ffff BEL/ST
    m = re.search(r"\x1b\](?P<code>\d+);(?P<body>.*?)(?:\x07|\x1b\\)", s, re.DOTALL)
    if not m:
        return None

    code = m.group("code")
    body = m.group("body")

    # Palette reply may include index: "4;1;rgb:..."
    # Sometimes nested; handle a few patterns.
    info: Dict[str, Any] = {"osc": code, "body": body}

    rgb_m = re.search(r"rgb:(?P<r>[0-9a-fA-F]{2,4})/(?P<g>[0-9a-fA-F]{2,4})/(?P<b>[0-9a-fA-F]{2,4})", body)
    if rgb_m:
        rhex, ghex, bhex = rgb_m.group("r"), rgb_m.group("g"), rgb_m.group("b")

        def norm(x: str) -> int:
            # If 4 hex digits, scale 0..65535 to 0..255 by >> 8.
            if len(x) == 4:
                return int(x, 16) >> 8
            return int(x, 16)

        info["rgb"] = {"r": norm(rhex), "g": norm(ghex), "b": norm(bhex), "raw": f"{rhex}/{ghex}/{bhex}"}

    # Palette index (if present)
    idx_m = re.search(r"^(\d+);(\d+);", body)
    if idx_m:
        info["palette"] = {"index": int(idx_m.group(2))}

    return info


def osc_query_probe(out_fd: int, in_fd: int, payload: bytes, timeout: float, terminator: str) -> ActiveProbeResult:
    """
    Send an OSC query, read reply, parse if possible.
    """
    write_bytes(out_fd, payload)
    rep = read_available(in_fd, timeout=timeout)
    s = _decode_bytes(rep)

    parsed = parse_osc_color_reply(s) if s else None
    if parsed:
        return ActiveProbeResult(
            supported=True,
            raw_reply=parsed.get("body") if parsed.get("body") else s,
            parsed=parsed,
            note=None,
            terminator_used=terminator,
        )

    # If we got *something* but couldn't parse, still record it for debugging.
    return ActiveProbeResult(
        supported=False,
        raw_reply=s if s else None,
        parsed=None,
        note="No parseable OSC color reply captured.",
        terminator_used=terminator,
    )


def probe_osc_queries(out_fd: int, in_fd: int) -> Dict[str, Any]:
    """
    Try OSC query forms for default fg/bg and a few palette slots.
    Tries ST first, then BEL if ST yields no parseable result.
    """
    results: Dict[str, Any] = {"tried": [], "results": {}}

    def try_both(name: str, mkpayload):
        # Try ST then BEL
        for term in ("st", "bel"):
            results["tried"].append({"name": name, "terminator": term})
            res = osc_query_probe(out_fd, in_fd, mkpayload(term), timeout=0.16, terminator=term)
            # Consider supported if parsed was obtained
            if res.supported and res.parsed is not None:
                results["results"][name] = asdict(res)
                return
            # If terminal replied but we couldn't parse, keep the best raw reply
            if name not in results["results"] and (res.raw_reply is not None):
                results["results"][name] = asdict(res)
        if name not in results["results"]:
            results["results"][name] = asdict(ActiveProbeResult(
                supported=False,
                raw_reply=None,
                parsed=None,
                note="No OSC reply captured (terminal may not support queries).",
            ))

    try_both("osc10_default_fg", lambda t: osc_query_default_fg(t))
    try_both("osc11_default_bg", lambda t: osc_query_default_bg(t))

    # Palette query: sample a few high-signal indices
    for idx in (0, 1, 2, 4, 7, 8, 15):
        try_both(f"osc4_palette_{idx}", lambda t, i=idx: osc_query_palette(i, t))

    return results


def _xtgettcap_encode(cap: str) -> bytes:
    return cap.encode("ascii").hex().encode("ascii")


def probe_xtgettcap(out_fd: int, in_fd: int, caps=("Tc", "RGB", "setaf", "setab")) -> ActiveProbeResult:
    """
    XTGETTCAP query (optional, not widely supported):
      DCS + q <hex(cap)> ST   => ESC P + q <hex> ESC \

    Many terminals don't implement it; keep behind --deep.
    """
    parsed: Dict[str, Any] = {}
    raw_collect = ""

    for cap in caps:
        query = b"\x1bP+q" + _xtgettcap_encode(cap) + b"\x1b\\"
        write_bytes(out_fd, query)
        rep = read_available(in_fd, timeout=0.16)
        s = _decode_bytes(rep)
        raw_collect += s

        m = re.search(r"\x1bP(?P<body>.*?)(?:\x1b\\)", s, re.DOTALL)
        if not m:
            continue
        body = m.group("body")
        if "+r" not in body:
            continue

        hex_m = re.search(r"\+r([0-9A-Fa-f=]+)", body)
        if not hex_m:
            continue
        hex_payload = hex_m.group(1)

        if "=" in hex_payload:
            left, right = hex_payload.split("=", 1)
        else:
            left, right = hex_payload, ""

        try:
            cap_name = bytes.fromhex(left).decode("ascii", "replace")
        except Exception:
            cap_name = f"(hex:{left})"

        val = None
        if right:
            try:
                val = bytes.fromhex(right).decode("ascii", "replace")
            except Exception:
                val = f"(hex:{right})"

        parsed[cap_name] = val if val is not None else True

    supported = bool(parsed)
    note = None if supported else "No XTGETTCAP replies detected (not supported by many terminals)."
    return ActiveProbeResult(supported=supported, raw_reply=raw_collect or None, parsed=parsed or None, note=note)


# ------------------------- inference -------------------------

def infer_truecolor(env: Dict[str, str], tput_colors: Optional[int], osc: Dict[str, Any], xt_caps: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Truecolor verdict with confidence & reasons.
    """
    reasons: List[str] = []
    val = False
    confidence = 0.30

    colorterm = env.get("COLORTERM", "").lower()
    if "truecolor" in colorterm or "24bit" in colorterm:
        val = True
        confidence = max(confidence, 0.85)
        reasons.append(f"COLORTERM={env.get('COLORTERM')}")

    term = env.get("TERM", "").lower()
    if any(x in term for x in ("xterm-kitty", "alacritty", "wezterm", "foot")):
        confidence = max(confidence, 0.70)
        reasons.append(f"TERM heuristic ({env.get('TERM')})")

    if tput_colors is not None and tput_colors >= 256:
        confidence = max(confidence, 0.50)
        reasons.append(f"tput colors={tput_colors} (weak signal)")

    # XTGETTCAP 'Tc' / 'RGB' is strong if present
    if xt_caps:
        if xt_caps.get("Tc") is True or xt_caps.get("Tc") == "":
            val = True
            confidence = max(confidence, 0.95)
            reasons.append("XTGETTCAP Tc present")
        if "RGB" in xt_caps:
            confidence = max(confidence, 0.90)
            reasons.append("XTGETTCAP RGB present")

    # Inside tmux can require config; lower confidence
    if env.get("TMUX"):
        confidence = min(confidence, 0.80)
        reasons.append("Inside tmux (truecolor may require config)")

    return {"value": val, "confidence": round(confidence, 2), "reasons": reasons}


def infer_color_depth(tput_colors: Optional[int]) -> Dict[str, Any]:
    if tput_colors is None:
        return {"value": None, "confidence": 0.20, "reasons": ["tput colors unavailable"]}
    if tput_colors >= 256:
        return {"value": 256, "confidence": 0.90, "reasons": [f"tput colors={tput_colors}"]}
    if tput_colors >= 16:
        return {"value": 16, "confidence": 0.80, "reasons": [f"tput colors={tput_colors}"]}
    if tput_colors >= 8:
        return {"value": 8, "confidence": 0.80, "reasons": [f"tput colors={tput_colors}"]}
    return {"value": tput_colors, "confidence": 0.60, "reasons": [f"tput colors={tput_colors}"]}


def infer_osc_support_from_queries(osc_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    If we successfully query OSC colors, that is a strong signal that OSC works.
    If not, we keep it unknown (many terminals accept-set but do not support query).
    """
    results = osc_results.get("results", {}) if osc_results else {}
    supported = False
    got_any_reply = False
    reasons: List[str] = []

    for k, v in results.items():
        if not isinstance(v, dict):
            continue
        if v.get("raw_reply") is not None:
            got_any_reply = True
        if v.get("supported") and v.get("parsed") is not None:
            supported = True
            reasons.append(f"{k} query replied")
    if supported:
        return {"value": True, "confidence": 0.95, "reasons": reasons}
    if got_any_reply:
        return {"value": "unknown", "confidence": 0.60, "reasons": ["Got OSC-ish reply but couldn't parse reliably."]}
    return {"value": "unknown", "confidence": 0.50, "reasons": ["OSC queries not supported or no reply captured (set may still work)."]}


def infer_osc_likelihood(env: Dict[str, str]) -> Dict[str, Any]:
    """
    Heuristic when we can't confirm via OSC query.
    """
    reasons: List[str] = []
    term = (env.get("TERM") or "").lower()
    if term in ("dumb", ""):
        return {"value": False, "confidence": 0.95, "reasons": ["TERM=dumb/empty"]}

    conf = 0.75
    reasons.append("Mainstream TERM (heuristic)")

    if env.get("TERM_PROGRAM") in ("Apple_Terminal", "iTerm.app", "WezTerm", "vscode"):
        conf = 0.90
        reasons.append(f"TERM_PROGRAM={env.get('TERM_PROGRAM')}")

    if env.get("VTE_VERSION"):
        conf = 0.90
        reasons.append(f"VTE_VERSION={env.get('VTE_VERSION')}")

    if env.get("TMUX"):
        conf = 0.75
        reasons.append("Inside tmux (usually passes OSC, depends on config)")

    return {"value": True, "confidence": round(conf, 2), "reasons": reasons}


def recommend(env: Dict[str, str], tput_colors: Optional[int], osc_query_support: Dict[str, Any], truecolor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make actionable recommendations for your color driver.
    """
    term_program = env.get("TERM_PROGRAM", "").lower()
    in_tmux = bool(env.get("TMUX"))

    # Terminator: if any OSC query succeeded with a terminator, prefer it; else default ST.
    term_pref = "st"
    if osc_query_support and isinstance(osc_query_support, dict):
        results = osc_query_support.get("results", {})
        for v in results.values():
            if isinstance(v, dict) and v.get("supported") and v.get("terminator_used"):
                term_pref = v["terminator_used"]
                break

    # Conservative defaults for VSCode/others
    fps = 20.0
    min_delta = 2
    if term_program == "vscode":
        fps = 15.0
        min_delta = 2
    if in_tmux:
        fps = min(fps, 15.0)
        min_delta = max(min_delta, 2)

    # Feature toggles
    enable_palette_0_15 = True if (tput_colors or 0) >= 16 else False
    enable_256 = True if (tput_colors or 0) >= 256 else False

    # OSC set is widely supported even when queries fail; treat "unknown" as still "try".
    osc_try = True
    if env.get("TERM", "").lower() in ("dumb", ""):
        osc_try = False

    # If truecolor is strongly present, palette swapping may affect less; still do it for broad coverage.
    tc_conf = float(truecolor.get("confidence", 0.0)) if isinstance(truecolor, dict) else 0.0

    return {
        "terminator": term_pref,
        "try_osc_10_11": osc_try,
        "try_osc_4_palette_0_15": enable_palette_0_15,
        "try_osc_4_palette_16_255": False,  # only flip true if you *confirm* a terminal supports it
        "color_depth": tput_colors,
        "likely_truecolor": True if (truecolor.get("value") is True and tc_conf >= 0.7) else False,
        "notes": [
            "OSC queries often unsupported even when OSC set works; treat query failure as 'unknown', not 'no'.",
            "If truecolor dominates your app output, consider pushing apps to 256-color mode or using a PTY filter to rewrite RGB.",
        ],
        "suggested_driver_defaults": {
            "fps_cap": fps,
            "min_rgb_delta": min_delta,
        },
    }


# ------------------------- main -------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Probe terminal capabilities; print JSON.")
    ap.add_argument("--tty-out", default=os.environ.get("TERM_PROBE_TTY", "/dev/tty"),
                    help="TTY path to write probes to (default: TERM_PROBE_TTY or /dev/tty).")
    ap.add_argument("--deep", action="store_true", help="Enable optional low-support probes (XTGETTCAP).")
    ap.add_argument("--no-active", action="store_true", help="Skip active probes entirely.")
    args = ap.parse_args()

    t0 = time.time()

    stdin_fd = 0
    stdout_fd = 1

    session = {
        "stdin_isatty": os.isatty(stdin_fd),
        "stdout_isatty": os.isatty(stdout_fd),
        "stdin_tty": get_tty_name(stdin_fd),
        "stdout_tty": get_tty_name(stdout_fd),
        "winsize": get_winsize(stdin_fd) if os.isatty(stdin_fd) else None,
    }

    env_subset_keys = [
        "TERM", "COLORTERM", "TERM_PROGRAM", "TERM_PROGRAM_VERSION",
        "VTE_VERSION", "KONSOLE_VERSION", "WT_SESSION",
        "TMUX", "STY",
        "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY",
        "INSIDE_EMACS",
        "LC_TERMINAL", "LC_TERMINAL_VERSION",
        # VSCode signals (high signal when present)
        "VSCODE_PID", "VSCODE_IPC_HOOK_CLI",
    ]
    env = getenv_keys(env_subset_keys)

    # terminfo: tput colors
    tput_colors = None
    rc, out, err = run_cmd("tput colors", timeout=0.25)
    if rc == 0 and out.isdigit():
        tput_colors = int(out)

    in_tmux = bool(env.get("TMUX"))
    in_screen = bool(env.get("STY"))
    in_ssh = bool(env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY"))

    # Active probes: write to tty-out, read replies from stdin
    out_fd = open_tty_w(args.tty_out)
    active: Dict[str, Any] = {
        "tty_out": {"path": args.tty_out, "opened": out_fd is not None},
        "device_attributes": None,
        "osc_queries": None,
        "xtgettcap": None,
        "drain": None,
    }

    xt_parsed = None
    osc_results = None

    # If stdin isn't a tty, active probing is unsafe/unreliable.
    can_probe = (not args.no_active) and (out_fd is not None) and os.isatty(stdin_fd)

    if can_probe:
        # Make stdin nonblocking + raw, and drain before/after probes to avoid reply leakage.
        old_nonblock = False
        try:
            # Best effort: set nonblocking (track previous state crudely)
            set_nonblocking(stdin_fd, True)
            old_nonblock = True
        except Exception:
            old_nonblock = False

        pre = b""
        post = b""
        try:
            with RawMode(stdin_fd):
                pre = drain_stdin(stdin_fd, drain_timeout=0.05)

                da = probe_device_attributes(out_fd, stdin_fd)
                active["device_attributes"] = {k: asdict(v) for k, v in da.items()}

                # OSC query probes (high signal)
                osc_results = probe_osc_queries(out_fd, stdin_fd)
                active["osc_queries"] = osc_results

                # Optional low-support probe
                if args.deep:
                    xt = probe_xtgettcap(out_fd, stdin_fd)
                    active["xtgettcap"] = asdict(xt)
                    xt_parsed = xt.parsed if xt and xt.parsed else None
                else:
                    active["xtgettcap"] = {"skipped": True, "note": "Use --deep to enable XTGETTCAP (low support)."}

                post = drain_stdin(stdin_fd, drain_timeout=0.08)

        except Exception as e:
            active["error"] = str(e)
        finally:
            active["drain"] = {
                "pre_bytes": len(pre),
                "post_bytes": len(post),
                "pre_sample": _decode_bytes(pre[:160]) if pre else None,
                "post_sample": _decode_bytes(post[:160]) if post else None,
            }
            if old_nonblock:
                try:
                    set_nonblocking(stdin_fd, False)
                except Exception:
                    pass
    else:
        reasons = []
        if args.no_active:
            reasons.append("--no-active")
        if out_fd is None:
            reasons.append("tty_out not opened")
        if not os.isatty(stdin_fd):
            reasons.append("stdin not a tty")
        active["skipped"] = True
        active["skip_reasons"] = reasons

    if out_fd is not None:
        try:
            os.close(out_fd)
        except Exception:
            pass

    # Inference: prefer OSC-query confirmation; fall back to heuristic
    osc_query_support = infer_osc_support_from_queries(osc_results) if osc_results else {"value": "unknown", "confidence": 0.5, "reasons": ["No OSC query results."]}
    osc_likely = infer_osc_likelihood(env)

    truecolor = infer_truecolor(env, tput_colors, osc_results or {}, xt_parsed)
    inferred = {
        "color_depth": infer_color_depth(tput_colors),
        "truecolor": truecolor,
        "osc_query_support": osc_query_support,
        "osc_likely_supported": osc_likely,
        "multiplexer": {"tmux": in_tmux, "screen": in_screen},
        "ssh": in_ssh,
    }

    info = {
        "timestamp": now_iso(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "session": session,
        "env": env,
        "terminfo": {
            "tput_colors": tput_colors,
            "tput_rc": rc,
            "tput_err": err or None,
        },
        "active_probes": active,
        "inferred": inferred,
        "recommended": recommend(env, tput_colors, osc_results or {}, truecolor),
        "probe_duration_ms": int((time.time() - t0) * 1000),
    }

    print(json.dumps(info, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
