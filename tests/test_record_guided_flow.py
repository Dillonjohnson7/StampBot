"""Control-flow tests for the guided recorder, with LeRobot fully mocked.

Runs the full stampbot.record_guided.run() flow (start/stop, redo, keep, quit,
reset, finalize, upload, counts, kwarg filtering, camera fourcc) without any
hardware or LeRobot install. Run with `pytest` or `python tests/test_record_guided_flow.py`.
"""
import builtins
import dataclasses
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

calls = {"save": 0, "clear": 0, "finalize": 0, "push": 0, "connect": 0,
         "disconnect": 0, "record_loop": 0, "enc_enter": 0, "enc_exit": 0,
         "register": 0, "live": 0, "create": 0, "ctor": 0, "img_writer": 0}

# controls fake record_loop behavior: "normal" waits for exit_early; "raise" throws
BEHAVIOR = {"mode": "normal"}


@dataclasses.dataclass
class FakeRobotConfig:
    port: str = ""
    id: str = ""
    cameras: dict = None
    can_adapter: str = None

@dataclasses.dataclass
class FakeTeleopConfig:
    port: str = ""
    id: str = ""
    joint_directions: dict = None

@dataclasses.dataclass
class FakeOpenCVCameraConfig:
    index_or_path: object = 0
    width: int = 0
    height: int = 0
    fps: int = 0
    fourcc: str = None
    warmup_s: int = 1


class FakeRobot:
    name = "seeed_b601_rs_follower"
    is_connected = False
    action_features = {"a": float}
    observation_features = {"o": float}
    def connect(self, calibrate=True): calls["connect"] += 1; self.is_connected = True
    def disconnect(self): calls["disconnect"] += 1; self.is_connected = False

class FakeTeleop(FakeRobot):
    name = "rebot_arm_102_leader"


class FakeDataset:
    def __init__(self, repo_id=None, root=None, **kw):  # resume path: LeRobotDataset(repo_id, root=)
        self.num_episodes = 0
        calls["ctor"] += 1
    @classmethod
    def create(cls, **kw):
        d = cls(); calls["ctor"] -= 1; calls["create"] += 1; d.create_kwargs = kw; return d
    def start_image_writer(self, **kw): calls["img_writer"] += 1
    def save_episode(self): calls["save"] += 1; self.num_episodes += 1
    def clear_episode_buffer(self): calls["clear"] += 1
    def finalize(self): calls["finalize"] += 1
    def push_to_hub(self): calls["push"] += 1


def fake_record_loop(**kw):
    import time
    calls["live" if kw.get("dataset") is None else "record_loop"] += 1
    if BEHAVIOR["mode"] == "raise":
        raise RuntimeError("boom")
    ev = kw["events"]
    for _ in range(100000):
        if ev.get("exit_early"):
            ev["exit_early"] = False
            break
        time.sleep(0.001)

class FakeEnc:
    def __init__(self, ds): self.ds = ds
    def __enter__(self): calls["enc_enter"] += 1; return self
    def __exit__(self, *a): calls["enc_exit"] += 1; return False


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

_mod("lerobot")
_mod("lerobot.robots", make_robot_from_config=lambda c: FakeRobot(),
     RobotConfig=types.SimpleNamespace(get_choice_class=lambda n: FakeRobotConfig))
_mod("lerobot.teleoperators", make_teleoperator_from_config=lambda c: FakeTeleop(),
     TeleoperatorConfig=types.SimpleNamespace(get_choice_class=lambda n: FakeTeleopConfig))
_mod("lerobot.cameras")
_mod("lerobot.cameras.opencv", OpenCVCameraConfig=FakeOpenCVCameraConfig)
_mod("lerobot.datasets")
_mod("lerobot.datasets.lerobot_dataset", LeRobotDataset=FakeDataset)
_mod("lerobot.utils")
_mod("lerobot.utils.feature_utils", hw_to_dataset_features=lambda hw, p: {p: hw})
def _register(): calls["register"] += 1
_mod("lerobot.utils.import_utils", register_third_party_plugins=_register)
_mod("lerobot.scripts")
_mod("lerobot.scripts.lerobot_record", record_loop=fake_record_loop, VideoEncodingManager=FakeEnc)
_mod("lerobot.processor", make_default_processors=lambda: (1, 2, 3))
_mod("lerobot.utils.visualization_utils",
     init_visualization=lambda *a, **k: None, shutdown_visualization=lambda *a, **k: None)

