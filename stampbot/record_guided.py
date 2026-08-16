"""Guided, interactive recorder for XyloBot.

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
message — fall back to the plain CLI: `xylobot record --raw`.
"""
from __future__ import annotations

import contextlib
import os
import dataclasses
import importlib
import threading
import time
from itertools import cycle


def _imp(name, *module_paths):
    """Return the first `name` importable from the given module paths, else None.

    LeRobot moves symbols between releases (e.g. hw_to_dataset_features lives in
    lerobot.datasets.utils on 0.4.4 but lerobot.utils.feature_utils on main), so
    we try each known location instead of pinning one.
    """
    for mod in module_paths:
        try:
            return getattr(importlib.import_module(mod), name)
        except Exception:
            continue
    return None


# Required LeRobot record primitives (with per-version fallbacks).
make_robot_from_config = _imp("make_robot_from_config", "lerobot.robots")
RobotConfig = _imp("RobotConfig", "lerobot.robots")
make_teleoperator_from_config = _imp("make_teleoperator_from_config", "lerobot.teleoperators")
TeleoperatorConfig = _imp("TeleoperatorConfig", "lerobot.teleoperators")
OpenCVCameraConfig = _imp("OpenCVCameraConfig", "lerobot.cameras.opencv")
LeRobotDataset = _imp("LeRobotDataset", "lerobot.datasets.lerobot_dataset", "lerobot.datasets")
record_loop = _imp("record_loop", "lerobot.scripts.lerobot_record")
hw_to_dataset_features = _imp("hw_to_dataset_features",
                              "lerobot.datasets.utils", "lerobot.utils.feature_utils")
make_default_processors = _imp("make_default_processors",
                               "lerobot.processor", "lerobot.processor.factory")

_REQUIRED = {
    "make_robot_from_config": make_robot_from_config, "RobotConfig": RobotConfig,
    "make_teleoperator_from_config": make_teleoperator_from_config,
    "TeleoperatorConfig": TeleoperatorConfig, "OpenCVCameraConfig": OpenCVCameraConfig,
    "LeRobotDataset": LeRobotDataset, "record_loop": record_loop,
    "hw_to_dataset_features": hw_to_dataset_features,
    "make_default_processors": make_default_processors,
}
_missing = [k for k, v in _REQUIRED.items() if v is None]
if _missing:  # pragma: no cover - only meaningful with LeRobot installed
    raise SystemExit(
        "Could not import the LeRobot record API for the guided recorder.\n"
        f"  missing: {', '.join(_missing)}\n"
        "Ensure LeRobot + the RS plugins are installed in this venv\n"
        "(see docs/hardware-bringup.md), or use the plain CLI:\n"
        "  xylobot record --raw"
    )

# Optional / version-varying pieces — guarded (older builds run without them).
# Third-party device plugins (RS follower `lerobot_robot_seeed_b601`, leader
# `lerobot_teleoperator_rebot_arm_102`) register their types only when imported;
# LeRobot's CLIs call this at startup, the Python API does not — so we must.
register_third_party_plugins = _imp("register_third_party_plugins", "lerobot.utils.import_utils")
VideoEncodingManager = _imp("VideoEncodingManager",
                            "lerobot.datasets.video_utils", "lerobot.scripts.lerobot_record")
init_visualization = _imp("init_visualization", "lerobot.utils.visualization_utils")
shutdown_visualization = _imp("shutdown_visualization", "lerobot.utils.visualization_utils")

BAR = "━" * 60


def _build_cameras(cams_cfg: dict) -> dict:
    fields = {f.name for f in dataclasses.fields(OpenCVCameraConfig)}
    out = {}
    for name, c in (cams_cfg or {}).items():
        if c.get("type", "opencv") != "opencv":
            raise SystemExit(f"camera '{name}': only 'opencv' is wired in the guided "
                             f"recorder; use `xylobot record --raw` for other types.")
        kwargs = dict(index_or_path=c["index_or_path"],
                      width=c["width"], height=c["height"], fps=c["fps"])
        if c.get("fourcc"):  # e.g. MJPG — needed for 640x480@30 on the RS USB cams
            kwargs["fourcc"] = c["fourcc"]
        if c.get("warmup_s"):  # slow-start cams (the HD scene cam needs >1s for frame 1)
            kwargs["warmup_s"] = c["warmup_s"]
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


def _live_phase(kw, prompt: str, max_s: float = 3600.0) -> str:
    """Keep leader→follower teleop mirroring LIVE while waiting at a prompt.

    Mirrors canonical record(): between episodes it runs record_loop WITHOUT a
    dataset so the operator can stage the scene/arm. Without this the follower
    freezes during SET UP/RESET and jumps when recording starts.
    Returns the user's input, stripped/lowercased ('q' on EOF/Ctrl+C).
    """
    kw_live = dict(kw)
    kw_live["dataset"] = None
    kw["events"]["exit_early"] = False
    err: dict = {}

    def _t():
        try:
            record_loop(**{**kw_live, "control_time_s": int(max_s)})
        except BaseException as e:
            err["e"] = e

    th = threading.Thread(target=_t, daemon=True)
    th.start()
    try:
        ans = input(prompt)
    except (EOFError, KeyboardInterrupt):
        ans = "q"
    kw["events"]["exit_early"] = True
    th.join()
    if "e" in err:
        raise err["e"]
    return ans.strip().lower()


