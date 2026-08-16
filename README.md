# StampBot 🤖✋

The stamp is built into the end-effector. The arm learns to **find a person's
hand and gently press the stamp onto it** — trained by imitation learning from
teleoperated demos with [LeRobot](https://github.com/huggingface/lerobot).

Edit one config file and you have the whole loop: teleop → record → train → deploy.

## Stack

| | |
|---|---|
| **Follower** | [reBot Arm B601-RS](https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/) — 6+1 DoF, RobStride motors over SocketCAN |
| **Leader** | reBot Arm 102 (leader-follower teleop) |
| **Policy** | ACT to start; π0 / π0.5 finetune later on the same dataset |

## Quickstart

```bash
git clone https://github.com/Dillonjohnson7/StampBot.git && cd StampBot
# activate your rebot_lerobot venv first (LeRobot + the RS plugin) — see
# docs/hardware-bringup.md — then install this CLI into it:
./setup.sh                              # pip install -e . (into the active venv)
$EDITOR configs/stampbot.local.yaml     # your ports, repo_id, cameras

stampbot can-up && stampbot doctor      # bring up CAN, check everything is ✅
stampbot calibrate all                  # one-time on RS
stampbot teleop --display               # confirm the follower tracks the leader
stampbot record                         # collect demos
stampbot train
stampbot eval --policy-path outputs/train/act_stamping/checkpoints/last/pretrained_model
```

**First time on RS hardware, do [hardware bring-up](docs/hardware-bringup.md) first** —
PCAN driver, CAN interface, and the MotorBridge motor init are prerequisites.

## Commands

Every command reads `configs/stampbot.yaml` (your `stampbot.local.yaml` overrides
it), so you set ports once. Add `--dry-run` to any command to print the exact
LeRobot call instead of running it; `make help` lists `make` equivalents.

| Command | Does |
|---|---|
| `stampbot doctor` | Check CLIs, CAN, ports, calibration, GPU |
| `stampbot find-ports` | Find the leader's USB port |
| `stampbot can-up` | Bring up SocketCAN (`can0`) for the RS follower |
| `stampbot calibrate {all,follower,leader}` | Home-pose calibration (one-time on RS) |
| `stampbot teleop [--display]` | Drive the follower with the leader |
| `stampbot record [-n N] [--display]` | Record demos — **guided** flow (`--raw` for plain CLI) |
| `stampbot replay --episode N` | Replay an episode on the arm |
| `stampbot visualize --episode N` | View an episode |
| `stampbot train [--policy act\|pi0\|pi05]` | Train the policy |
| `stampbot eval --policy-path P [--record]` | Run a trained policy on the arm |

## The task

Stamp fixed to the end-effector: **locate the hand → approach → gently press →
brief hold → retract.** The policy has to find the hand at varying positions and
make a *light-force* contact on a person — read the
[safety notes](docs/data-collection.md#safety) before running on a real hand.

ACT is the fast path — it trains from scratch on one GPU from ~50 demos, so it's
the quickest way to prove the pipeline end to end. The same dataset then feeds a
π0/π0.5 finetune (`stampbot train --policy pi05`), so nothing gets thrown away.

## Docs

- [Hardware bring-up](docs/hardware-bringup.md) — power, PCAN, CAN, MotorBridge
- [Calibration](docs/calibration.md) — the RS one-time home-pose step
- [Data collection](docs/data-collection.md) — recording good demos + safety
- [Troubleshooting](docs/troubleshooting.md)

## License

Apache-2.0 (software); hardware is CERN-OHL-W 2.0 upstream. See [LICENSE](LICENSE).
