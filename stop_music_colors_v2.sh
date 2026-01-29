#!/usr/bin/env bash
set -euo pipefail

echo "Stopping AudioReactiveVibe V2..."

pkill cava 2>/dev/null
pkill -f "v2/run.py" 2>/dev/null

printf "\e]104\a"
printf "\e]110\a"
printf "\e]111\a"
printf "\e]112\a"

echo "Reset colors and stopped processes."
