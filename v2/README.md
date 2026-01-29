## V2 (pure engine + IO backend)

This directory is an organized rewrite based on `Ideas.md`:

- Inputs (impure) → pure engine → DesiredFrame → OSC backend (impure)
- Baseline (fg/bg/palette16) queried once when possible (with safe fallbacks)
- Scenes bundle BG/FG/palette effects + constraints

### Quick start

1) Configure CAVA raw output to a FIFO (same as V1):

```ini
[output]
method = raw
raw_target = /tmp/cava.fifo
bit_format = 8bit
```

2) Create the FIFO once:

```bash
mkfifo /tmp/cava.fifo
```

3) Run:

```bash
python3 v2/run.py --scene mood
```

Alternative:

```bash
PYTHONPATH=v2 python3 -m music_colors_v2 --scene mood
```

List scenes:

```bash
python3 v2/run.py --list-scenes
```

If your terminal echoes OSC query replies (looks like `10;rgb:...` in the shell), either run via `start_music_colors_v2.sh` (baseline query off by default) or pass `--no-baseline-query` to the Python command.

Stop with Ctrl+C (it will attempt to reset colors).

### Notes

- If OSC baseline queries don’t work in your terminal, use `--no-baseline-query`.
- To avoid touching certain channels: `--no-fg`, `--no-bg`, `--no-palette`.
- If you want the terminal to be completely still when it’s quiet, use the silence gate (defaults: `--silence-threshold 0.04 --silence-seconds 0.6 --silence-mode reset`).
- Scenes are now audio-driven (no time-based LFO drift). For the most “CAVA-like” look, use `--scene spectrum` (maps low→high bands across palette indices).
