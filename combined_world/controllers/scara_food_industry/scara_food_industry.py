# Copyright 1996-2024 Cyberbotics Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import socket
import time
from pathlib import Path

from controller import Supervisor


def _load_sim_config():
    config = Path(__file__).parent.parent / ".sim_config"
    if config.exists():
        for line in config.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_sim_config()


class BlinkingLED:
    def __init__(self, led_device):
        self.led_device = led_device
        self.on = True

    def toggle(self):
        self.led_device.set(self.on)
        self.on = not self.on


HOST = os.environ.get("COORDINATOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("COORDINATOR_TCP_PORT", "9099"))
SIM_SLOWDOWN = max(1, min(100, int(os.environ.get("SIM_SLOWDOWN", "10"))))


def connect_coordinator():
    for _ in range(400):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))
            s.sendall(b"REGISTER ScaraT6\n")
            s.setblocking(False)
            return s
        except OSError:
            time.sleep(0.05)
    return None


supervisor = Supervisor()
timestep = int(supervisor.getBasicTimeStep())

base_arm = supervisor.getDevice("base_arm_motor")
arm = supervisor.getDevice("arm_motor")
shaft_linear = supervisor.getDevice("shaft_linear_motor")
led = BlinkingLED(supervisor.getDevice("epson_led"))

coord_sock = connect_coordinator()
recv_buf = b""
if coord_sock is None:
    print("scara_food_industry: could not connect to coordinator TCP; SCARA commands disabled")

merged_tool = False
fruitType = 0
step = 0


def merge_tool(fruit_id, merged_tool):
    if not merged_tool:
        fruit = supervisor.getFromDef("fruit" + str(fruit_id))
        vaccum = supervisor.getFromDef("VACCUM")
        if fruit:
            poses = vaccum.getPosition()
            fruitTranslation = fruit.getField('translation')
            if fruitTranslation and poses:
                fruitTranslation.setSFVec3f([poses[0], poses[1], poses[2] - 0.07])
                fruit.resetPhysics()


def handle_command(msg):
    global fruitType
    msg = msg.strip()
    if msg == "SCARA_HOME":
        arm.setPosition(0.6)
        base_arm.setPosition(0.2)
    elif msg == "SCARA_SHAFT_DOWN":
        shaft_linear.setPosition(-0.148)
    elif msg == "SCARA_MERGE":
        merge_tool(fruitType, merged_tool)
    elif msg == "SCARA_SHAFT_UP":
        shaft_linear.setPosition(0)
    elif msg == "SCARA_SORT_ORANGE":
        base_arm.setPosition(0)
        arm.setPosition(-0.83)
    elif msg == "SCARA_SORT_APPLE":
        base_arm.setPosition(-0.50)
        arm.setPosition(-0.83)
    elif msg.startswith("SCARA_SET_FRUIT"):
        parts = msg.split()
        if len(parts) >= 2:
            fruitType = int(parts[1])
    else:
        print("scara_food_industry: unknown command:", repr(msg))


def poll_socket_commands():
    global coord_sock, recv_buf
    if coord_sock is None:
        return
    try:
        chunk = coord_sock.recv(4096)
    except BlockingIOError:
        return
    except OSError:
        coord_sock.close()
        coord_sock = None
        recv_buf = b""
        return
    if not chunk:
        coord_sock.close()
        coord_sock = None
        recv_buf = b""
        return
    recv_buf += chunk
    while True:
        nl = recv_buf.find(b"\n")
        if nl < 0:
            break
        line = recv_buf[:nl].decode("utf-8", errors="replace").strip()
        recv_buf = recv_buf[nl + 1:]
        if line:
            handle_command(line)


while supervisor.step(timestep) != -1:
    if step % 100 == 0:
        led.toggle()
    step += 1

    poll_socket_commands()
    if SIM_SLOWDOWN > 1:
        time.sleep((SIM_SLOWDOWN - 1) * timestep / 1000.0)
