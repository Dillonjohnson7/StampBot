# StampBot 🤖✋

A hand-stamping robot that learns to pick up a stamp, ink it, and press it onto
paper — trained by imitation learning from human teleoperation demonstrations.

Clone it, edit one config file, and you have a full data-collection → training →
deployment toolkit ready to go.

## Stack

| Component | Choice |
|---|---|
| **Follower arm** | [reBot Arm B601-RS](https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/) — 6+1 DoF, Robstride motors, SocketCAN, 2.5 kg payload, ±0.1 mm |
| **Leader arm** | reBot Arm 102 (Star Arm 102) — leader-follower teleop |
| **Framework** | [LeRobot](https://github.com/huggingface/lerobot) |
| **Policy** | ACT (prototype) → π0 / π0.5 (VLA finetune) |

## Quickstart

```bash
git clone https://github.com/Dillonjohnson7/StampBot.git
cd StampBot

# 1. Install (venv + toolkit + LeRobot + reBot drivers)
./setup.sh

# 2. Edit YOUR ports / repo_id / cameras
#    (setup.sh made configs/stampbot.local.yaml for you)
$EDITOR configs/stampbot.local.yaml

# 3. Bring up hardware and verify
source .venv/bin/activate
stampbot can-up            # RS follower uses SocketCAN (can0)
stampbot doctor            # everything should be ✅

# 4. Calibrate → teleop → record
stampbot calibrate all
stampbot teleop --display  # confirm the follower tracks the leader
stampbot record            # collect demonstrations

# 5. Train and deploy
stampbot train
stampbot eval --policy-path outputs/train/act_stamping/checkpoints/last/pretrained_model
```

> Prefer `make`? `make help` lists equivalent targets.
> Want to see a command without running it? Prefix any command with `--dry-run`.

## The `stampbot` CLI

Every tool reads from `configs/stampbot.yaml` (overridden by your private
`stampbot.local.yaml`), so you configure ports **once** and everything works.

| Command | What it does |
|---|---|
| `stampbot doctor` | Check env: CLIs installed, CAN up, ports present, GPU |
| `stampbot find-ports` | Discover USB serial ports (`lerobot-find-port`) |
| `stampbot can-up` | Bring up the SocketCAN interface for the RS follower |
| `stampbot calibrate {all,follower,leader}` | Re-zero the arm(s) |
| `stampbot teleop [--display]` | Drive follower with the leader |
| `stampbot record [-n N] [--resume]` | Record demonstrations |
| `stampbot replay --episode N` | Replay a recorded episode on the arm |
| `stampbot visualize --episode N` | View a recorded episode |
| `stampbot train [--policy act\|pi0]` | Train the policy |
| `stampbot eval --policy-path P` | Run a trained policy on the real arm |

Global flags: `--config PATH`, `--dry-run`.

## The task

A single, repeatable manipulation sequence:
**grasp the stamp → press on the ink pad → move to the paper → press → reset.**

## Why ACT first, π0.5 later

ACT trains from scratch on a single consumer GPU with as few as ~50 demos —
perfect for proving the teleop → record → train → deploy loop end to end. The
same LeRobot dataset then feeds a π0/π0.5 finetune for language conditioning and
generalization, so nothing is thrown away. Switch with `stampbot train --policy pi0`.

## Docs

- [Hardware bring-up](docs/hardware-bringup.md) — power, CAN, ports, adapters
- [Calibration](docs/calibration.md) — zeroing, reversed joints
- [Data collection SOP](docs/data-collection.md) — how to record good demos
- [Troubleshooting](docs/troubleshooting.md) — CAN, cameras, training

## Repository layout

```
StampBot/
├── stampbot/         # the `stampbot` CLI (config-driven LeRobot wrappers)
├── configs/          # stampbot.yaml — the one file you edit
├── docs/             # bring-up, calibration, data-collection, troubleshooting
├── scripts/          # extra helper scripts
├── notebooks/        # dataset analysis / visualization
├── data/             # recorded datasets (gitignored; pushed to HF Hub)
├── setup.sh          # one-shot installer
└── Makefile          # convenience targets
```

## References

- [reBot B601-RS in LeRobot](https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/)
- [LeRobot ACT policy](https://deepwiki.com/huggingface/lerobot/4.2-act-policy)
- [reBot-DevArm (open hardware)](https://github.com/Seeed-Projects/reBot-DevArm)

## License

Apache-2.0 (software). Hardware is CERN-OHL-W 2.0 upstream. See [LICENSE](LICENSE).
