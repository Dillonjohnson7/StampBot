# XyloBot — Training Run Status & Working Log

_Last updated: 2026-08-17_

This doc captures the first ACT training run on the H100, everything we vetted,
the performance picture, and the open decisions. It's a handoff/status snapshot —
not a permanent design doc.

---

## 1. Where we are in one line

The **first ACT policy is training on an H100** from the cleaned xylophone
dataset, running fully offline. Throughput is ~**4 steps/s** (dataloader-bound on
video decode), so a full 100k-step run is ~**7 hours** — but the policy will
likely be usable at the **50k checkpoint (~3.5h)**.

---

## 2. The project (context)

XyloBot is an imitation-learning toolkit for a **reBot Arm B601-RS** (Robstride
motors over SocketCAN) that learns to **pick up a mallet and strike a xylophone
bar to play a note**. It's a thin, config-driven wrapper around HuggingFace
**LeRobot**: one YAML (`configs/stampbot.yaml`) drives the whole loop
teleop → record → train → deploy via the `xb` / `xylobot` CLI.

- Package is named `stampbot` internally (legacy name); product is XyloBot.
- Policy plan: **ACT** first (fast, trains from scratch on one GPU from ~50
  demos), then reuse the same dataset for a **π0 / π0.5** finetune later.
- LeRobot here is a special `rebot_lerobot` build + `lerobot_robot_seeed_b601`
  plugin for *hardware* commands — but **training only reads the dataset**, so
  plain upstream LeRobot is acceptable for the train step (see risks below).

---

## 3. What we launched

The dataset ships with a `TRAIN_ON_H100.sh` (lives in the `xylobot_dataset`
folder, **not** in this code repo) that builds a venv, installs LeRobot, and
trains. The equivalent manual command:

```bash
python3 -m venv ~/xylo_venv && source ~/xylo_venv/bin/activate
pip install --upgrade pip && pip install lerobot
export HF_HUB_OFFLINE=1                       # load dataset purely from local disk
lerobot-train \
  --dataset.repo_id=dillonjohnson7/xylobot_xylophone_clean \
  --dataset.root=/path/to/xylobot_xylophone_clean \
  --policy.type=act --policy.device=cuda --policy.push_to_hub=false \
  --output_dir=~/outputs/train/act_xylobot --job_name=act_xylobot \
  --batch_size=32 --steps=100000 --save_freq=10000 --num_workers=8 --wandb.enable=false
```

**Status: running.** Loss should be trending down; checkpoints every 10k steps.

---

## 4. What we vetted — findings

### ✅ Correct
- `HF_HUB_OFFLINE=1` **+** `--dataset.root=…` → fully local load, no Hub round-trip.
- `--policy.push_to_hub=false` → nothing uploaded; run is offline end to end.
- `--batch_size=32 --steps=100000 --save_freq=10000 --num_workers=8` for ACT on
  an H100 from ~50 demos is sound. No sim `--env`, so no eval-env crash.
- Using cleaned repo_id `dillonjohnson7/xylobot_xylophone_clean` (vs. the
  `CHANGE_ME/xylobot_xylophone` placeholder still in `configs/stampbot.yaml`) is
  expected — the real dataset diverged from the committed default.

### ⚠️ Risks / gotchas flagged
1. **LeRobot version vs. dataset format** (highest risk). `pip install lerobot`
   pulls the *latest* upstream; the dataset was recorded with the `rebot_lerobot`
   build (~0.4.4). If `codebase_version` in `meta/info.json` doesn't match what
   the installed lerobot expects, loading fails or needs migration.
   → Since training **started and is stepping**, this risk is effectively cleared
   for this run (the dataset loaded).
2. **Trailing `\ ` (backslash + space)** in the pasted manual block breaks line
   continuation. Non-issue if `TRAIN_ON_H100.sh` was used instead. Since training
   is running with the right flags, this is moot for this run.
3. **`--output_dir=~/outputs/...` tilde may not expand.** Bash only tilde-expands
   `~` at the start of a word or in a real `name=value` assignment;
   `--output_dir=~/…` is neither, so lerobot may receive a literal `~` and write
   checkpoints to `./~/outputs/train/act_xylobot`. **Action:** confirm where
   checkpoints actually land before eval; prefer `$HOME/...` or an absolute path.

---

## 5. Performance picture

- **Throughput: ~4 steps/s** (batch 32 → ~128 samples/s).
- **Diagnosis: dataloader-bound on video decode**, not GPU-bound. ACT is a small
  model (ResNet18 + small transformer, ~80M params) and barely taxes an H100; the
  bottleneck is CPU decoding video frames each batch.
- **Root cause: the 1280×720 scene camera.** Every sample pays a full 720p decode.
  ACT downsizes internally, but the decode cost is baked into the recorded data —
  not changeable mid-run without re-encoding the dataset.
- **ETA: 100k steps ÷ 4/s ≈ 6.9 hours.** Checkpoint every ~42 min.

### Speedup levers (if we want to intervene)
1. **`nvidia-smi` + `nproc`** to confirm: low GPU-Util → dataloader-bound.
2. **Raise `--num_workers`** to match core count (8 → ~24). Biggest lever when
   decode-bound. Requires restart, but resume from the last checkpoint:
   ```bash
   lerobot-train \
     --config_path=$HOME/outputs/train/act_xylobot/checkpoints/last/pretrained_model/train_config.json \
     --resume=true --num_workers=24
   ```
3. **`--policy.use_amp=true`** — only helps if actually GPU-bound (unlikely here).
4. **Re-encode the scene cam smaller** — real fix for decode cost, but a
   dataset-level change; not for this run.

**Decision so far:** let it ride rather than restart — see the pragmatic plan.

---

## 6. Pragmatic plan (recommended)

Don't wait for the full 100k. ACT on ~50 demos is usually competent by
**40k–50k steps (~3–3.5h)**.

1. Let training continue.
2. When `checkpoints/050000/pretrained_model` lands (~3.5h in), **eval it while
   training keeps running.**
3. If it's already landing clean strikes, **kill the run early** — saves ~half
   the time.

### Eval command (once a checkpoint exists)
```bash
xb eval --policy-path <output_dir>/checkpoints/050000/pretrained_model
```
- **On-arm eval needs the hardware build** (`rebot_lerobot` + the
  `lerobot_robot_seeed_b601` plugin) and the CAN/cameras up — not plain upstream
  lerobot. Run it on the robot machine, not the H100.
- Confirm the real `<output_dir>` first (tilde caveat, §4.3).

---

## 7. Open items / next actions

- [ ] Confirm actual checkpoint directory (verify the `~` didn't land literally).
- [ ] Watch loss / `l1_loss` trending down over first few thousand steps.
- [ ] Decide: restart with more `num_workers`, or ride to the 50k checkpoint.
- [ ] Prep the on-arm eval on the robot machine (hardware build + `xb can-up` +
      cameras) for when the 50k checkpoint is ready.
- [ ] After ACT validates the pipeline: π0 / π0.5 finetune on the same dataset.
