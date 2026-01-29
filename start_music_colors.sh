#!/usr/bin/env bash
set -euo pipefail

FIFO="/tmp/cava.fifo"
PALETTE_SCRIPT="$HOME/Projects/AudioReactiveVibeCoding/palette_swapper.py"   # adjust path if needed

LOG_DIR="$HOME/Library/Logs"
CAVA_LOG="$LOG_DIR/cava_music_colors.log"
PY_LOG="$LOG_DIR/palette_swapper.log"

mkdir -p "$LOG_DIR"

echo "🎵 Starting music-reactive terminal colors..."
echo "Logs:"
echo "  CAVA: $CAVA_LOG"
echo "  PY:   $PY_LOG"

# Ensure FIFO exists
if [[ ! -p "$FIFO" ]]; then
  rm -f "$FIFO"
  mkfifo "$FIFO"
fi

# Start cava (log stdout+stderr)
# NOTE: cava must be configured to raw_target=$FIFO
cava >>"$CAVA_LOG" 2>&1 &
CAVA_PID=$!

# Give cava a moment to start and open its outputs
sleep 0.3

# Start palette swapper (log to file, but OSC goes to /dev/tty)
python3 "$PALETTE_SCRIPT" \
  --fifo "$FIFO" \
  --bars 64 \
  --log-file "$PY_LOG" \
  --log-level DEBUG \
  >>"$PY_LOG" 2>&1 &
PY_PID=$!

disown "$CAVA_PID" "$PY_PID"

echo "Started:"
echo "  cava PID:    $CAVA_PID"
echo "  palette PID: $PY_PID"
echo ""
echo "To stop:"
echo "  pkill cava"
echo "  pkill -f palette_swapper.py"
