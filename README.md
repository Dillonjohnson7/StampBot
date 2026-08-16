# StampBot 🤖✋

A hand-stamping robot that learns to pick up a stamp, ink it, and press it onto paper — trained by imitation learning from human teleoperation demonstrations.

## Stack

| Component | Choice |
|---|---|
| **Robot arm (follower)** | [reBot Arm B601-RS](https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/) — 6+1 DoF, Robstride motors, 2.5 kg payload, ±0.1 mm repeatability |
| **Teleop (leader)** | Leader-follower — Star Arm 102 leader arm |
| **Framework** | [LeRobot](https://github.com/huggingface/lerobot) (Hugging Face) |
| **Policy** | ACT (Action Chunking Transformer) for prototyping → π0.5 (VLA) finetune |
| **Cameras** | TBD (wrist + overhead recommended) |

## Why this design

- **ACT first, π0.5 later.** ACT trains from scratch on a single consumer GPU with as few as ~50 demos — ideal for nailing the data pipeline end-to-end. Once teleop → record → train → deploy is proven, the same LeRobot dataset can be reused to finetune π0.5 for language conditioning and generalization.
- **Leader-follower teleop** gives clean joint-space demonstrations, which is exactly what ACT consumes.

## The task

A single, repeatable manipulation sequence:

1. Locate and grasp the stamp
2. Press the stamp onto the ink pad
3. Move to the paper
4. Press to stamp
5. Return the stamp / reset

## Roadmap

- [ ] **Hardware bring-up** — assemble B601-RS follower + Star Arm 102 leader, wire 48V/15A PSU, calibrate motors
- [ ] **LeRobot setup** — install, configure the arm driver, verify teleop loop
- [ ] **Camera setup** — mount + register wrist and overhead cameras
- [ ] **Data collection** — record 50+ stamping demonstrations
- [ ] **Train ACT** — train and evaluate the ACT policy
- [ ] **Deploy + evaluate** — closed-loop rollout on the real arm, measure success rate
- [ ] **π0.5 finetune** — reuse dataset to finetune π0.5, compare

## Repository layout

```
StampBot/
├── configs/        # LeRobot + policy configs (arm, cameras, training)
├── data/           # recorded datasets (gitignored; pushed to HF Hub)
├── scripts/        # record / train / eval / deploy helpers
├── notebooks/      # analysis + visualization
└── docs/           # hardware bring-up notes, calibration, wiring
```

## References

- [reBot Arm B601-RS Quick Start](https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/)
- [reBot B601 in LeRobot](https://huggingface.co/docs/lerobot/en/rebot_b601)
- [LeRobot ACT policy docs](https://deepwiki.com/huggingface/lerobot/4.2-act-policy)
- [reBot-DevArm (open hardware)](https://github.com/Seeed-Projects/reBot-DevArm)

## License

TBD
