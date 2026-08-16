"""StampBot CLI — thin, config-driven wrappers around the LeRobot commands.

    stampbot doctor                 # check your environment is ready
    stampbot find-ports            # discover USB ports for the arms
    stampbot can-up                # bring up the SocketCAN interface (RS)
    stampbot calibrate all         # calibrate follower, then leader (one-time)
    stampbot teleop                # drive follower with the leader
    stampbot record                # record demonstrations
    stampbot replay --episode 0    # replay a recorded episode on the arm
    stampbot visualize --episode 0 # view a recorded episode
    stampbot train                 # train the policy (act / pi0 / pi05)
    stampbot eval --policy-path P  # run a trained policy on the real arm

Add --dry-run to any command (before OR after the subcommand) to print the exact
LeRobot command instead of running it. Add --config PATH for a non-default config.
"""
from __future__ import annotations

import argparse
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


def _run(cmd: list[str], *, dry_run: bool) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    if dry_run:
        print(printable)
        return 0
    if shutil.which(cmd[0]) is None:
        sys.exit(
            f"error: `{cmd[0]}` not found on PATH.\n"
            f"       Run `stampbot doctor`, or {INSTALL_HINT}."
        )
    print(f"\n$ {printable}\n", flush=True)
    return subprocess.call(cmd)


# --- commands ---------------------------------------------------------------

def cmd_doctor(cfg, args):
    ok = True

    def check(label, passed, hint=""):
        nonlocal ok
        mark = "✅" if passed else "❌"
        print(f"  {mark} {label}" + (f"  — {hint}" if (not passed and hint) else ""))
        ok = ok and passed

    print("StampBot environment check\n")
    for tool in ["lerobot-find-port", "lerobot-calibrate", "lerobot-teleoperate",
                 "lerobot-record", "lerobot-replay", "lerobot-rollout", "lerobot-train"]:
        check(f"`{tool}` on PATH", shutil.which(tool) is not None, INSTALL_HINT)

    # Follower on RS is a SocketCAN interface (can0), not a serial path.
    # A CAN link reports operstate "unknown" (not "up") when actually up, so
    # only treat "down"/"missing" as a failure.
    f_port = cfg["follower"]["port"]
    if cfg["follower"].get("can_adapter") == "socketcan":
        state_file = Path(f"/sys/class/net/{f_port}/operstate")
        state = state_file.read_text().strip() if state_file.exists() else "missing"
        check(f"CAN interface '{f_port}' up (state: {state})",
              state not in ("down", "missing"),
              "run `stampbot can-up` (needs the USB-CAN adapter plugged in)")
    else:
        check(f"follower port exists ({f_port})", Path(f_port).exists(),
              "edit configs/stampbot(.local).yaml; run `stampbot find-ports`")

    l_port = Path(cfg["leader"]["port"])
    check(f"leader port exists ({l_port})", l_port.exists(),
          "edit configs/stampbot(.local).yaml; run `stampbot find-ports`")

    # RS persists calibration to JSON, keyed by id — check it's been done once.
    cal = Path.home() / ".cache/huggingface/lerobot/calibration"
    f_id, l_id = cfg["follower"]["id"], cfg["leader"]["id"]
    f_cal = (cal / "robots").exists() and any((cal / "robots").rglob(f"{f_id}.json"))
    l_cal = (cal / "teleoperators").exists() and any((cal / "teleoperators").rglob(f"{l_id}.json"))
    check(f"follower calibrated ({f_id})", f_cal,
          "run `stampbot calibrate follower` (one-time on RS)")
    check(f"leader calibrated ({l_id})", l_cal,
          "run `stampbot calibrate leader` (one-time on RS)")

    rid = cfg["dataset"]["repo_id"]
    check(f"dataset.repo_id set ({rid})", "CHANGE_ME" not in rid,
          "set <hf_user>/<name> in configs/stampbot.yaml")
    check("Hugging Face CLI on PATH (for dataset upload)", shutil.which("hf") is not None,
          "pip install huggingface_hub; then `hf auth login`")

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
        return run_guided(cfg, display=args.display, num_episodes=args.num_episodes)
    if args.num_episodes is not None:
        cfg["dataset"]["num_episodes"] = args.num_episodes
    if args.resume and not cfg["dataset"].get("root"):
        sys.exit(
            "error: --resume requires `dataset.root` set in your config.\n"
            "       LeRobot writes the additional episodes there, and on resume\n"
            "       `dataset.num_episodes` means the number of NEW episodes to add.\n"
            "       See docs/data-collection.md."
        )
    cmd = ["lerobot-record",
           *robot_flags(cfg), *teleop_flags(cfg), *dataset_flags(cfg),
           "--display_data=true"]
    if args.resume:
        cmd.append("--resume=true")
    return _run(cmd, dry_run=args.dry_run)


def cmd_replay(cfg, args):
    # Replay drives the motors from recorded actions — no cameras needed.
    cmd = ["lerobot-replay",
           *robot_flags(cfg, cameras=False),
           f"--dataset.repo_id={cfg['dataset']['repo_id']}",
           f"--dataset.episode={args.episode}"]
    return _run(cmd, dry_run=args.dry_run)


def cmd_visualize(cfg, args):
    rid = cfg["dataset"]["repo_id"]
    # Prefer the local viewer if this LeRobot build ships it; otherwise point at
    # the online viewer (works for any dataset pushed to the Hub).
    if shutil.which("lerobot-dataset-viz"):
        return _run(["lerobot-dataset-viz", f"--repo-id={rid}",
                     f"--episode-index={args.episode}"], dry_run=args.dry_run)
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
    return _run(cmd, dry_run=args.dry_run)


def cmd_eval(cfg, args):
    # Deploy a trained policy on the real arm with lerobot-rollout.
    #   base   → autonomous rollout, no recording (quick check)
    #   sentry → continuous recording + auto-upload (measure success at scale)
    p = cfg["policy"]
    ptype = args.policy or p["type"]
    task = cfg["dataset"]["single_task"]
    cmd = ["lerobot-rollout",
           f"--strategy.type={'sentry' if args.record else 'base'}",
           f"--policy.path={args.policy_path}",
           *robot_flags(cfg, cameras=True),  # the policy needs image observations
           f"--duration={args.duration}"]
    if args.record:
        cmd += [f"--dataset.repo_id={cfg['dataset']['repo_id']}_eval",
                f"--dataset.single_task={task}"]
    else:
        cmd.append(f"--task={task}")
    if ptype in VLA_POLICIES:  # smooth execution for slow VLA policies (pi0/pi05)
        cmd.append("--inference.type=rtc")
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
        prog="stampbot", parents=[common],
        description="Config-driven toolkit for the StampBot reBot B601-RS arm.",
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

    t = add("teleop", help="drive the follower with the leader")
    t.add_argument("--display", action="store_true", help="show camera feeds")
    t.set_defaults(func=cmd_teleop)

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
    e.add_argument("--record", action="store_true", help="record + upload eval episodes")
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
