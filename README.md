Here’s a clean, concise README you can drop into the repo:

---

# 🎵 Audio-Reactive Terminal Colors

Real-time music-driven color modulation for your terminal.

This project connects **CAVA’s audio spectrum output** to your terminal using ANSI **OSC escape sequences**, causing:

* Terminal background to subtly pulse with bass
* Default foreground (prompt & normal text) to smoothly shift hue
* ANSI palette colors (0–15) to gently rotate

The result is a **living terminal aesthetic** that reacts to music without destroying readability.

Works especially well in **Cursor / VSCode integrated terminal** and modern xterm-compatible terminals.

---

## ✨ Features

* Reads raw spectrum data from CAVA
* Smooth exponential moving average (no flicker)
* HSL-based hue rotation (silk-like color glide)
* Foreground (OSC 10), Background (OSC 11), and Palette (OSC 4) control
* Per-terminal targeting via TTY
* Safe stop script that restores defaults

---

## 🧰 Requirements

* Python 3.9+
* `cava`
* A terminal that supports OSC sequences (Cursor, VSCode, iTerm2, Kitty, WezTerm, Alacritty, etc.)

---

## 🔧 CAVA Setup

Edit:

```
~/.config/cava/config
```

Set:

```ini
[output]
method = raw
raw_target = /tmp/cava.fifo
bit_format = 8bit
```

Create the FIFO once:

```bash
mkfifo /tmp/cava.fifo
```

---

## ▶️ Start

`start_music_colors.sh`

Make executable:

```bash
chmod +x start_music_colors.sh
```

Run:

```bash
./start_music_colors.sh
```

Press Enter a few times so the prompt redraws.

---

## ⏹ Stop & Reset

`stop_music_colors.sh`

Make executable:

```bash
chmod +x stop_music_colors.sh
```

---

## 🎛 Useful Flags

```bash
--tty "$(tty)"          # target current terminal
--terminator bel        # more reliable in Cursor
--fps-cap 15            # 15–25 recommended
--all-swing 30          # palette hue range
--fg-swing 30           # foreground hue range
--bg-swing 20           # background hue range
--min-rgb-delta 0       # disable thresholding (debug)
```

---

## 🧠 How It Works

1. CAVA outputs raw 8-bit amplitude bars
2. Script computes bass / mids / treble energy
3. Energy → smooth curves
4. Curves → hue offsets
5. Colors sent via OSC:

* `OSC 10` → default foreground
* `OSC 11` → background
* `OSC 4`  → palette entries

No theme files are modified.

---

## ⚠️ Notes

* Prompt only updates color when it is **redrawn** (press Enter).
* Truecolor output (`38;2`) from programs will not be affected by palette rotation.
* If the terminal ever looks odd, run the stop script.

---

## 🌈 Philosophy

Instead of mapping notes to fixed colors, this system performs **continuous hue interpolation**, producing a “breathing light” effect that feels alive but remains readable.

Think of it as a shader for your terminal.
