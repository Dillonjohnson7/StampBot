# Data collection SOP — recording xylophone demonstrations

The task: **pick up the mallet and strike the xylophone to play a note**. Good
demos are the whole game for imitation learning. This is the SOP for a clean
dataset.

## Before you record

1. Complete [hardware bring-up](./hardware-bringup.md) — PCAN driver, CAN up,
   MotorBridge motor init (all 7 joints online).
2. `xylobot can-up` then `xylobot doctor` — everything ✅.
3. `xylobot calibrate all` — one-time on RS (see [calibration.md](./calibration.md)).
4. `xylobot teleop` — confirm the follower tracks the leader and the
   camera(s) clearly see the mallet and the xylophone bars. Fix any reversed joints.

## Setup: one operator

Collection is teleoperated, so a human is always in the loop. A **single
operator** drives the **leader** arm; the follower (holding/grabbing the mallet)
mirrors it live. No helper is needed — the scene is just a xylophone and a
mallet, with nothing to present.

Work at low speed and demonstrate a **clean, gentle strike** — enough to sound
the bar, not enough to damage the mallet or the xylophone. The policy imitates
your motion, so smooth, controlled demos → a smooth, controlled policy.

## Safety

- Keep speeds low; keep an **e-stop / kill** within reach and the 48V supply
  switch accessible.
- **Keep clear of the moving arm** — the only hazard is the arm itself, so stay
  out of its swing while it's live.
- Strike **gently** so you don't damage the mallet or the xylophone bars.

## Scene setup (keep it consistent, vary the target note)

- Mount the camera(s) so the **mallet and bars are always in view**: a wrist
  camera sees the grasp and the strike; the overhead scene camera sees
  the whole workspace, the mallet, and the xylophone.
- Consistent, diffuse lighting; avoid moving shadows and glare on the bars.
- **Vary what you want to generalize over:** target note/bar (low / middle /
  high), mallet starting position, and xylophone placement within the reachable
  zone. Variation you record is variation the policy can handle; variation you
  *don't* record becomes a failure mode.
- Keep the **strike target consistent** (the center of the chosen bar) so the
  label is unambiguous.

## Record (guided flow)

`xylobot record` runs a guided, step-by-step recorder — you press ENTER to
start each demo, ENTER again to stop (so a demo is exactly as long as it needs
to be), then keep or redo it:

```bash
xylobot record            # target = num_episodes from config
xylobot record -n 10      # just 10 demos this run
xylobot record --display  # also show the camera feeds (rerun)
```

Each episode:

```
EPISODE 12   (demo 3 of 10 this run · 11 saved total)
STEP 1 · SET UP
 • Start state: target = MIDDLE bar, mallet at RIGHT  (cycles every demo)
 • Move the LEADER arm to your start pose (follower mirrors live).
 • Drive the task deliberately: grab the mallet, strike the bar.
 >> Press ENTER to START recording (q = finish session):
 🔴 RECORDING… perform the task now.
 >> Press ENTER to STOP.
 Captured ~430 frames (14.3s).
STEP 3 · KEEP THIS DEMO?  [ENTER]=keep · r=redo · q=save & quit:
 ✓ Saved. Good episodes total: 12
STEP 4 · RESET — reset the scene / mallet position for the next demo.
```

The start-state hints come from `dataset.start_states` in the config — edit them
to match the target notes and mallet placements you want to cover. On finish, the
dataset is finalized and (if `push_to_hub: true`) uploaded.

**Prefer the plain LeRobot loop?** `xylobot record --raw` runs `lerobot-record`
instead (supports `--resume`, which needs `dataset.root` set; on resume
`num_episodes` means *additional* episodes, not the new total).

## What makes a good strike demo

- **One clean intent:** locate mallet → grasp → move to the target bar → strike →
  retract.
- **Smooth, moderate speed.** Jerky teleop is hard to imitate.
- **Show the strike clearly** on camera — the moment the mallet meets the bar is
  the information-rich one. Approach each bar from a consistent direction.
- **Recover naturally** from a near-miss (re-approach) instead of stopping —
  recoveries are valuable training signal.
- **Reset identically** during the `reset_time_s` window: mallet to a new start
  position, arm back to a home pose.

## How many?

- ACT gives a working policy from **~50** solid demos. Start there; aim for
  spread across the target bars (e.g. ~10 per note).
- Quality and diversity beat raw count. 50 clean, varied demos > 150 sloppy ones.

## Verify the dataset

```bash
xylobot visualize --episode 0     # view frames + action traces
xylobot replay --episode 0        # replay on the arm — clear the area, keep clear of the swing
```

Datasets push to the Hugging Face Hub automatically when `push_to_hub: true`.
When replays look right, move on to training.
