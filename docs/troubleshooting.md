# Troubleshooting

## CAN / follower

- **`can0` doesn't exist** → USB-CAN adapter not recognized. Check `dmesg`.
  On Jetson, install the PCAN driver (see the Seeed wiki).
- **`can-up` fails / interface won't come up** → wrong bitrate or adapter busy.
  Run `xb can-up` (sets bitrate while the iface is DOWN, then brings it up).
- **Arm doesn't move in teleop, no error** → confirm `candump can0` shows traffic;
  confirm `can_adapter: socketcan` and `type: seeed_b601_rs_follower` in config.
- **`seeed_b601_rs_follower` is "unknown type"** → you're on plain upstream
  LeRobot; RS support may need Seeed's branch. Follow the install on the
  [RS wiki](https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/).

## Leader / serial

- **Leader port not found** → run `xylobot find-ports`. On Linux:
  `sudo apt remove brltty` and `sudo chmod 666 /dev/ttyUSB*`.
- **A joint moves backwards** → this is a FOLLOWER motor-direction issue on the RS
  (the RS leader has no joint_directions; see [calibration.md](./calibration.md)).

## Cameras

- **Wrong feed / black frame** → the OpenCV `index_or_path` is off. Try 0,1,2…
  or the explicit `/dev/video*` path. Remove cameras you don't have from config.
- **FPS drops during record** → lower camera `width`/`height` or `fps`; USB
  bandwidth is the usual bottleneck with two cameras.

## Training

- **CUDA out of memory** → lower `policy.batch_size` in the config.
- **No GPU** → training ACT on CPU is impractically slow. Use a CUDA box (or a
  cloud GPU) and point `xylobot train` at the dataset on the Hub.
- **Policy does nothing sensible** → almost always data, not hyperparameters.
  Re-watch demos with `xylobot visualize`; look for inconsistent resets, teleop
  jitter, or a task the cameras can't actually observe.

## General

- Add `--dry-run` to any command to see the exact LeRobot invocation.
- `xylobot doctor` is the fastest triage — run it first.
