#!/usr/bin/env python
"""End-to-end smoke test of the XyloBot training pipeline — no hardware needed.

Builds a tiny SYNTHETIC LeRobotDataset (7-joint state/action + scene/wrist
cameras, random data) using the exact same API calls the recorder uses
(hw_to_dataset_features → build_dataset_frame → add_frame → save_episode →
finalize), then runs `lerobot-train` (policy=act) on it for a few steps on the
GPU. Proves: dataset format, train CLI, ACT construction with our camera keys,
forward/backward on CUDA, checkpoint save.

Usage (inside the rebot_lerobot venv):
    python scripts/smoke_train.py [--steps 60] [--device cuda]

Everything lives under /tmp/xb_smoke*; nothing touches your real datasets.
Designed to be run `nice -n 19` so it never competes with a live record session.
"""
from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np


def _imp(name, *mods):
    for m in mods:
        try:
            return getattr(importlib.import_module(m), name)
        except Exception:
            continue
    sys.exit(f"smoke: cannot import {name} from {mods} — run inside the rebot_lerobot venv")


LeRobotDataset = _imp("LeRobotDataset", "lerobot.datasets.lerobot_dataset", "lerobot.datasets")
hw_to_dataset_features = _imp("hw_to_dataset_features",
                              "lerobot.datasets.utils", "lerobot.utils.feature_utils")
build_dataset_frame = _imp("build_dataset_frame",
                           "lerobot.datasets.utils", "lerobot.utils.feature_utils")

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex",
          "wrist_yaw", "wrist_roll", "gripper"]
CAMS = {"scene": (120, 160, 3), "wrist": (120, 160, 3)}  # small = fast smoke
TASK = "Pick up the mallet and strike the xylophone to play a note."
REPO_ID = "local/xb_smoke"
ROOT = Path("/tmp/xb_smoke_ds")
OUT = Path("/tmp/xb_smoke_train")
FPS = 30


def build_dataset(episodes: int, frames: int) -> None:
    for p in (ROOT, OUT):
        shutil.rmtree(p, ignore_errors=True)
    action_hw = {f"{j}.pos": float for j in JOINTS}
    obs_hw = {**{f"{j}.pos": float for j in JOINTS}, **CAMS}
    features = {**hw_to_dataset_features(action_hw, "action"),
                **hw_to_dataset_features(obs_hw, "observation")}
    ds = LeRobotDataset.create(repo_id=REPO_ID, fps=FPS, features=features,
                               robot_type="seeed_b601_rs_follower", use_videos=True,
                               image_writer_threads=2, root=ROOT)
    rng = np.random.default_rng(0)
    for ep in range(episodes):
        for t in range(frames):
            joints = {f"{j}.pos": float(rng.normal()) for j in JOINTS}
            obs = {**joints, **{c: rng.integers(0, 255, s, dtype=np.uint8)
                                for c, s in CAMS.items()}}
            act = {f"{j}.pos": float(rng.normal()) for j in JOINTS}
            frame = {**build_dataset_frame(ds.features, obs, prefix="observation"),
                     **build_dataset_frame(ds.features, act, prefix="action"),
                     "task": TASK}
            ds.add_frame(frame)
        ds.save_episode()
        print(f"smoke: episode {ep + 1}/{episodes} saved ({frames} frames)")
    ds.finalize()
    print(f"smoke: dataset ready at {ROOT} ({ds.num_episodes} episodes)")


def train(steps: int, device: str) -> int:
    train_bin = shutil.which("lerobot-train") or str(Path(sys.executable).parent / "lerobot-train")
    cmd = [train_bin,
           f"--dataset.repo_id={REPO_ID}", f"--dataset.root={ROOT}",
           "--policy.type=act", f"--policy.device={device}",
           "--policy.push_to_hub=false",
           f"--output_dir={OUT}", "--job_name=xb_smoke",
           "--batch_size=2", f"--steps={steps}", f"--save_freq={steps}",
           "--num_workers=0", "--wandb.enable=false"]
    print("smoke: running", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--episodes", type=int, default=2)
    ap.add_argument("--frames", type=int, default=60)
    args = ap.parse_args()

    build_dataset(args.episodes, args.frames)
    rc = train(args.steps, args.device)
    ckpts = list(OUT.rglob("pretrained_model")) if OUT.exists() else []
    if rc == 0 and ckpts:
        print(f"\nSMOKE TEST PASSED ✅  checkpoint: {ckpts[0]}")
        return 0
    print(f"\nSMOKE TEST FAILED ✗  (train rc={rc}, checkpoints={len(ckpts)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
