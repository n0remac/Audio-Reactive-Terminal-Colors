#!/usr/bin/env bash

echo "Stopping music-reactive colors..."

# Kill running processes
pkill cava 2>/dev/null
pkill -f palette_swapper.py 2>/dev/null

# Reset terminal colors to defaults
# OSC 104 -> reset all palette entries
# OSC 110 -> reset default foreground
# OSC 111 -> reset default background
# OSC 112 -> reset cursor color (optional but nice)

printf "\e]104\a"
printf "\e]110\a"
printf "\e]111\a"
printf "\e]112\a"

echo "Colors reset. Processes stopped."
