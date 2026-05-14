import os
import sys
import time
from controller import Robot


def sim_wall_sleep_after_step(timestep_ms):
    try:
        m = int(os.environ.get("SIM_SLOWDOWN", "10"))
    except ValueError:
        m = 10
    m = max(1, min(100, m))
    if m <= 1:
        return
    time.sleep((m - 1) * timestep_ms / 1000.0)


robot = Robot()
timestep = int(robot.getBasicTimeStep())

speed = float(sys.argv[1])
timer = float(sys.argv[2])

belt_motor = robot.getDevice("belt_motor")
belt_motor.setPosition(float('inf'))
belt_motor.setVelocity(speed)

while robot.step(timestep) != -1:
    sim_wall_sleep_after_step(timestep)
    if timer > 0 and robot.getTime() >= timer:
        belt_motor.setVelocity(0.0)
        robot.step(timestep)
        sim_wall_sleep_after_step(timestep)
        break