def _record_segment(kw, max_s: float) -> tuple[float, bool]:
    """Run one record_loop until the user presses ENTER (or max_s elapses).

    record_loop breaks its inner loop when events["exit_early"] is True (verified
    against source), so we run it in a thread and flip that flag on ENTER.

    SAFETY: if the max_s cap expires before ENTER, the thread hands off
    seamlessly into a LIVE (non-recording) teleop loop, so the follower keeps
    mirroring the leader — it never freezes mid-motion and never jumps when the
    next phase starts. Returns (recorded_seconds, capped).
    """
    kw["events"]["exit_early"] = False
    err: dict = {}
    state = {"entered": False, "capped": False}

    def _target():
        try:
            record_loop(**{**kw, "control_time_s": int(max_s)})
            if not state["entered"]:
                # Timer expired (not ENTER): keep teleop live until the user acts.
                state["capped"] = True
                live = dict(kw)
                live["dataset"] = None
                record_loop(**{**live, "control_time_s": 10800})
        except BaseException as e:  # surface real failures (bad camera, CAN, etc.)
            err["e"] = e

    t = threading.Thread(target=_target, daemon=True)
    start = time.perf_counter()
    t.start()
    try:
        input()  # ENTER stops the demo
    except (EOFError, KeyboardInterrupt):
        pass
    state["entered"] = True
    kw["events"]["exit_early"] = True
    t.join()
    if "e" in err:
        raise err["e"]
    elapsed = time.perf_counter() - start
    return (min(elapsed, max_s), True) if state["capped"] else (elapsed, False)


def _disconnect(dev) -> None:
    if dev is None:
        return
    try:
        if getattr(dev, "is_connected", True):
            dev.disconnect()
    except Exception:
        pass


def run(cfg: dict, *, display: bool = False, num_episodes: int | None = None) -> int:
    # Tame the SVT-AV1 encoder's console spam during video encoding (it logs
    # its whole config banner per episode per camera). 1 = errors only.
    os.environ.setdefault("SVT_LOG", "1")
    d = cfg["dataset"]
    fps = int(d["fps"])
    task = d["single_task"]
    target = int(num_episodes if num_episodes is not None else d["num_episodes"])
    max_s = float(d.get("episode_time_s", 60))
    states = d.get("start_states") or ["(vary the target bar / mallet start position)"]
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
    try:
        dataset = LeRobotDataset.create(
            repo_id=d["repo_id"], fps=fps,
            features={**action_features, **obs_features},
            robot_type=robot.name, use_videos=True, image_writer_threads=4,
            root=d.get("root"),
        )
    except Exception:
        # Dataset already exists (e.g. a previous session) → resume into it,
        # the same way lerobot-record --resume does on this LeRobot version.
        dataset = LeRobotDataset(d["repo_id"], root=d.get("root"))
        if cams and hasattr(dataset, "start_image_writer"):
            dataset.start_image_writer(num_processes=0, num_threads=4)
        print(f"↩  Resuming existing dataset '{d['repo_id']}' "
              f"({dataset.num_episodes} episode(s) already saved).")

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
            init_visualization("rerun", session_name="xylobot-record")

        # Match canonical record(): batch video encoding across the session.
        enc = VideoEncodingManager(dataset) if VideoEncodingManager else contextlib.nullcontext()
        print(f"\nTask: {task}\nCameras: {cam_names}   ·   target this run: {target} demo(s)\n")
        with enc:
            for i in range(target):
                state = next(state_cycle)
                print(f"\n{BAR}\n EPISODE {dataset.num_episodes + 1}   "
                      f"(demo {i + 1} of {target} this run · {saved} saved total)\n{BAR}\n")
                while True:  # repeat until this demo is kept
                    print("STEP 1 · SET UP  (teleop LIVE — follower mirrors the leader)")
                    print(f" • Start state: {state}  (cycles every demo)")
                    print(" • Move the LEADER arm to your start pose.")
                    print(" • Place the mallet at its start spot; xylophone fully in view.\n")
                    if _live_phase(loop_kw,
                                   " >> Press ENTER to START recording (q = finish session): ") == "q":
                        raise _Finish()

                    print(f"\n 🔴 RECORDING… perform the task now "
                          f"(recording caps at {int(max_s)}s — mirroring stays live).")
                    print(" >> Press ENTER to STOP.", flush=True)
                    elapsed, capped = _record_segment(loop_kw, max_s)
                    if capped:
                        print(f"\n ⚠ Hit the {int(max_s)}s cap — recording stopped there, "
                              f"but teleop kept mirroring (no jump). Raise "
                              f"dataset.episode_time_s if demos need longer.")
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
                    print("STEP 4 · RESET  (teleop LIVE) — reset mallet/target bar for the next demo.\n")
                    if _live_phase(loop_kw,
                                   " >> Press ENTER when the scene is ready (q = finish session): ") == "q":
                        raise _Finish()
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
