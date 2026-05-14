import os
import random
import socket
import time
from controller import Supervisor


def sim_wall_sleep_after_step(timestep_ms):
    try:
        m = int(os.environ.get("SIM_SLOWDOWN", "10"))
    except ValueError:
        m = 10
    m = max(1, min(100, m))
    if m <= 1:
        return
    time.sleep((m - 1) * timestep_ms / 1000.0)


LOG_PREFIX = "coordinator: "
ARM_NAME = ["UR3e", "UR5e", "UR10e"]
CAN_BELT_DEF = ["CAN_BELT_1", "CAN_BELT_2", "CAN_BELT_3"]
CAN_BELT_NOMINAL = [0.2, 0.2, 0.062]
SCARA_BELT_NOMINAL = 0.1

WAITING, GRASPING, ROTATING, RELEASING, ROTATING_BACK = range(5)
ROLE_NONE, ROLE_UI, ROLE_UR3e, ROLE_UR5e, ROLE_UR10e, ROLE_SCARA = range(6)


class Client:
    def __init__(self, sock):
        self.sock = sock
        self.role = ROLE_NONE
        self.buf = ""


class Coordinator:
    def __init__(self):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())

        self.can_belt_speed = []
        self.scara_belt_speed = None
        self.scara_motor_vel = None

        self.clients = {}
        self.ur_sock = [None, None, None]
        self.scara_sock = None
        self.listen_sock = None

        self.arms_state = [WAITING, WAITING, WAITING]
        self.arms_counter = [0, 0, 0]
        self.telemetry_dist = [10000.0, 10000.0, 10000.0]
        self.telemetry_wrist = [0.0, 0.0, 0.0]

        self.scara_i = 0
        self.scara_fruit_type = 0
        self.scara_stride_ctr = 0

    def belts_init(self):
        for k in range(3):
            node = self.robot.getFromDef(CAN_BELT_DEF[k])
            self.can_belt_speed.append(node.getField("speed") if node else None)
        scara_node = self.robot.getFromDef("SCARA_BELT")
        self.scara_belt_speed = scara_node.getField("speed") if scara_node else None
        # The SCARA belt is inside a Pose so its conveyor_belt.py controller never
        # runs and the LinearMotor velocity stays at 0. Navigate the scene tree to
        # get a direct handle to the motor's velocity field so we can drive it from
        # the supervisor side.
        if scara_node:
            try:
                motor = (scara_node.getField("children")
                         .getMFNode(0)          # Track
                         .getField("device")
                         .getMFNode(0))         # LinearMotor "belt_motor"
                self.scara_motor_vel = motor.getField("velocity")
            except Exception as e:
                print(f"{LOG_PREFIX}warning: could not get SCARA motor velocity field: {e}", flush=True)
        # All belts start stopped; LLM/UI commands start them.
        self.conveyor_set_can(0.0)
        self.conveyor_set_fruit(0.0)

    def conveyor_set_can(self, speed):
        for f in self.can_belt_speed:
            if f:
                f.setSFFloat(speed)

    def conveyor_set_fruit(self, speed):
        if self.scara_belt_speed:
            self.scara_belt_speed.setSFFloat(speed)
        # Also drive the motor velocity directly (controller doesn't run for nested belt).
        if self.scara_motor_vel:
            self.scara_motor_vel.setSFFloat(speed)

    def ui_broadcast(self, msg):
        encoded = msg.encode() if isinstance(msg, str) else msg
        dead = []
        for sock, c in self.clients.items():
            if c.role == ROLE_UI:
                try:
                    sock.send(encoded)
                except BlockingIOError:
                    pass  # send buffer full — drop the log message, keep the connection
                except OSError:
                    dead.append(sock)
        for sock in dead:
            self.client_remove(sock)

    def log_and_ui(self, msg):
        print(msg, end='', flush=True)
        self.ui_broadcast(f"LOG|{msg}")

    def client_remove(self, sock):
        c = self.clients.pop(sock, None)
        if c is None:
            return
        try:
            sock.close()
        except OSError:
            pass
        for k in range(3):
            if self.ur_sock[k] is sock:
                self.ur_sock[k] = None
        if self.scara_sock is sock:
            self.scara_sock = None

    def arm_idx(self, role):
        if role == ROLE_UR3e:
            return 0
        if role == ROLE_UR5e:
            return 1
        if role == ROLE_UR10e:
            return 2
        return -1

    def parse_register(self, line):
        line = line.strip()
        if not line.startswith("REGISTER "):
            return ROLE_NONE
        name = line[9:].strip()
        return {"UI": ROLE_UI, "UR3e": ROLE_UR3e, "UR5e": ROLE_UR5e,
                "UR10e": ROLE_UR10e, "ScaraT6": ROLE_SCARA}.get(name, ROLE_NONE)

    def process_line(self, sock, line):
        c = self.clients.get(sock)
        if c is None:
            return
        line = line.strip()

        if c.role == ROLE_UI:
            if line == "CONTROL RUN":
                self.robot.simulationSetMode(Supervisor.SIMULATION_MODE_REAL_TIME)
                self.log_and_ui(f"{LOG_PREFIX}UI: simulation RUN\n")
            elif line == "CONTROL PAUSE":
                self.robot.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
                self.log_and_ui(f"{LOG_PREFIX}UI: simulation PAUSE\n")
            elif line == "CONTROL FAST":
                self.robot.simulationSetMode(Supervisor.SIMULATION_MODE_FAST)
                self.log_and_ui(f"{LOG_PREFIX}UI: simulation FAST\n")
            elif line == "CONVEYOR_STOP can":
                self.conveyor_set_can(0.0)
                self.log_and_ui(f"{LOG_PREFIX}UI: can conveyors STOPPED\n")
                self.ui_broadcast("LOG|conveyor|can|STOPPED\n")
            elif line == "CONVEYOR_START can":
                for k in range(3):
                    if self.can_belt_speed[k]:
                        self.can_belt_speed[k].setSFFloat(CAN_BELT_NOMINAL[k])
                self.log_and_ui(f"{LOG_PREFIX}UI: can conveyors STARTED\n")
                self.ui_broadcast("LOG|conveyor|can|STARTED\n")
            elif line == "CONVEYOR_STOP fruit":
                self.conveyor_set_fruit(0.0)
                self.log_and_ui(f"{LOG_PREFIX}UI: fruit conveyor STOPPED\n")
                self.ui_broadcast("LOG|conveyor|fruit|STOPPED\n")
            elif line == "CONVEYOR_START fruit":
                self.conveyor_set_fruit(SCARA_BELT_NOMINAL)
                self.log_and_ui(f"{LOG_PREFIX}UI: fruit conveyor STARTED\n")
                self.ui_broadcast("LOG|conveyor|fruit|STARTED\n")
            return

        if c.role == ROLE_SCARA:
            return

        if c.role == ROLE_NONE:
            role = self.parse_register(line)
            if role == ROLE_NONE:
                return
            c.role = role
            ai = self.arm_idx(role)
            if ai >= 0:
                old = self.ur_sock[ai]
                if old and old in self.clients:
                    self.client_remove(old)
                self.ur_sock[ai] = sock
                print(f"{LOG_PREFIX}registered arm {ARM_NAME[ai]}", flush=True)
                self.ui_broadcast(f"LOG|registered|{ARM_NAME[ai]}\n")
            elif role == ROLE_SCARA:
                old = self.scara_sock
                if old and old in self.clients:
                    self.client_remove(old)
                self.scara_sock = sock
                print(f"{LOG_PREFIX}registered ScaraT6", flush=True)
                self.ui_broadcast("LOG|registered|ScaraT6\n")
            elif role == ROLE_UI:
                print(f"{LOG_PREFIX}registered UI", flush=True)
                self.ui_broadcast("LOG|registered|UI\n")
            return

        ai = self.arm_idx(c.role)
        if ai >= 0 and line.startswith("TELEM "):
            parts = line.split()
            if len(parts) == 3:
                try:
                    d, w = float(parts[1]), float(parts[2])
                    self.telemetry_dist[ai] = d
                    self.telemetry_wrist[ai] = w
                    self.ui_broadcast(f"TELEM|{ARM_NAME[ai]}|{d:.8g}|{w:.8g}\n")
                except ValueError:
                    pass

    def send_arm_cmd(self, arm_index, cmd):
        sock = self.ur_sock[arm_index]
        if sock is None:
            return
        try:
            sock.sendall(f"CMD {cmd}\n".encode())
            self.log_and_ui(f"{LOG_PREFIX}-> {ARM_NAME[arm_index]}: sending command: {cmd}\n")
            self.ui_broadcast(f"CMD|{ARM_NAME[arm_index]}|{cmd}\n")
        except OSError:
            self.client_remove(sock)

    def send_scara_cmd(self, msg):
        sock = self.scara_sock
        if sock is None:
            return
        try:
            sock.sendall(f"{msg}\n".encode())
            self.log_and_ui(f"{LOG_PREFIX}-> ScaraT6: sending command: {msg}\n")
            self.ui_broadcast(f"CMD|ScaraT6|{msg}\n")
        except OSError:
            self.client_remove(sock)

    def scara_coordinator_step(self):
        if self.scara_sock is None:
            return
        i = self.scara_i
        if i == 0:
            self.send_scara_cmd("SCARA_HOME")
        elif i > 275:
            self.scara_i = -1
        elif i > 200:
            self.scara_fruit_type = random.randint(0, 1)
            self.send_scara_cmd(f"SCARA_SET_FRUIT {self.scara_fruit_type}")
        elif i > 90:
            self.send_scara_cmd("SCARA_MERGE")
            if i > 125:
                if self.scara_fruit_type:
                    self.send_scara_cmd("SCARA_SORT_ORANGE")
                else:
                    self.send_scara_cmd("SCARA_SORT_APPLE")
            else:
                self.send_scara_cmd("SCARA_SHAFT_UP")
        elif i > 75:
            self.send_scara_cmd("SCARA_MERGE")
        elif i > 55:
            self.send_scara_cmd("SCARA_SHAFT_DOWN")
        self.scara_i += 1

    def ur_phase_ticks(self):
        try:
            mult = max(1, min(1000, int(os.environ.get("UR_SPEED_MULT", "1"))))
        except ValueError:
            mult = 1
        t = (8 + mult - 1) // mult
        return max(8, min(64, t))

    def scara_stride(self):
        try:
            return max(1, min(1000, int(os.environ.get("SCARA_SPEED_DIV", "10"))))
        except ValueError:
            return 10

    def accept_new(self):
        while True:
            try:
                conn, _ = self.listen_sock.accept()
                conn.setblocking(False)
                self.clients[conn] = Client(conn)
                try:
                    conn.sendall(b"OK send REGISTER <UI|UR3e|UR5e|UR10e|ScaraT6> then newline\n")
                except OSError:
                    self.client_remove(conn)
            except BlockingIOError:
                break
            except OSError:
                break

    def recv_clients(self):
        dead = []
        for sock, c in list(self.clients.items()):
            try:
                data = sock.recv(1024)
                if not data:
                    dead.append(sock)
                    continue
                c.buf += data.decode(errors='replace')
                while '\n' in c.buf:
                    line, c.buf = c.buf.split('\n', 1)
                    self.process_line(sock, line)
            except BlockingIOError:
                pass
            except OSError:
                dead.append(sock)
        for sock in dead:
            self.client_remove(sock)

    def run(self):
        try:
            port = int(os.environ.get("COORDINATOR_TCP_PORT", "9099"))
        except ValueError:
            port = 9099

        self.belts_init()

        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_sock.bind(("127.0.0.1", port))
        self.listen_sock.listen(8)
        self.listen_sock.setblocking(False)
        print(f"{LOG_PREFIX}listening on 127.0.0.1:{port} (COORDINATOR_TCP_PORT)", flush=True)

        phase_ticks = self.ur_phase_ticks()
        stride = self.scara_stride()
        print(f"{LOG_PREFIX}UR phase ticks={phase_ticks}; SCARA coordinator stride={stride}", flush=True)

        while self.robot.step(self.timestep) != -1:
            self.accept_new()
            self.recv_clients()

            for i in range(3):
                if self.arms_counter[i] <= 0:
                    state = self.arms_state[i]
                    if state == WAITING:
                        if self.telemetry_dist[i] < 500:
                            self.arms_state[i] = GRASPING
                            self.arms_counter[i] = phase_ticks
                            self.send_arm_cmd(i, "GRASPING_CAN")
                    elif state == GRASPING:
                        self.send_arm_cmd(i, "ROTATING_ARM")
                        self.arms_state[i] = ROTATING
                    elif state == ROTATING:
                        if self.telemetry_wrist[i] < -2.3:
                            self.arms_counter[i] = phase_ticks
                            self.arms_state[i] = RELEASING
                            self.send_arm_cmd(i, "RELEASING_CAN")
                    elif state == RELEASING:
                        self.send_arm_cmd(i, "ROTATING_ARM_BACK")
                        self.arms_state[i] = ROTATING_BACK
                    elif state == ROTATING_BACK:
                        if self.telemetry_wrist[i] > -0.1:
                            self.arms_state[i] = WAITING
                            self.send_arm_cmd(i, "WAITING")
                self.arms_counter[i] -= 1

            self.scara_stride_ctr += 1
            if self.scara_stride_ctr % stride == 0:
                self.scara_coordinator_step()

            sim_wall_sleep_after_step(self.timestep)

        self.listen_sock.close()


if __name__ == "__main__":
    Coordinator().run()
