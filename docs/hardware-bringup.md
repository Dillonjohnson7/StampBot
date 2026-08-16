# Hardware bring-up — reBot Arm B601-RS + reBot Arm 102 leader

Reference: [Seeed wiki — B601-RS in LeRobot](https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/)

## 1. Power & wiring

- **Follower (B601-RS):** needs a **48 V / 15 A** power supply (not included). Robstride motors (4× RS-00, 3× RS-06) on a CAN bus.
- **Leader (reBot Arm 102):** FashionStar UART smart servos, powered + connected over USB serial (`/dev/ttyUSB0`).
- Connect the follower's CAN adapter (USB-CAN, or PCAN on Jetson) to the host.

## 2. Bring up the CAN interface (RS-specific)

The RS follower talks over **SocketCAN**, so the "port" is a network interface (`can0`), not a serial path.

```bash
sudo ip link set can0 up type can bitrate 1000000
# convenience wrapper:
stampbot can-up
```

Verify it's up:

```bash
ip -details link show can0     # state should be UP
candump can0                   # (from can-utils) should show traffic when the arm moves
```

- **Jetson users:** you may need to install the **PCAN driver** per the Seeed docs before `can0` appears.
- If `can0` doesn't exist, your USB-CAN adapter isn't recognized — check `dmesg`.

## 3. Find the leader serial port

```bash
stampbot find-ports      # wraps lerobot-find-port
```

On Linux, if the leader port is held: `sudo apt remove brltty`, and
`sudo chmod 666 /dev/ttyUSB*` to grant access.

## 4. Put the ports in your config

Edit `configs/stampbot.local.yaml` (created by `setup.sh`):

```yaml
follower: { port: can0 }         # usually stays can0
leader:   { port: /dev/ttyUSB0 } # whatever find-ports reported
```

## 5. Sanity check

```bash
stampbot doctor
```

All checks should be ✅ before calibrating. Then continue to
[calibration.md](./calibration.md).

## Device-type reference (RS)

| Role | LeRobot type | port | adapter |
|---|---|---|---|
| Follower | `seeed_b601_rs_follower` | `can0` | `socketcan` |
| Leader | `rebot_arm_102_leader` | `/dev/ttyUSB0` | — |

> Note: RS support may require Seeed's LeRobot branch/fork rather than plain
> upstream — follow the install steps on the wiki page above if
> `seeed_b601_rs_follower` is not a recognized type after install.
