#!/usr/bin/env bash
set -euo pipefail

FIFO="/tmp/cava.fifo"
SCRIPT="$PWD/v2/run.py"

LOG_DIR="$HOME/Library/Logs"
CAVA_LOG="$LOG_DIR/cava_music_colors.log"
PY_LOG="$LOG_DIR/music_colors_v2.log"

mkdir -p "$LOG_DIR"

echo "🎵 Starting AudioReactiveVibe V2..."
echo "Logs:"
echo "  CAVA: $CAVA_LOG"
echo "  PY:   $PY_LOG"

if [[ ! -p "$FIFO" ]]; then
  rm -f "$FIFO"
  mkfifo "$FIFO"
fi

cava >>"$CAVA_LOG" 2>&1 &
CAVA_PID=$!

sleep 0.3

python3 "$SCRIPT" \
  --scene mood \
  --fifo "$FIFO" \
  --bars 64 \
  --terminator auto \
  >>"$PY_LOG" 2>&1 &
PY_PID=$!

disown "$CAVA_PID" "$PY_PID"

echo "Started:"
echo "  cava PID:    $CAVA_PID"
echo "  v2 script PID: $PY_PID"
echo ""
echo "To stop:"
echo "  ./stop_music_colors_v2.sh"
