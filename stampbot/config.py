"""Load StampBot config and turn it into LeRobot CLI flags.

One YAML drives every command. `stampbot.local.yaml` (gitignored) overrides
`stampbot.yaml` so each person can keep their own ports without a merge.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install the toolkit with `pip install -e .` "
        "(or `pip install pyyaml`)."
    ) from e

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "configs"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load stampbot.yaml, then overlay stampbot.local.yaml if it exists."""
    base_path = Path(path) if path else CONFIG_DIR / "stampbot.yaml"
    if not base_path.exists():
        raise SystemExit(f"Config not found: {base_path}")
    cfg = yaml.safe_load(base_path.read_text()) or {}

    local = base_path.with_name("stampbot.local.yaml")
    if path is None and local.exists():
        cfg = _deep_merge(cfg, yaml.safe_load(local.read_text()) or {})
    return cfg


# --- flag builders ----------------------------------------------------------

def robot_flags(cfg: dict) -> list[str]:
    f = cfg["follower"]
    flags = [
        f"--robot.type={f['type']}",
        f"--robot.port={f['port']}",
        f"--robot.id={f['id']}",
    ]
    if f.get("can_adapter"):
        flags.append(f"--robot.can_adapter={f['can_adapter']}")
    cams = cfg.get("cameras") or {}
    if cams:
        flags.append("--robot.cameras=" + json.dumps(cams, separators=(",", ":")))
    return flags


def teleop_flags(cfg: dict) -> list[str]:
    t = cfg["leader"]
    flags = [
        f"--teleop.type={t['type']}",
        f"--teleop.port={t['port']}",
        f"--teleop.id={t['id']}",
    ]
    jd = t.get("joint_directions")
    if jd:
        flags.append("--teleop.joint_directions=" + json.dumps(jd, separators=(",", ":")))
    return flags


def dataset_flags(cfg: dict, *, repo_id: str | None = None) -> list[str]:
    d = cfg["dataset"]
    rid = repo_id or d["repo_id"]
    flags = [
        f"--dataset.repo_id={rid}",
        f"--dataset.single_task={d['single_task']}",
        f"--dataset.fps={d['fps']}",
        f"--dataset.num_episodes={d['num_episodes']}",
        f"--dataset.episode_time_s={d['episode_time_s']}",
        f"--dataset.reset_time_s={d['reset_time_s']}",
        f"--dataset.push_to_hub={str(bool(d.get('push_to_hub', False))).lower()}",
    ]
    if d.get("root"):
        flags.append(f"--dataset.root={d['root']}")
    return flags
