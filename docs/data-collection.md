# Data collection SOP — recording stamping demonstrations

Good demos are the whole game for imitation learning. This is the standard
operating procedure for building a clean StampBot dataset.

## Before you record

1. `stampbot can-up` — bring up the CAN interface.
2. `stampbot doctor` — everything ✅.
3. `stampbot calibrate all` — zero both arms.
4. `stampbot teleop --display` — confirm the follower tracks the leader and both
   camera feeds look right. Fix any reversed joints (see calibration.md).

## Scene setup (keep it consistent)

- Fix the stamp, ink pad, and paper positions with tape marks or a jig.
- Consistent, diffuse lighting — avoid moving shadows and glare on the paper.
- Wrist camera sees the stamp/contact; top camera sees the whole workspace.
- Decide up front what you'll vary (paper position?) vs. keep fixed. Variation
  you record is variation the policy can learn to handle; variation you *don't*
  record becomes a failure mode.

## Record

```bash
stampbot record            # uses num_episodes from the config
stampbot record -n 10      # quick batch of 10
stampbot record --resume   # add more episodes to an existing dataset
```

This runs `lerobot-record` with your arm + camera + dataset settings and
`--display_data=true`. During recording, LeRobot's keyboard controls let you
end an episode early, re-record a bad one, and step through the reset window.

## What makes a good stamping demo

- **One clean intent per episode:** grasp stamp → ink → stamp paper → reset.
- **Smooth, moderate speed.** Jerky teleop is hard to imitate.
- **Show the contact clearly** — the press onto the ink pad and onto the paper
  are the hardest, most information-rich moments. Don't rush them.
- **Recover naturally** from small misses instead of stopping — recoveries are
  valuable training signal.
- **Reset the scene identically** each episode during the `reset_time_s` window.

## How many?

- ACT gives a working policy from **~50** solid demos. Start there.
- Diminishing returns come from *quality and diversity*, not raw count. 50 clean,
  varied demos beat 150 sloppy identical ones.

## Verify the dataset

```bash
stampbot visualize --episode 0     # view frames + action traces
stampbot replay --episode 0        # replay it on the real arm (clear the area!)
```

If replays look right, you're ready to [train](./troubleshooting.md#training).
Datasets push to the Hugging Face Hub automatically when `push_to_hub: true`.
