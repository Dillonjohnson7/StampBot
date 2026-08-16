# Contributing to XyloBot

## Setup

```bash
./setup.sh          # or ./setup.sh --lite for toolkit-only (no LeRobot/hardware)
source .venv/bin/activate
```

## Config

- **Never commit ports.** Edit `configs/stampbot.local.yaml` (gitignored), not
  the tracked `configs/stampbot.yaml`. The CLI merges local over base.
- Keep `configs/stampbot.yaml` as sensible RS defaults + documentation.

## Style

- `ruff check stampbot` before pushing (`make lint`).
- The CLI wraps LeRobot commands — keep wrappers thin and config-driven. If you
  add a flag, add it to the config, not hardcoded in `cli.py`.
- Test wrappers without hardware using `--dry-run`.

## Datasets & models

- Don't commit datasets or checkpoints (they're gitignored). Push them to the
  Hugging Face Hub and reference by `repo_id`.

## PRs

- Small, focused PRs. Note which LeRobot version you tested against — the
  reBot/LeRobot CLIs evolve.
