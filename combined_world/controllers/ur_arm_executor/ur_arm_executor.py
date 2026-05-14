import os
import sys
import socket
import time
from pathlib import Path
from controller import Robot


def _load_sim_config():
    config = Path(__file__).parent.parent / ".sim_config"
    if config.exists():
        for line in config.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_sim_config()


def sim_wall_sleep_after_step(timestep_ms):
    try:
        m = int(os.environ.get("SIM_SLOWDOWN", "10"))
    except ValueError:
        m = 10
    m = max(1, min(100, m))
    if m <= 1:
        return
    time.sleep((m - 1) * timestep_ms / 1000.0)


TARGET_POSITIONS = [-1.88, -2.14, -2.38, -1.51]
g_last_ur_cmd = ""


def apply_command(cmd, hand_motors, ur_motors):
    global g_last_ur_cmd
    if cmd == "WAITING":
        pass
    elif cmd == "GRASPING_CAN":
        for m in hand_motors:
            m.setPosition(0.85)
    elif cmd == "ROTATING_ARM":
        for i, m in enumerate(ur_motors):
            m.setPosition(TARGET_POSITIONS[i])
    elif cmd == "RELEASING_CAN":
        for m in hand_motors:
            m.setPosition(m.getMinPosition())
    elif cmd == "ROTATING_ARM_BACK":
        for m in ur_motors:
            m.setPosition(0.0)


robot = Robot()
timestep = int(robot.getBasicTimeStep())

speed = 1.0
role = "UR3e"
if len(sys.argv) >= 2:
    try:
        speed = float(sys.argv[1])
    except ValueError:
        pass
if len(sys.argv) >= 3:
    role = sys.argv[2]

hand_motors = [
    robot.getDevice("finger_1_joint_1"),
    robot.getDevice("finger_2_joint_1"),
    robot.getDevice("finger_middle_joint_1"),
]
ur_motors = [
    robot.getDevice("shoulder_lift_joint"),
    robot.getDevice("elbow_joint"),
    robot.getDevice("wrist_1_joint"),
    robot.getDevice("wrist_2_joint"),
]
for m in ur_motors:
    m.setVelocity(speed)

distance_sensor = robot.getDevice("distance sensor")
distance_sensor.enable(timestep)
position_sensor = robot.getDevice("wrist_1_joint_sensor")
position_sensor.enable(timestep)

host = os.environ.get("COORDINATOR_HOST", "127.0.0.1")
port = int(os.environ.get("COORDINATOR_TCP_PORT", "9099"))

coord_sock = None
line_buf = ""

while robot.step(timestep) != -1:
    dist = distance_sensor.getValue()
    wrist = position_sensor.getValue()

    if coord_sock is None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.01)
            s.connect((host, port))
            s.setblocking(False)
            s.sendall(f"REGISTER {role}\n".encode())
            coord_sock = s
            line_buf = ""
        except OSError:
            coord_sock = None

    if coord_sock is not None:
        try:
            coord_sock.sendall(f"TELEM {dist:.10g} {wrist:.10g}\n".encode())
        except OSError:
            coord_sock = None
            line_buf = ""
            g_last_ur_cmd = ""

    if coord_sock is not None:
        try:
            data = coord_sock.recv(1024)
            if data:
                line_buf += data.decode(errors='replace')
                while '\n' in line_buf:
                    line, line_buf = line_buf.split('\n', 1)
                    if line.startswith("CMD "):
                        cmd = line[4:].strip()
                        apply_command(cmd, hand_motors, ur_motors)
                        g_last_ur_cmd = cmd
            else:
                coord_sock = None
                line_buf = ""
                g_last_ur_cmd = ""
        except BlockingIOError:
            pass
        except OSError:
            coord_sock = None
            line_buf = ""
            g_last_ur_cmd = ""

        if g_last_ur_cmd == "GRASPING_CAN":
            apply_command("GRASPING_CAN", hand_motors, ur_motors)
        elif g_last_ur_cmd == "RELEASING_CAN":
            apply_command("RELEASING_CAN", hand_motors, ur_motors)

    sim_wall_sleep_after_step(timestep)

if coord_sock:
    coord_sock.close()
