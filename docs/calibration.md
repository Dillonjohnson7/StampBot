# Calibration

Neither arm stores a persistent hardware calibration — every time it connects,
the motors re-zero against the pose the arm is physically holding. Calibration
just records that zero pose.

**When prompted, manually move the arm to its zero position** (the default
sit-down pose, gripper fully closed) and press ENTER.

## One command for both arms

```bash
stampbot calibrate all
```

This runs, in order:

```bash
# Follower (B601-RS)
lerobot-calibrate \
    --robot.type=seeed_b601_rs_follower \
    --robot.port=can0 \
    --robot.id=follower1 \
    --robot.can_adapter=socketcan

# Leader (reBot Arm 102)
lerobot-calibrate \
    --teleop.type=rebot_arm_102_leader \
    --teleop.port=/dev/ttyUSB0 \
    --teleop.id=rebot_arm_102_leader
```

Calibrate one at a time with `stampbot calibrate follower` /
`stampbot calibrate leader`.

## Preview any command without running it

```bash
stampbot --dry-run calibrate all
```

## Fixing reversed joints

If, during teleop, a joint moves **opposite** to the leader, flip its sign in
`configs/stampbot.local.yaml`:

```yaml
leader:
  joint_directions: {"shoulder_pan": -1, "wrist_roll": -1, "gripper": -6}
```

Joint names: `shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_yaw,
wrist_roll, gripper`. The gripper carries a scale (e.g. `-6`) to widen its range
to the follower.

Next: [data-collection.md](./data-collection.md).
