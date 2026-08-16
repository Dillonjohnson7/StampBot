#!/usr/bin/env bash
# StampBot setup. Installs the `stampbot` CLI. LeRobot + the RS plugin are NOT
# installed here — the B601-RS uses a specific `rebot_lerobot` + plugin build
# (see docs/hardware-bringup.md). The right move is to install StampBot INTO
# that existing environment.
#
#   # activate your working rebot_lerobot venv first, then:
#   ./setup.sh
#
# If no venv is active, a local .venv is created (toolkit only; you still need
# LeRobot + the RS plugin for anything that touches the arm).
set -euo pipefail
cd "$(dirname "$0")"

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "==> Installing into active venv: $VIRTUAL_ENV"
else
  echo "==> No venv active — creating ./.venv (toolkit only)"
  PY="${PYTHON:-python3}"
  [[ -d .venv ]] || "$PY" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install --upgrade pip
pip install -e .

if [[ ! -f configs/stampbot.local.yaml ]]; then
  echo "==> Creating configs/stampbot.local.yaml (your private overrides)"
  cp configs/stampbot.yaml configs/stampbot.local.yaml
fi

echo
if python -c "import lerobot" 2>/dev/null; then
  echo "LeRobot detected ✅"
else
  echo "⚠  LeRobot not importable in this env."
  echo "   Install LeRobot + the RS plugin (lerobot_robot_seeed_b601, Python 3.10)"
  echo "   per docs/hardware-bringup.md, then re-run in that venv."
fi
echo
echo "Next:"
echo "  1) edit configs/stampbot.local.yaml  (ports, repo_id, cameras)"
echo "  2) stampbot doctor"
echo "  3) stampbot can-up → stampbot calibrate all → stampbot teleop --display"
