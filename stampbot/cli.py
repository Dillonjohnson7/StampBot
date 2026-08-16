"""XyloBot CLI — thin, config-driven wrappers around the LeRobot commands.

    xylobot doctor                 # check your environment is ready
    xylobot find-ports            # discover USB ports for the arms
    xylobot can-up                # bring up the SocketCAN interface (RS)
    xylobot calibrate all         # calibrate follower, then leader (one-time)
    xylobot teleop                # drive follower with the leader
    xylobot record                # record demonstrations
    xylobot replay --episode 0    # replay a recorded episode on the arm
    xylobot visualize --episode 0 # view a recorded episode
    xylobot train                 # train the policy (act / pi0 / pi05)
    xylobot eval --policy-path P  # run a trained policy on the real arm

Add --dry-run to any command (before OR after the subcommand) to print the exact
LeRobot command instead of running it. Add --config PATH for a non-default config.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config, robot_flags, teleop_flags, dataset_flags

INSTALL_HINT = ("install LeRobot + the RS plugin (lerobot_robot_seeed_b601) per "
                "docs/hardware-bringup.md, then `pip install -e .` in that venv")
# LeRobot policy types that are slow VLAs and benefit from real-time chunking.
VLA_POLICIES = {"pi0", "pi05", "pi0.5", "smolvla"}


def _bin(name: str) -> str | None:
    """Resolve a command on PATH, or in this interpreter's own bin dir.

    lerobot-* live in the same venv bin as `xb`; when `xb` is launched by full
    path without activating the venv, that dir isn't on PATH, so check it too.
    """
    found = shutil.which(name)
    if found:
        return found
    cand = os.path.join(os.path.dirname(sys.executable), name)
    return cand if (os.path.isfile(cand) and os.access(cand, os.X_OK)) else None


def _run(cmd: list[str], *, dry_run: bool) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    if dry_run:
        print(printable)
        return 0
    exe = _bin(cmd[0])
    if exe is None:
        sys.exit(
            f"error: `{cmd[0]}` not found on PATH or in the venv bin.\n"
            f"       Run `xylobot doctor`, or {INSTALL_HINT}."
        )
    print(f"\n$ {printable}\n", flush=True)
    try:
        return subprocess.call([exe] + cmd[1:])
    except KeyboardInterrupt:
        # Ctrl+C reaches the child too; let it shut down (safe_zero etc.) and
        # exit quietly instead of dumping a Python traceback.
        return 130


# --- commands ---------------------------------------------------------------

def cmd_doctor(cfg, args):
    ok = True

    def check(label, passed, hint=""):
        nonlocal ok
        mark = "✅" if passed else "❌"
        print(f"  {mark} {label}" + (f"  — {hint}" if (not passed and hint) else ""))
        ok = ok and passed

    print("XyloBot environment check\n")
    for tool in ["lerobot-find-port", "lerobot-calibrate", "lerobot-teleoperate",
                 "lerobot-record", "lerobot-replay", "lerobot-train"]:
        check(f"`{tool}` available", _bin(tool) is not None, INSTALL_HINT)

    # Follower on RS is a SocketCAN interface (can0), not a serial path.
    # A CAN link reports operstate "unknown" (not "up") when actually up, so
    # only treat "down"/"missing" as a failure.
    f_port = cfg["follower"]["port"]
    if cfg["follower"].get("can_adapter") == "socketcan":
        state_file = Path(f"/sys/class/net/{f_port}/operstate")
        state = state_file.read_text().strip() if state_file.exists() else "missing"
        check(f"CAN interface '{f_port}' up (state: {state})",
              state not in ("down", "missing"),
              "run `xylobot can-up` (needs the USB-CAN adapter plugged in)")
    else:
        check(f"follower port exists ({f_port})", Path(f_port).exists(),
              "edit configs/stampbot(.local).yaml; run `xylobot find-ports`")

    l_port = Path(cfg["leader"]["port"])
    check(f"leader port exists ({l_port})", l_port.exists(),
          "edit configs/stampbot(.local).yaml; run `xylobot find-ports`")

    # Camera devices — the most common thing that blocks recording (the scene
    # cam can be a /dev/video* path grabbed by pipewire).
    for name, c in (cfg.get("cameras") or {}).items():
        dev = c.get("index_or_path")
        if isinstance(dev, str) and dev.startswith("/dev/"):
            check(f"camera '{name}' device exists ({dev})", Path(dev).exists(),
                  "run `lerobot-find-cameras opencv`; if grabbed, "
                  "`systemctl --user restart wireplumber`")

    # RS persists calibration to JSON, keyed by id — check it's been done once.
    cal = Path(os.environ.get("HF_LEROBOT_HOME",
                              Path.home() / ".cache/huggingface/lerobot")) / "calibration"
    f_id, l_id = cfg["follower"]["id"], cfg["leader"]["id"]
    f_cal = (cal / "robots").exists() and any((cal / "robots").rglob(f"{f_id}.json"))
    l_cal = (cal / "teleoperators").exists() and any((cal / "teleoperators").rglob(f"{l_id}.json"))
    check(f"follower calibrated ({f_id})", f_cal,
          "run `xylobot calibrate follower` (one-time on RS)")
    check(f"leader calibrated ({l_id})", l_cal,
          "run `xylobot calibrate leader` (one-time on RS)")

    rid = cfg["dataset"]["repo_id"]
    check(f"dataset.repo_id set ({rid})", "CHANGE_ME" not in rid,
          "set <hf_user>/<name> in configs/stampbot.yaml")
    check("Hugging Face CLI available (for dataset upload)",
          (_bin("hf") or _bin("huggingface-cli")) is not None,
          "install huggingface_hub; then `hf auth login`")

    try:
        import torch  # noqa
        dev = cfg["policy"]["device"]
        mps = getattr(torch.backends, "mps", None)
        avail = (dev == "cpu"
                 or (dev == "cuda" and torch.cuda.is_available())
                 or (dev == "mps" and mps is not None and mps.is_available()))
        check(f"torch device '{dev}' available", avail,
              "training needs a GPU; set policy.device or use a CUDA/MPS machine")
    except ImportError:
        check("PyTorch importable", False, INSTALL_HINT)

    print("\n" + ("All good — you're ready to collect data. 🎉" if ok
                  else "Some checks failed — fix the ❌ items above."))
    return 0 if ok else 1


def cmd_find_ports(cfg, args):
    return _run(["lerobot-find-port"], dry_run=args.dry_run)


def cmd_can_up(cfg, args):
    # RS uses a PCAN-USB (PEAK) adapter in SocketCAN/netdev mode. The CAN
    # bitrate must be set while the interface is DOWN, THEN brought up — you
    # cannot set bitrate and 'up' in one command. This mirrors the RS wiki:
    #   ip link set can0 down; ip link set can0 type can bitrate 1000000; ... up
    can = cfg.get("can", {})
    iface = can.get("interface", "can0")
    bitrate = str(can.get("bitrate", 1000000))
    steps = [
        ["sudo", "ip", "link", "set", iface, "down"],                 # ensure down (best effort)
        ["sudo", "ip", "link", "set", iface, "type", "can", "bitrate", bitrate],
        ["sudo", "ip", "link", "set", iface, "up"],
    ]
    rc = 0
    for step in steps:
        rc = _run(step, dry_run=args.dry_run)
        if rc != 0 and step[-1] != "down":  # the initial 'down' may fail if already down
            return rc
    return rc


def cmd_calibrate(cfg, args):
    # Follower first, then leader (RS order). Fail fast: if the follower
    # calibration fails, don't proceed to the leader.
    rc = 0
    if args.which in ("follower", "all"):
        rc = _run(["lerobot-calibrate", *robot_flags(cfg, cameras=False)], dry_run=args.dry_run)
        if rc != 0:
            return rc
    if args.which in ("leader", "all"):
        rc = _run(["lerobot-calibrate", *teleop_flags(cfg)], dry_run=args.dry_run)
    return rc


def cmd_teleop(cfg, args):
    # Cameras only when displaying — otherwise a bad camera index would block a
    # pure motion check.
    cmd = ["lerobot-teleoperate",
           *robot_flags(cfg, cameras=args.display), *teleop_flags(cfg)]
    if args.display:
        cmd.append("--display_data=true")
    return _run(cmd, dry_run=args.dry_run)


def cmd_record(cfg, args):
    # Guided interactive recorder by default; --raw drops to plain lerobot-record.
    if not args.raw and not args.dry_run:
        from .record_guided import run as run_guided
        try:
            return run_guided(cfg, display=args.display, num_episodes=args.num_episodes)
        except KeyboardInterrupt:
            print("\ninterrupted — saved episodes are kept.")
            return 130
    if args.num_episodes is not None:
        cfg["dataset"]["num_episodes"] = args.num_episodes
    if args.resume and not cfg["dataset"].get("root"):
        sys.exit(
            "error: --resume requires `dataset.root` set in your config.\n"
            "       LeRobot writes the additional episodes there, and on resume\n"
            "       `dataset.num_episodes` means the number of NEW episodes to add.\n"
            "       See docs/data-collection.md."
        )
    cmd = ["lerobot-record", *robot_flags(cfg), *teleop_flags(cfg), *dataset_flags(cfg)]
    if args.display:  # rerun viewer only when asked (headless/SSH can't show it)
        cmd.append("--display_data=true")
    if args.resume:
        cmd.append("--resume=true")
    return _run(cmd, dry_run=args.dry_run)


def cmd_replay(cfg, args):
    # Replay drives the motors from recorded actions — no cameras needed.
    cmd = ["lerobot-replay",
           *robot_flags(cfg, cameras=False),
           f"--dataset.repo_id={cfg['dataset']['repo_id']}",
           f"--dataset.episode={args.episode}"]
    if cfg["dataset"].get("root"):
        cmd.append(f"--dataset.root={cfg['dataset']['root']}")
    return _run(cmd, dry_run=args.dry_run)


def cmd_visualize(cfg, args):
    rid = cfg["dataset"]["repo_id"]
    root = cfg["dataset"].get("root")
    # Prefer the local viewer if this LeRobot build ships it; otherwise point at
    # the online viewer (works for any dataset pushed to the Hub).
    if _bin("lerobot-dataset-viz"):
        cmd = ["lerobot-dataset-viz", f"--repo-id={rid}", f"--episode-index={args.episode}"]
        if root:
            cmd.append(f"--root={root}")
        return _run(cmd, dry_run=args.dry_run)
    url = f"https://huggingface.co/spaces/lerobot/visualize_dataset?dataset={rid}&episode={args.episode}"
    if args.dry_run:
        print(f"# open: {url}")
        return 0
    print(f"Local viewer not installed. View online:\n  {url}\n"
          f"Or locally: python -m lerobot.scripts.visualize_dataset "
          f"--repo-id {rid} --episode-index {args.episode}")
    return 0


def cmd_train(cfg, args):
    p = cfg["policy"]
    ptype = args.policy or p["type"]
    cmd = ["lerobot-train",
           f"--dataset.repo_id={cfg['dataset']['repo_id']}",
           f"--policy.type={ptype}",
           f"--policy.device={p['device']}",
           f"--output_dir={p['output_dir']}",
           f"--job_name={p['job_name']}",
           f"--batch_size={p['batch_size']}",
           f"--steps={p['steps']}",
           f"--wandb.enable={str(bool(p.get('wandb', False))).lower()}"]
    if cfg["dataset"].get("root"):  # locally-rooted dataset (e.g. from --resume)
        cmd.append(f"--dataset.root={cfg['dataset']['root']}")
    return _run(cmd, dry_run=args.dry_run)


def cmd_eval(cfg, args):
    # Run a trained policy on the real arm. Newer LeRobot has `lerobot-rollout`;
    # 0.4.4 (the reBot RS build) runs the policy via `lerobot-record --policy.path`.
    p = cfg["policy"]
    ptype = args.policy or p["type"]
    task = cfg["dataset"]["single_task"]
    eval_repo = cfg["dataset"]["repo_id"] + "_eval"
    if _bin("lerobot-rollout"):
        cmd = ["lerobot-rollout",
               f"--strategy.type={'sentry' if args.record else 'base'}",
               f"--policy.path={args.policy_path}",
               *robot_flags(cfg, cameras=True),  # the policy needs image observations
               f"--duration={args.duration}"]
        if args.record:
            cmd += [f"--dataset.repo_id={eval_repo}", f"--dataset.single_task={task}"]
        else:
            cmd.append(f"--task={task}")
        if ptype in VLA_POLICIES:  # smooth execution for slow VLA policies (pi0/pi05)
            cmd.append("--inference.type=rtc")
    else:  # LeRobot 0.4.4: no lerobot-rollout — deploy the policy via record
        print("note: this LeRobot has no lerobot-rollout; eval runs the policy "
              "through lerobot-record. --policy type/rtc has no effect here; "
              "--duration sets the rollout length.", file=sys.stderr)
        d = cfg["dataset"]
        eval_root = (d["root"] + "_eval") if d.get("root") else None  # don't collide with training root
        cmd = ["lerobot-record",
               *robot_flags(cfg, cameras=True),
               # one rollout of --duration seconds; upload only when --record
               *dataset_flags(cfg, repo_id=eval_repo, root=eval_root,
                              num_episodes=1, episode_time_s=args.duration,
                              push_to_hub=bool(args.record)),
               f"--policy.path={args.policy_path}",
               "--display_data=true"]
    return _run(cmd, dry_run=args.dry_run)


# --- arg parsing ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # Shared options usable before OR after the subcommand. SUPPRESS defaults so
    # neither parser clobbers the other's value; resolved in main() via getattr.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help="path to config yaml (default: configs/stampbot.yaml)")
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                        help="print the LeRobot command instead of running it")

    p = argparse.ArgumentParser(
        prog="xylobot", parents=[common],
        description="Config-driven toolkit for the XyloBot reBot B601-RS arm.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    add("doctor", help="check your environment is ready").set_defaults(func=cmd_doctor)
    add("find-ports", help="discover USB ports for the arms").set_defaults(func=cmd_find_ports)
    add("can-up", help="bring up the SocketCAN interface (RS follower)").set_defaults(func=cmd_can_up)

    c = add("calibrate", help="calibrate follower / leader / all (one-time on RS)")
    c.add_argument("which", choices=["follower", "leader", "all"], default="all", nargs="?")
    c.set_defaults(func=cmd_calibrate)

    t = add("teleop", help="drive the follower with the leader (cameras on)")
    t.add_argument("--no-display", dest="display", action="store_false",
                   help="motion only — hide cameras (faster; skips opening them)")
    t.set_defaults(func=cmd_teleop, display=True)

    r = add("record", help="record demonstrations (guided interactive flow)")
    r.add_argument("-n", "--num-episodes", type=int, help="demos to record this run")
    r.add_argument("--display", action="store_true", help="show camera feeds (rerun)")
    r.add_argument("--raw", action="store_true",
                   help="use the plain lerobot-record CLI instead of the guided flow")
    r.add_argument("--resume", action="store_true",
                   help="[--raw] add episodes to an existing dataset (needs dataset.root)")
    r.set_defaults(func=cmd_record)

    rp = add("replay", help="replay a recorded episode on the arm")
    rp.add_argument("--episode", type=int, default=0)
    rp.set_defaults(func=cmd_replay)

    v = add("visualize", help="view a recorded episode")
    v.add_argument("--episode", type=int, default=0)
    v.set_defaults(func=cmd_visualize)

    tr = add("train", help="train the policy")
    tr.add_argument("--policy", help="override policy type (act, pi0, pi05, smolvla)")
    tr.set_defaults(func=cmd_train)

    e = add("eval", help="run a trained policy on the real arm")
    e.add_argument("--policy-path", required=True, help="path or HF id of the trained policy")
    e.add_argument("--policy", help="policy type (enables rtc for VLA policies)")
    e.add_argument("--record", action="store_true",
                   help="upload the eval rollout to the Hub (on 0.4.4 it's recorded locally either way)")
    e.add_argument("--duration", type=int, default=600, help="rollout seconds (default 600)")
    e.set_defaults(func=cmd_eval)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.dry_run = getattr(args, "dry_run", False)
    cfg = load_config(getattr(args, "config", None))
    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
