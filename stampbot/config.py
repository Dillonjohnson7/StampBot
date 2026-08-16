"""Load XyloBot config and turn it into LeRobot CLI flags.

One YAML drives every command. `stampbot.local.yaml` (gitignored) overrides
`stampbot.yaml` so each person can keep their own ports without a merge.
"""
from __future__ import annotations

import json
import os
import sys
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

    # Overlay the gitignored local config whenever it exists and isn't the base
    # file itself — including when --config explicitly names the default file, so
    # `xb --config configs/stampbot.yaml ...` behaves like plain `xb ...`.
    local = base_path.with_name("stampbot.local.yaml")
    if local.exists() and local.resolve() != base_path.resolve():
        cfg = _deep_merge(cfg, yaml.safe_load(local.read_text()) or {})
    return cfg


# --- flag builders ----------------------------------------------------------

def robot_flags(cfg: dict, *, cameras: bool = True) -> list[str]:
    """Follower --robot.* flags.

    Set cameras=False for commands that only drive the motors (calibrate,
    replay): attaching cameras there forces LeRobot to open them and can block
    the command if a camera index is wrong. Recording and policy rollout need
    the cameras (they are the observation), so cameras=True there.
    """
    f = cfg["follower"]
    flags = [
        f"--robot.type={f['type']}",
        f"--robot.port={f['port']}",
        f"--robot.id={f['id']}",
    ]
    if f.get("can_adapter"):
        flags.append(f"--robot.can_adapter={f['can_adapter']}")
    cams = cfg.get("cameras") or {}
    if cameras and cams:
        flags.append("--robot.cameras=" + json.dumps(cams, separators=(",", ":")))
    return flags


def teleop_flags(cfg: dict) -> list[str]:
    t = cfg["leader"]
    flags = [
        f"--teleop.type={t['type']}",
        f"--teleop.port={t['port']}",
        f"--teleop.id={t['id']}",
    ]
    # The RS leader (rebot_arm_102_leader) has NO joint_directions field —
    # emitting --teleop.joint_directions would crash the leader config. Direction
    # fixes live on the follower. Warn (don't emit) if it's set.
    if t.get("joint_directions"):
        print("warning: leader.joint_directions is ignored on the RS leader "
              "(no such field) — set direction fixes on the follower instead.",
              file=sys.stderr)
    return flags


def dataset_flags(cfg: dict, *, repo_id: str | None = None, root: str | None = None,
                  num_episodes: int | None = None, episode_time_s: int | None = None,
                  push_to_hub: bool | None = None) -> list[str]:
    d = cfg["dataset"]
    rid = repo_id or d["repo_id"]
    root_v = root if root is not None else d.get("root")
    ne = num_episodes if num_episodes is not None else d["num_episodes"]
    ets = episode_time_s if episode_time_s is not None else d["episode_time_s"]
    push = d.get("push_to_hub", False) if push_to_hub is None else push_to_hub
    flags = [
        f"--dataset.repo_id={rid}",
        f"--dataset.single_task={d['single_task']}",
        f"--dataset.fps={d['fps']}",
        f"--dataset.num_episodes={ne}",
        f"--dataset.episode_time_s={ets}",
        f"--dataset.reset_time_s={d['reset_time_s']}",
        f"--dataset.push_to_hub={str(bool(push)).lower()}",
    ]
    if root_v:
        flags.append(f"--dataset.root={root_v}")
    return flags
