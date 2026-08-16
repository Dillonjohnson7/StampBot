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
xylobot calibrate all
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

Do one at a time with `xylobot calibrate follower` / `xylobot calibrate leader`.
Preview without running: `xylobot calibrate all --dry-run`.

## Reversed joints

On the RS the **leader has no `joint_directions` field** — direction handling
lives on the **follower**. If a joint moves opposite to the leader during teleop,
it's a follower motor-direction issue: it's baked into the reBot follower plugin
config (`joint_directions` on the follower, set by the plugin), not something you
flip in `stampbot.local.yaml`. If a joint is genuinely reversed, re-check the
MotorBridge motor init / calibration; don't add `leader.joint_directions` (the
CLI ignores it and warns).

Next: [data-collection.md](./data-collection.md).
