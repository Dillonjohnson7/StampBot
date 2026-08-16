#!/usr/bin/env bash
# XyloBot setup. Installs the `xb`/`xylobot` CLI. LeRobot + the RS plugin are
# NOT installed here — the B601-RS uses a specific `rebot_lerobot` + plugin build
# (see docs/hardware-bringup.md). The right move is to install XyloBot INTO that
# existing environment.
#
# The rebot arms use uv, so this prefers `uv pip` (a `uv venv` has no `pip`).
# Falls back to python venv + pip if uv isn't installed.
#
#   # activate your working rebot_lerobot .venv first, then:
#   ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

HAVE_UV=0
command -v uv >/dev/null 2>&1 && HAVE_UV=1

pip_install() {  # editable-install the toolkit into the active env
  if [[ $HAVE_UV -eq 1 ]]; then uv pip install -e .; else python -m pip install -e .; fi
}

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "==> Installing into active venv: $VIRTUAL_ENV  (uv=$HAVE_UV)"
  pip_install
elif [[ $HAVE_UV -eq 1 ]]; then
  echo "==> No venv active — creating ./.venv with uv (Python 3.10)"
  [[ -d .venv ]] || uv venv --python 3.10
  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install -e .
else
  echo "==> No venv active and uv not found — creating ./.venv with python venv"
  PY="${PYTHON:-python3}"
  [[ -d .venv ]] || "$PY" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -e .
fi

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
echo "  2) xb doctor"
echo "  3) xb can-up → xb calibrate all → xb teleop"
