#!/bin/zsh
set -eu
kit_dir="${0:A:h}"
if ! command -v python3 >/dev/null 2>&1; then
  print -u2 "Install Python 3, then run this launcher again."
  exit 1
fi
exec python3 "$kit_dir/mac-relay-control.py" start DEV
