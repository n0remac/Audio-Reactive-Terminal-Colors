#!/usr/bin/env bash
set -euo pipefail

SCRIPT="${SCRIPT:-$PWD/v2/run.py}"
FIFO="${FIFO:-/tmp/cava.fifo}"
LOG_DIR="$HOME/Library/Logs"
CAVA_LOG="$LOG_DIR/cava_music_colors.log"
PY_LOG="$LOG_DIR/music_colors_v2.log"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SCENE="mood"
EXTRA_ARGS=()
LIST_ONLY=0
DO_BASELINE=0

usage() {
  cat <<'EOF'
Usage: ./start_music_colors_v2.sh [--scene NAME] [--list-scenes] [--help] [-- ...extra args...]

Examples:
  ./start_music_colors_v2.sh --scene spectrum
  ./start_music_colors_v2.sh --list-scenes

Notes:
  - All extra args after recognized flags are passed to v2/run.py
  - Baseline OSC queries are OFF by default to avoid leaking replies into your shell; enable with --baseline-query
  - FIFO path defaults to /tmp/cava.fifo; override with FIFO=/path ./start_music_colors_v2.sh
  - Python defaults to python3; override with PYTHON_BIN=python3.11 ...
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scene)
      SCENE="${2:-mood}"
      shift 2
      ;;
    --baseline-query)
      DO_BASELINE=1
      shift
      ;;
    --list-scenes)
      LIST_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

mkdir -p "$LOG_DIR"

if [[ "$LIST_ONLY" -eq 1 ]]; then
  echo "Available scenes:"
  "$PYTHON_BIN" "$SCRIPT" --list-scenes
  exit 0
fi

echo "🎵 Starting AudioReactiveVibe V2..."
echo "Scene: $SCENE"
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

"$PYTHON_BIN" "$SCRIPT" \
  --scene "$SCENE" \
  --fifo "$FIFO" \
  --bars 64 \
  --terminator auto \
  $(if [[ "$DO_BASELINE" -eq 0 ]]; then printf -- '--no-baseline-query '; fi) \
  $(if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then printf '%q ' "${EXTRA_ARGS[@]}"; fi) \
  >>"$PY_LOG" 2>&1 &
PY_PID=$!

disown "$CAVA_PID" "$PY_PID"

echo "Started:"
echo "  cava PID:     $CAVA_PID"
echo "  v2 script PID:$PY_PID"
echo ""
echo "To stop:"
echo "  ./stop_music_colors_v2.sh"
