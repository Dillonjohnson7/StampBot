#!/usr/bin/env bash
# StampBot one-shot setup. Creates a venv, installs the toolkit + LeRobot,
# and drops a local config for you to edit.
#
#   ./setup.sh            # full install (toolkit + LeRobot + reBot drivers)
#   ./setup.sh --lite     # toolkit only (no LeRobot) — for editing/config work
set -euo pipefail
cd "$(dirname "$0")"

LITE=0
[[ "${1:-}" == "--lite" ]] && LITE=1

PY="${PYTHON:-python3}"
echo "==> Using interpreter: $($PY --version)"

if [[ ! -d .venv ]]; then
  echo "==> Creating virtualenv (.venv)"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip

if [[ $LITE -eq 1 ]]; then
  echo "==> Installing toolkit only (lite)"
  pip install -e .
else
  echo "==> Installing toolkit + LeRobot + reBot drivers"
  pip install -e ".[robot]"
fi

if [[ ! -f configs/stampbot.local.yaml ]]; then
  echo "==> Creating configs/stampbot.local.yaml (your private overrides)"
  cp configs/stampbot.yaml configs/stampbot.local.yaml
fi

echo
echo "Done. Next:"
echo "  1) source .venv/bin/activate"
echo "  2) edit configs/stampbot.local.yaml  (ports, repo_id, cameras)"
echo "  3) stampbot doctor"
echo "  4) stampbot find-ports   →   stampbot calibrate all   →   stampbot teleop"
