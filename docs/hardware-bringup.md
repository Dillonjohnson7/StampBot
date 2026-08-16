# Hardware bring-up — reBot Arm B601-RS (RobStride) + reBot Arm 102 leader

Reference: [Seeed wiki — B601-RS getting started](https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/)
· [B601-RS in LeRobot](https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/)

> ⚠️ The RS pipeline is **not** the SO101 pipeline. RS motors are RobStride on a
> CAN bus behind a **PCAN-USB** adapter, and there is a **MotorBridge** motor-init
> stage that has no SO101 equivalent. Do these steps in order.

## 0. What's different from an SO101

| | SO101 | B601-RS |
|---|---|---|
| Comms | USB serial `/dev/ttyACM*` | **SocketCAN `can0`** via PCAN-USB (PEAK) |
| Motors | feetech serial servos | **RobStride** CAN motors (RS-00 ×4, RS-06 ×3) |
| Pre-LeRobot init | none | **MotorBridge**: init motors, verify 7 joints online |
| Calibration | range-of-motion sweep, per connect | **single home pose, one-time, persisted** |
| Power | 5–12 V | **48 V / 12.5 A** MeanWell |

## 1. Power

- **48 V / 12.5 A MeanWell** supply (via Seeed). Set the voltage selector:
  **230V** for 220V mains, **115V** for 110V regions. Don't use unbranded PSUs.

## 2. PCAN-USB driver (PEAK) in netdev mode

The kit's USB-CAN adapter is a **PCAN-USB**. It must present a **SocketCAN
netdev** interface (`can0`), *not* chardev mode.

- **Jetson:** remove conflicts and compile the PEAK driver in **netdev mode**:
  ```bash
  sudo apt remove -y brltty
  # then build/install the PEAK (peak-linux-driver) in netdev mode per Seeed docs
  ```
- **Desktop Linux:** recent kernels expose PCAN as SocketCAN out of the box;
  confirm `can0` appears (`ip link show`). Remove `brltty` if it grabs USB.

## 3. Bring up the CAN interface (bitrate 1 Mbps)

Bitrate must be set while the interface is **down**, then brought up:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
# convenience wrapper that does exactly this:
stampbot can-up
```

Verify:

```bash
ip -details link show can0     # UP; note CAN operstate often reads UNKNOWN when up
candump can0                   # (can-utils) shows traffic when a motor moves
```

## 4. MotorBridge — initialize the RobStride motors (RS-only)

Before LeRobot can talk to the arm, initialize the motors with MotorBridge
(model **`rebot-arm-robstride`**):

1. Python **3.12** env (Miniforge recommended), then `pip install motorbridge`.
2. Launch the gateway for zero-point setup:
   ```bash
   motorbridge-gateway
   ```
3. Open **MotorBridge Studio** (web UI) and initialize motor control parameters.
4. **Scan joints 1–7 and confirm they are all "online"** before continuing.

If any joint is offline here, LeRobot calibration and teleop will fail — fix it
at this stage (wiring, CAN, motor ID) first.

## 5. Find the leader serial port

```bash
stampbot find-ports      # wraps lerobot-find-port
```

Linux: if the port is held, `sudo apt remove brltty` and
`sudo chmod 666 /dev/ttyUSB*`.

## 6. Put the ports in your config

Edit `configs/stampbot.local.yaml` (created by `setup.sh`):

```yaml
follower: { port: can0 }         # SocketCAN interface, stays can0
leader:   { port: /dev/ttyUSB0 } # whatever find-ports reported
```

## 7. Sanity check

```bash
stampbot doctor
```

All checks ✅ before calibrating. Then continue to
[calibration.md](./calibration.md).

## Device-type reference (RS)

| Role | LeRobot type | port | adapter |
|---|---|---|---|
| Follower | `seeed_b601_rs_follower` | `can0` | `socketcan` |
| Leader | `rebot_arm_102_leader` | `/dev/ttyUSB0` | — |