from stampbot import record_guided  # noqa: E402


def _scripted(responses):
    it = iter(responses)
    return lambda prompt="": next(it, "")


CFG = {
    "follower": {"type": "seeed_b601_rs_follower", "port": "can0", "id": "follower1",
                 "can_adapter": "socketcan"},
    "leader": {"type": "rebot_arm_102_leader", "port": "/dev/ttyUSB0",
               "id": "rebot_arm_102_leader", "joint_directions": None},
    "cameras": {"front": {"type": "opencv", "index_or_path": 0, "width": 640,
                          "height": 480, "fps": 30, "fourcc": "MJPG"},
                "side": {"type": "opencv", "index_or_path": 6, "width": 640,
                         "height": 480, "fps": 30, "fourcc": "MJPG"}},
    "dataset": {"repo_id": "u/stampbot", "single_task": "stamp the hand", "fps": 30,
                "num_episodes": 2, "episode_time_s": 5, "reset_time_s": 2,
                "push_to_hub": True, "root": None, "start_states": ["A", "B", "C"]},
}


_ORIG_INPUT = builtins.input


def _run(responses, num_episodes=2, cfg=None):
    for k in calls:
        calls[k] = 0
    builtins.input = _scripted(responses)
    try:
        return record_guided.run(cfg or dict(CFG, dataset=dict(CFG["dataset"])),
                                 display=False, num_episodes=num_episodes)
    finally:
        builtins.input = _ORIG_INPUT  # don't leak the monkeypatch across tests


def test_two_demos_with_one_redo():
    rc = _run(["", "", "r", "", "", "", "", "", "", ""])
    assert rc == 0
    assert calls["save"] == 2          # both demos kept
    assert calls["clear"] == 1         # one redo cleared the buffer
    assert calls["record_loop"] == 3   # 2 kept + 1 redone (recording segments)
    assert calls["live"] == 4          # teleop stays live: setup x3 + reset x1
    assert calls["connect"] == 2 and calls["disconnect"] == 2
    assert calls["finalize"] == 1
    assert calls["push"] == 1          # saved>0 and push_to_hub true
    assert calls["enc_enter"] == 1 and calls["enc_exit"] == 1
    assert calls["register"] == 1      # third-party RS plugin types registered
    assert calls["create"] == 1        # fresh dataset created (no existing dir)


def test_resume_existing_dataset():
    import tempfile, os as _os
    dd = tempfile.mkdtemp()
    open(_os.path.join(dd, "meta"), "w").close()  # non-empty -> resume
    cfg = dict(CFG, dataset=dict(CFG["dataset"], root=dd))
    _run(["q"], num_episodes=1, cfg=cfg)           # q at first SET UP -> finish
    assert calls["create"] == 0 and calls["ctor"] == 1   # resumed, not created
    assert calls["img_writer"] == 1                       # image writer started on resume


def test_quit_at_reset():
    _run(["", "", "", "q"])            # demo 1 kept, then q at the RESET prompt
    assert calls["save"] == 1


def test_thread_exception_propagates_and_cleans_up():
    BEHAVIOR["mode"] = "raise"
    raised = False
    try:
        try:
            _run(["", "", ""])
        except RuntimeError:
            raised = True
    finally:
        BEHAVIOR["mode"] = "normal"
    assert raised                      # record_loop error surfaced, not swallowed
    assert calls["disconnect"] == 2    # cleanup still ran in the finally block


def test_quit_before_any_demo():
    rc = _run(["q"])
    assert rc == 0
    assert calls["save"] == 0
    assert calls["push"] == 0          # nothing saved -> no upload
    assert calls["finalize"] == 1      # still finalized
    assert calls["disconnect"] == 2    # still cleaned up


def test_save_and_quit():
    _run(["", "", "q"])
    assert calls["save"] == 1
    assert calls["push"] == 1


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print("ALL PASS ✅" if not fails else f"{fails} FAILED ✗")
    sys.exit(1 if fails else 0)
