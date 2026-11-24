#!/bin/zsh
set -eu
cd "${0:A:h}"
VIP_BUNDLED_PYTHON='/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
if [[ -x .venv-paddle/bin/python && -f .runtime/paddle-ready.json ]]; then
  VIP_TRIAL_PYTHON="$PWD/.venv-paddle/bin/python"
elif [[ -x .venv/bin/python ]]; then
  VIP_TRIAL_PYTHON="$PWD/.venv/bin/python"
elif [[ -x "$VIP_BUNDLED_PYTHON" ]]; then
  VIP_TRIAL_PYTHON="$VIP_BUNDLED_PYTHON"
else
  VIP_TRIAL_PYTHON="$(command -v python3)"
fi
exec "$VIP_TRIAL_PYTHON" -u scripts/team_trial.py
