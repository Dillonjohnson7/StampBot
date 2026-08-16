# Data collection SOP — recording hand-stamping demonstrations

The task: the stamp is built into the end-effector, and the arm must **find a
person's hand and gently press the stamp onto the back of it**. Good demos are
the whole game for imitation learning. This is the SOP for a clean dataset.

## Before you record

1. Complete [hardware bring-up](./hardware-bringup.md) — PCAN driver, CAN up,
   MotorBridge motor init (all 7 joints online).
2. `stampbot can-up` then `stampbot doctor` — everything ✅.
3. `stampbot calibrate all` — one-time on RS (see [calibration.md](./calibration.md)).
4. `stampbot teleop --display` — confirm the follower tracks the leader and the
   camera(s) clearly see the hand region. Fix any reversed joints.

## Safety (you are pressing on a person)

- **Start with a stand-in**, not a real hand: a foam block, a mannequin hand, or
  your own gloved hand behind a barrier, until the motion is reliable.
- Keep teleop/rollout **speeds low**. Keep an **e-stop / kill** within reach and
  the 48V supply switch accessible.
- Demonstrate a **light, brief contact** — a soft press, then retract. Never a
  hard or sustained push. The policy imitates your force profile, so gentle
  demos → gentle policy.
- During `stampbot eval`, run the **base** (non-recording) strategy first at
  short `--duration`, with a stand-in hand, before any real hand.

## Scene setup (keep it consistent, vary the hand)

- Mount the camera(s) so the **hand region is always in view**: a wrist camera
  sees the approach/contact; a second (front/overhead) camera sees the whole
  workspace and the hand.
- Consistent, diffuse lighting; avoid moving shadows and glare on skin.
- **Vary what you want to generalize over:** hand position within the reachable
  zone, hand orientation, left/right hand, different people/skin tones, sleeve
  vs. bare wrist. Variation you record is variation the policy can handle;
  variation you *don't* record becomes a failure mode.
- Keep the **contact target consistent** (e.g. back of the hand) so the label is
  unambiguous.

## Record

```bash
stampbot record            # uses num_episodes from the config
stampbot record -n 10      # quick batch of 10
stampbot record --resume   # add episodes (requires dataset.root; see below)
```

During recording, LeRobot's keyboard controls (`→`/`n` next, `←`/`r` re-record,
`ESC`/`q` stop) let you drop a bad episode and redo it. Use them — don't keep
sloppy demos.

> **Resuming** needs `dataset.root` set in your config, and on resume
> `num_episodes` means the number of **additional** episodes, not the new total.

## What makes a good hand-stamp demo

- **One clean intent:** locate hand → approach → gentle press → brief hold →
  retract.
- **Smooth, moderate speed.** Jerky teleop is hard to imitate and unsafe near a hand.
- **Show the contact clearly** on camera — the press is the information-rich
  moment. Approach from a consistent direction.
- **Recover naturally** from a near-miss (re-approach) instead of stopping —
  recoveries are valuable training signal.
- **Reset identically** during the `reset_time_s` window: move the hand to a new
  position, arm back to a home pose.

## How many?

- ACT gives a working policy from **~50** solid demos. Start there; aim for
  spread across hand positions (e.g. ~10 per zone).
- Quality and diversity beat raw count. 50 clean, varied demos > 150 sloppy ones.

## Verify the dataset

```bash
stampbot visualize --episode 0     # view frames + action traces
stampbot replay --episode 0        # replay on the arm — use a STAND-IN hand, clear the area
```

Datasets push to the Hugging Face Hub automatically when `push_to_hub: true`.
When replays look right, move on to training.
