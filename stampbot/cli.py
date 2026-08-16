"""StampBot CLI — thin, config-driven wrappers around the LeRobot commands.

    stampbot doctor                 # check your environment is ready
    stampbot find-ports            # discover USB ports for the arms
    stampbot calibrate all         # calibrate follower + leader
    stampbot teleop                # drive follower with the leader
    stampbot record                # record demonstrations
    stampbot replay --episode 0    # replay a recorded episode on the arm
    stampbot visualize --episode 0 # view a recorded episode
    stampbot train                 # train the policy (act / pi0)
    stampbot eval --policy-path P  # run a trained policy on the real arm

Add --dry-run to any command to print the exact LeRobot command instead of
running it. Add --config PATH to use a non-default config file.
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config, robot_flags, teleop_flags, dataset_flags


def _run(cmd: list[str], *, dry_run: bool) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    if dry_run:
        print(printable)
        return 0
    print(f"\n$ {printable}\n", flush=True)
    if shutil.which(cmd[0]) is None:
        sys.exit(
            f"error: `{cmd[0]}` not found on PATH. Is LeRobot installed?\n"
            f"       Run `stampbot doctor`, or `pip install -e \".[rebot]\"`."
        )
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
                 "lerobot-record", "lerobot-train"]:
        check(f"`{tool}` on PATH", shutil.which(tool) is not None,
              'install LeRobot: pip install -e ".[rebot]"')

    # Follower on RS is a SocketCAN interface (can0), not a serial path.
    f_port = cfg["follower"]["port"]
    if cfg["follower"].get("can_adapter") == "socketcan":
        up = Path(f"/sys/class/net/{f_port}/operstate")
        state = up.read_text().strip() if up.exists() else "missing"
        check(f"CAN interface '{f_port}' is up (state: {state})", state == "up",
              "run `stampbot can-up` (sudo ip link set can0 up ...)")
    else:
        check(f"follower port exists ({f_port})", Path(f_port).exists(),
              "edit configs/stampbot(.local).yaml; run `stampbot find-ports`")

    l_port = Path(cfg["leader"]["port"])
    check(f"leader port exists ({l_port})", l_port.exists(),
          "edit configs/stampbot(.local).yaml; run `stampbot find-ports`")

    rid = cfg["dataset"]["repo_id"]
    check(f"dataset.repo_id set ({rid})", "CHANGE_ME" not in rid,
          "set <hf_user>/<name> in configs/stampbot.yaml")

    try:
        import torch  # noqa
        dev = cfg["policy"]["device"]
        avail = (dev == "cpu"
                 or (dev == "cuda" and torch.cuda.is_available())
                 or (dev == "mps" and torch.backends.mps.is_available()))
        check(f"torch device '{dev}' available", avail,
              "training needs a GPU; set policy.device or use a CUDA/MPS machine")
    except ImportError:
        check("PyTorch importable", False, 'installed with LeRobot')

    print("\n" + ("All good — you're ready to collect data. 🎉" if ok
                  else "Some checks failed — fix the ❌ items above."))
    return 0 if ok else 1


def cmd_find_ports(cfg, args):
    return _run(["lerobot-find-port"], dry_run=args.dry_run)


def cmd_can_up(cfg, args):
    # Bring up the SocketCAN interface the RS follower talks over.
    can = cfg.get("can", {})
    iface = can.get("interface", "can0")
    bitrate = can.get("bitrate", 1000000)
    cmd = ["sudo", "ip", "link", "set", iface, "up", "type", "can",
           "bitrate", str(bitrate)]
    return _run(cmd, dry_run=args.dry_run)


def cmd_calibrate(cfg, args):
    which = args.which
    rc = 0
    if which in ("follower", "all"):
        rc |= _run(["lerobot-calibrate", *robot_flags(cfg)], dry_run=args.dry_run)
    if which in ("leader", "all"):
        rc |= _run(["lerobot-calibrate", *teleop_flags(cfg)], dry_run=args.dry_run)
    return rc


def cmd_teleop(cfg, args):
    cmd = ["lerobot-teleoperate", *robot_flags(cfg), *teleop_flags(cfg)]
    if args.display:
        cmd.append("--display_data=true")
    return _run(cmd, dry_run=args.dry_run)


def cmd_record(cfg, args):
    # allow quick overrides without editing the yaml
    if args.num_episodes is not None:
        cfg["dataset"]["num_episodes"] = args.num_episodes
    cmd = [
        "lerobot-record",
        *robot_flags(cfg), *teleop_flags(cfg), *dataset_flags(cfg),
        "--display_data=true",
    ]
    if args.resume:
        cmd.append("--resume=true")
    return _run(cmd, dry_run=args.dry_run)


def cmd_replay(cfg, args):
    cmd = [
        "lerobot-replay",
        *robot_flags(cfg),
        f"--dataset.repo_id={cfg['dataset']['repo_id']}",
        f"--dataset.episode={args.episode}",
    ]
    return _run(cmd, dry_run=args.dry_run)


def cmd_visualize(cfg, args):
    cmd = [
        "lerobot-dataset-viz",
        f"--repo-id={cfg['dataset']['repo_id']}",
        f"--episode-index={args.episode}",
    ]
    return _run(cmd, dry_run=args.dry_run)


def cmd_train(cfg, args):
    p = cfg["policy"]
    ptype = args.policy or p["type"]
    cmd = [
        "lerobot-train",
        f"--dataset.repo_id={cfg['dataset']['repo_id']}",
        f"--policy.type={ptype}",
        f"--policy.device={p['device']}",
        f"--output_dir={p['output_dir']}",
        f"--job_name={p['job_name']}",
        f"--batch_size={p['batch_size']}",
        f"--steps={p['steps']}",
        f"--wandb.enable={str(bool(p.get('wandb', False))).lower()}",
    ]
    return _run(cmd, dry_run=args.dry_run)


def cmd_eval(cfg, args):
    # Run a trained policy on the real robot, recording eval episodes.
    eval_repo = cfg["dataset"]["repo_id"] + "_eval"
    cmd = [
        "lerobot-record",
        *robot_flags(cfg),
        *dataset_flags(cfg, repo_id=eval_repo),
        f"--policy.path={args.policy_path}",
        "--display_data=true",
    ]
    return _run(cmd, dry_run=args.dry_run)


# --- arg parsing ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stampbot",
        description="Config-driven toolkit for the StampBot reBot B601 arm.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--config", help="path to config yaml (default: configs/stampbot.yaml)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the LeRobot command instead of running it")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check your environment is ready").set_defaults(func=cmd_doctor)
    sub.add_parser("find-ports", help="discover USB ports for the arms").set_defaults(func=cmd_find_ports)
    sub.add_parser("can-up", help="bring up the SocketCAN interface (RS follower)").set_defaults(func=cmd_can_up)

    c = sub.add_parser("calibrate", help="calibrate follower / leader / all")
    c.add_argument("which", choices=["follower", "leader", "all"], default="all", nargs="?")
    c.set_defaults(func=cmd_calibrate)

    t = sub.add_parser("teleop", help="drive the follower with the leader")
    t.add_argument("--display", action="store_true", help="show camera feeds")
    t.set_defaults(func=cmd_teleop)

    r = sub.add_parser("record", help="record demonstrations")
    r.add_argument("-n", "--num-episodes", type=int, help="override target episode count")
    r.add_argument("--resume", action="store_true", help="resume recording into an existing dataset")
    r.set_defaults(func=cmd_record)

    rp = sub.add_parser("replay", help="replay a recorded episode on the arm")
    rp.add_argument("--episode", type=int, default=0)
    rp.set_defaults(func=cmd_replay)

    v = sub.add_parser("visualize", help="view a recorded episode")
    v.add_argument("--episode", type=int, default=0)
    v.set_defaults(func=cmd_visualize)

    tr = sub.add_parser("train", help="train the policy")
    tr.add_argument("--policy", choices=["act", "pi0"], help="override policy type")
    tr.set_defaults(func=cmd_train)

    e = sub.add_parser("eval", help="run a trained policy on the real arm")
    e.add_argument("--policy-path", required=True, help="path or HF id of the trained policy")
    e.set_defaults(func=cmd_eval)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
