"""Guided, interactive recorder for StampBot.

A step-by-step terminal flow — SET UP → ENTER to start → ENTER to stop →
keep/redo → RESET — that is much easier to run than the bare `lerobot-record`
loop. You press ENTER to start each demo, ENTER again to stop (or it caps at
`episode_time_s`), then keep or redo it.

HARDWARE-AGNOSTIC BY DESIGN: the follower/leader are built from the *type
strings in your config* (`seeed_b601_rs_follower`, `rebot_arm_102_leader`) via
LeRobot's registry, and kwargs are filtered to each config class's real fields.
Nothing here is SO101-specific — it works for the reBot RS as-is.

Built on the SAME primitives LeRobot's own `record()` uses (verified against
current source): `record_loop`, `VideoEncodingManager`, `make_default_processors`,
`LeRobotDataset.create`. If the API differs on your version it fails with a clear
message — fall back to the plain CLI: `stampbot record --raw`.
"""
from __future__ import annotations

import contextlib
import dataclasses
import threading
import time
from itertools import cycle

# LeRobot record primitives. Import paths verified against huggingface/lerobot.
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
        "Ensure LeRobot + the RS plugin (lerobot_robot_seeed_b601) are installed\n"
        "in this venv (see docs/hardware-bringup.md), or use the plain CLI:\n"
        "  stampbot record --raw"
    ) from e

# Third-party device plugins (e.g. the RS follower `lerobot_robot_seeed_b601`
# and leader `lerobot_teleoperator_rebot_arm_102`) register their types only when
# imported. LeRobot's CLIs call this discovery hook at startup; the Python API
# does NOT, so we must call it ourselves or get_choice_class won't find the RS
# types. Verified against LeRobot 0.4.4 on the reBot RS.
try:
    from lerobot.utils.import_utils import register_third_party_plugins
except Exception:  # pragma: no cover
    register_third_party_plugins = None

# Optional pieces — present in current LeRobot, guarded so an older build still
# runs (just without batched video encoding / the rerun viewer).
try:
    from lerobot.scripts.lerobot_record import VideoEncodingManager
except Exception:  # pragma: no cover
    VideoEncodingManager = None
try:
    from lerobot.utils.visualization_utils import init_visualization, shutdown_visualization
except Exception:  # pragma: no cover
    init_visualization = shutdown_visualization = None

BAR = "━" * 60


def _build_cameras(cams_cfg: dict) -> dict:
    fields = {f.name for f in dataclasses.fields(OpenCVCameraConfig)}
    out = {}
    for name, c in (cams_cfg or {}).items():
        if c.get("type", "opencv") != "opencv":
            raise SystemExit(f"camera '{name}': only 'opencv' is wired in the guided "
                             f"recorder; use `stampbot record --raw` for other types.")
        kwargs = dict(index_or_path=c["index_or_path"],
                      width=c["width"], height=c["height"], fps=c["fps"])
        if c.get("fourcc"):  # e.g. MJPG — needed for 640x480@30 on the RS USB cams
            kwargs["fourcc"] = c["fourcc"]
        out[name] = OpenCVCameraConfig(**{k: v for k, v in kwargs.items() if k in fields})
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
    """Run one record_loop until the user presses ENTER (or max_s elapses).

    record_loop breaks its inner loop when events["exit_early"] is True (verified
    against source), so we run it in a thread and flip that flag on ENTER. Thread
    exceptions are re-raised on the main thread rather than being swallowed.
    """
    kw["events"]["exit_early"] = False
    err: dict = {}

    def _target():
        try:
            record_loop(**{**kw, "control_time_s": int(max_s)})
        except BaseException as e:  # surface real failures (bad camera, CAN, etc.)
            err["e"] = e

    t = threading.Thread(target=_target, daemon=True)
    start = time.perf_counter()
    t.start()
    try:
        input()  # ENTER stops the demo
    except (EOFError, KeyboardInterrupt):
        pass
    kw["events"]["exit_early"] = True
    t.join()
    if "e" in err:
        raise err["e"]
    return time.perf_counter() - start


def _disconnect(dev) -> None:
    if dev is None:
        return
    try:
        if getattr(dev, "is_connected", True):
            dev.disconnect()
    except Exception:
        pass


def run(cfg: dict, *, display: bool = False, num_episodes: int | None = None) -> int:
    d = cfg["dataset"]
    fps = int(d["fps"])
    task = d["single_task"]
    target = int(num_episodes if num_episodes is not None else d["num_episodes"])
    max_s = float(d.get("episode_time_s", 60))
    states = d.get("start_states") or ["(vary the hand position / orientation)"]
    state_cycle = cycle(states)

    if display and init_visualization is None:
        print("(note: rerun viewer unavailable in this LeRobot build — recording without display)")
        display = False

    # Register third-party device plugins so the RS follower/leader types resolve.
    if register_third_party_plugins is not None:
        register_third_party_plugins()

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

    procs = make_default_processors()
    events = {"exit_early": False, "rerecord_episode": False, "stop_recording": False}
    loop_kw = dict(
        robot=robot, events=events, fps=fps, teleop=teleop, dataset=dataset,
        single_task=task, display_data=display,
        teleop_action_processor=procs[0], robot_action_processor=procs[1],
        robot_observation_processor=procs[2],
    )

    saved = 0
    try:
        robot.connect()
        teleop.connect()
        if display:
            init_visualization("rerun", session_name="stampbot-record")

        # Match canonical record(): batch video encoding across the session.
        enc = VideoEncodingManager(dataset) if VideoEncodingManager else contextlib.nullcontext()
        print(f"\nTask: {task}\nCameras: {cam_names}   ·   target this run: {target} demo(s)\n")
        with enc:
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

                    print(f"\n 🔴 RECORDING… perform the task now (auto-stops at {int(max_s)}s).")
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
        if display and shutdown_visualization is not None:
            with contextlib.suppress(Exception):
                shutdown_visualization("rerun")
        print("Finalizing dataset…")
        with contextlib.suppress(Exception):
            dataset.finalize()
        _disconnect(robot)
        _disconnect(teleop)
        if saved and d.get("push_to_hub"):
            print("Uploading to the Hugging Face Hub…")
            with contextlib.suppress(Exception):
                dataset.push_to_hub()
        with contextlib.suppress(Exception):
            print(f"✓ Dataset '{d['repo_id']}' now has {dataset.num_episodes} episode(s).")
    return 0


class _Finish(Exception):
    """Internal signal to end the session cleanly."""
