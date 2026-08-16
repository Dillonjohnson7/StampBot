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

## Setup: two people

Collection is teleoperated, so a human is always in the loop:

- **Operator** drives the **leader** arm; the follower (with the stamp) mirrors
  it live.
- **Helper** presents their **hand** under the follower and **moves it to a new
  position each demo** (the guided recorder prints a cycling position hint).

Because the operator is in direct control the whole time, recording on a real
hand is fine — just work at low speed and demonstrate a **light, brief contact**
(soft press, then retract). The policy imitates your force profile, so gentle
demos → a gentle policy.

## Safety

- Keep speeds low; keep an **e-stop / kill** within reach and the 48V supply
  switch accessible.
- The autonomous step is where caution matters: during `stampbot eval`, run the
  **base** (non-recording) strategy first at short `--duration` against a
  **stand-in** (foam/mannequin) before any real hand.

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

## Record (guided flow)

`stampbot record` runs a guided, step-by-step recorder — you press ENTER to
start each demo, ENTER again to stop (so a demo is exactly as long as it needs
to be), then keep or redo it:

```bash
stampbot record            # target = num_episodes from config
stampbot record -n 10      # just 10 demos this run
stampbot record --display  # also show the camera feeds (rerun)
```

Each episode:

```
EPISODE 12   (demo 3 of 10 this run · 11 saved total)
STEP 1 · SET UP
 • Start state: hand at RIGHT, back of hand up  (cycles every demo)
 • Move the LEADER arm to your start pose (follower mirrors live).
 • Have the helper present the hand; drive the task deliberately.
 >> Press ENTER to START recording (q = finish session):
 🔴 RECORDING… perform the task now.
 >> Press ENTER to STOP.
 Captured ~430 frames (14.3s).
STEP 3 · KEEP THIS DEMO?  [ENTER]=keep · r=redo · q=save & quit:
 ✓ Saved. Good episodes total: 12
STEP 4 · RESET — reset the scene / hand position for the next demo.
```

The start-state hints come from `dataset.start_states` in the config — edit them
to match how your helper should place the hand. On finish, the dataset is
finalized and (if `push_to_hub: true`) uploaded.

**Prefer the plain LeRobot loop?** `stampbot record --raw` runs `lerobot-record`
instead (supports `--resume`, which needs `dataset.root` set; on resume
`num_episodes` means *additional* episodes, not the new total).

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
