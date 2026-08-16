# Calibration (RS)

RS calibration is **one-time after assembly** — unlike the SO101, which re-zeros
every connection. It's a **single home-pose** step (no range-of-motion sweep),
and it **persists to JSON** under `~/.cache/huggingface/lerobot/calibration/`,
keyed by the arm's `id`. Keep the same `id` across calibrate / record / eval
(the config already does).

**Prerequisite:** finish [hardware bring-up](./hardware-bringup.md) first —
especially the MotorBridge motor init with all 7 joints online. Calibration
won't work until the motors are up.

## Run it (follower first, then leader)

```bash
stampbot calibrate all
```

Which runs:

```bash
# Follower (B601-RS) — over CAN
lerobot-calibrate \
    --robot.type=seeed_b601_rs_follower \
    --robot.port=can0 --robot.id=follower1 --robot.can_adapter=socketcan

# Leader (reBot Arm 102) — over serial
lerobot-calibrate \
    --teleop.type=rebot_arm_102_leader \
    --teleop.port=/dev/ttyUSB0 --teleop.id=rebot_arm_102_leader
```

When prompted: **move the arm to its documented zero/home pose (gripper fully
closed), hold it still, and press Enter.** That's the whole calibration.

Do one at a time with `stampbot calibrate follower` / `stampbot calibrate leader`.
Preview without running: `stampbot calibrate all --dry-run`.

## Reversed joints

If a joint moves opposite to the leader during teleop, flip its sign in
`configs/stampbot.local.yaml`:

```yaml
leader:
  joint_directions: {"<joint>": -1}   # confirm the joint names from teleop output
```

Next: [data-collection.md](./data-collection.md).
