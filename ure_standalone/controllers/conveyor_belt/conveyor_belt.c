/*
 * Copyright 1996-2024 Cyberbotics Ltd.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <stdlib.h>
#include <webots/motor.h>
#include <webots/robot.h>

#include <assert.h>
#include <stdio.h>
#include <unistd.h>

static void sim_wall_sleep_after_step(int timestep_ms) {
  const char *e = getenv("SIM_SLOWDOWN");
  int m = 10;
  if (e && e[0]) {
    m = atoi(e);
    if (m < 1)
      m = 1;
    if (m > 100)
      m = 100;
  }
  if (m <= 1)
    return;
  usleep((unsigned int)((m - 1) * timestep_ms * 1000u));
}

// cppcheck-suppress constParameter
int main(int argc, char *argv[]) {
  wb_robot_init();
  assert(argc == 3);  // speed and timer excepted as argument.

  const int timestep = (int)wb_robot_get_basic_time_step();

  double speed;
  sscanf(argv[1], "%lf", &speed);

  double timer;
  sscanf(argv[2], "%lf", &timer);

  WbDeviceTag belt_motor = wb_robot_get_device("belt_motor");
  wb_motor_set_position(belt_motor, INFINITY);
  wb_motor_set_velocity(belt_motor, speed);

  while (wb_robot_step(timestep) != -1) {
    sim_wall_sleep_after_step(timestep);
    if (timer > 0 && wb_robot_get_time() >= timer) {
      wb_motor_set_velocity(belt_motor, 0.0);
      wb_robot_step(timestep);
      sim_wall_sleep_after_step(timestep);
      break;
    }
  }

  wb_robot_cleanup();
  return EXIT_SUCCESS;
}
