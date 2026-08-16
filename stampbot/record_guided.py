"""Guided, interactive recorder for StampBot.

A step-by-step terminal flow — SET UP → ENTER to start → ENTER to stop →
keep/redo → RESET — that is much easier to run than the bare `lerobot-record`
loop. You press ENTER to start each demo, ENTER again to stop (so episodes are
as long as they need to be), then keep or redo it.

HARDWARE-AGNOSTIC BY DESIGN: the follower/leader are built from the *type
strings in your config* (`seeed_b601_rs_follower`, `rebot_arm_102_leader`) via
LeRobot's registry, and kwargs are filtered to each config class's real fields.
Nothing here is SO101-specific — it works for the reBot RS as-is.

If the LeRobot Python API differs on your version, fall back to the plain CLI:
`stampbot record --raw`.
"""
from __future__ import annotations

import dataclasses
import threading
import time
from itertools import cycle

# LeRobot public record primitives (from the current il_robots tutorial).
try:
    from lerobot.robots import make_robot_from_config, RobotConfig
    from lerobot.teleoperators import make_teleoperator_from_config, TeleoperatorConfig
    from lerobot.cameras.opencv import OpenCVCameraConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.utils.feature_utils import hw_to_dataset_features
    from lerobot.scripts.lerobot_record import record_loop
    from lerobot.processor import make_default_processors
except Exception as e:  # pragma: no cover - only meaningful with LeRobot installed
    raise SystemExit(
        "Could not import the LeRobot record API for the guided recorder.\n"
        f"  ({type(e).__name__}: {e})\n"
        'Install with `pip install -e ".[robot]"`, or use the plain CLI:\n'
        "  stampbot record --raw"
    ) from e

BAR = "━" * 60


def _build_cameras(cams_cfg: dict) -> dict:
    out = {}
    for name, c in (cams_cfg or {}).items():
        if c.get("type", "opencv") != "opencv":
            raise SystemExit(f"camera '{name}': only 'opencv' is wired in the guided "
                             f"recorder; use `stampbot record --raw` for other types.")
        out[name] = OpenCVCameraConfig(index_or_path=c["index_or_path"],
                                       width=c["width"], height=c["height"], fps=c["fps"])
    return out


def _build(config_base, make_fn, spec: dict, extra: dict):
    """Construct a robot/teleop from its registered type string.

    Only kwargs that are real fields of the resolved config class are passed, so
    the same code handles the RS follower (which takes can_adapter) and the
    leader (which takes joint_directions) without hardcoding either.
    """
    cls = config_base.get_choice_class(spec["type"])
    fields = {f.name for f in dataclasses.fields(cls)}
    kwargs = {k: v for k, v in extra.items() if k in fields and v is not None}
    return make_fn(cls(**kwargs))


def _record_segment(kw, max_s: float) -> float:
    """Run one record_loop until the user presses ENTER (or max_s elapses)."""
    kw["events"]["exit_early"] = False
    t = threading.Thread(target=record_loop, kwargs={**kw, "control_time_s": max_s}, daemon=True)
    start = time.perf_counter()
    t.start()
    try:
        input()  # ENTER stops the demo
    except (EOFError, KeyboardInterrupt):
        pass
    kw["events"]["exit_early"] = True
    t.join()
    return time.perf_counter() - start


def run(cfg: dict, *, display: bool = False, num_episodes: int | None = None) -> int:
    d = cfg["dataset"]
    fps = int(d["fps"])
    task = d["single_task"]
    target = int(num_episodes if num_episodes is not None else d["num_episodes"])
    max_s = float(d.get("episode_time_s", 60))
    # Start-state hints cycle each demo so you vary the scene (e.g. hand position).
    states = d.get("start_states") or ["(vary the hand position / orientation)"]
    state_cycle = cycle(states)

    f, l = cfg["follower"], cfg["leader"]
    cams = _build_cameras(cfg.get("cameras", {}))
    cam_names = " + ".join(cams) if cams else "no cameras"

    print(f"\nBuilding devices for {f['type']} (follower) + {l['type']} (leader)…")
    robot = _build(RobotConfig, make_robot_from_config, f,
                   {"port": f["port"], "id": f["id"], "cameras": cams,
                    "can_adapter": f.get("can_adapter")})
    teleop = _build(TeleoperatorConfig, make_teleoperator_from_config, l,
                    {"port": l["port"], "id": l["id"],
                     "joint_directions": l.get("joint_directions")})

    action_features = hw_to_dataset_features(robot.action_features, "action")
    obs_features = hw_to_dataset_features(robot.observation_features, "observation")
    dataset = LeRobotDataset.create(
        repo_id=d["repo_id"], fps=fps,
        features={**action_features, **obs_features},
        robot_type=robot.name, use_videos=True, image_writer_threads=4,
        root=d.get("root"),
    )

    robot.connect()
    teleop.connect()
    procs = make_default_processors()
    events = {"exit_early": False, "rerecord_episode": False, "stop_recording": False}
    loop_kw = dict(
        robot=robot, events=events, fps=fps, teleop=teleop, dataset=dataset,
        single_task=task, display_data=display,
        teleop_action_processor=procs[0], robot_action_processor=procs[1],
        robot_observation_processor=procs[2],
    )

    saved = 0
    print(f"\nTask: {task}\nCameras: {cam_names}   ·   target this run: {target} demo(s)\n")
    try:
        for i in range(target):
            state = next(state_cycle)
            print(f"\n{BAR}\n EPISODE {dataset.num_episodes + 1}   "
                  f"(demo {i + 1} of {target} this run · {saved} saved total)\n{BAR}\n")
            while True:  # repeat until this demo is kept
                print("STEP 1 · SET UP")
                print(f" • Start state: {state}  (cycles every demo)")
                print(" • Move the LEADER arm to your start pose (follower mirrors live).")
                print(" • Have the helper present the hand; drive the task deliberately.\n")
                if input(" >> Press ENTER to START recording (q = finish session): ").strip().lower() == "q":
                    raise _Finish()

                print("\n 🔴 RECORDING… perform the task now.")
                print(" >> Press ENTER to STOP.", flush=True)
                elapsed = _record_segment(loop_kw, max_s)
                print(f"\n Captured ~{int(elapsed * fps)} frames ({elapsed:.1f}s).\n")

                choice = input("STEP 3 · KEEP THIS DEMO?  [ENTER]=keep · r=redo · q=save & quit: ").strip().lower()
                if choice == "r":
                    dataset.clear_episode_buffer()
                    print(" ↺ Discarded. Re-recording this demo…\n")
                    continue
                print(f"  saving… encoding video ({cam_names})")
                t0 = time.perf_counter()
                dataset.save_episode()
                saved += 1
                print(f"  done in {time.perf_counter() - t0:.1f}s")
                print(f" ✓ Saved. Good episodes total: {dataset.num_episodes}\n")
                if choice == "q":
                    raise _Finish()
                break

            if i < target - 1:
                print("STEP 4 · RESET — reset the scene / hand position for the next demo.\n")
                input(" >> Press ENTER when the scene is ready for the next demo: ")
    except _Finish:
        pass
    finally:
        print(f"\nSession done. Recorded {saved} demo(s) this run.")
        print("Finalizing dataset…")
        dataset.finalize()
        robot.disconnect()
        teleop.disconnect()
        if d.get("push_to_hub"):
            print("Uploading to the Hugging Face Hub…")
            dataset.push_to_hub()
        print(f"✓ Dataset '{d['repo_id']}' now has {dataset.num_episodes} episode(s).")
    return 0


class _Finish(Exception):
    """Internal signal to end the session cleanly."""
