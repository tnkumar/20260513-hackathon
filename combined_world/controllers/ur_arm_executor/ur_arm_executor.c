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

#include <webots/distance_sensor.h>
#include <webots/motor.h>
#include <webots/position_sensor.h>
#include <webots/robot.h>

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h> /* getenv */
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* Last CMD from coordinator; used to re-apply grasp/release each step (TCP split vs monolithic demo). */
static char g_last_ur_cmd[40] = "";

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

/* Finger / arm targets match example_code/ure_can_grasper.c (Cyberbotics demo). */
static void apply_command(const char *cmd, WbDeviceTag hand_motors[3], WbDeviceTag ur_motors[4],
                          const double target_positions[4]) {
  int i;
  if (strcmp(cmd, "WAITING") == 0) {
    /* No motor change (matches original WAITING). */
  } else if (strcmp(cmd, "GRASPING_CAN") == 0) {
    for (i = 0; i < 3; ++i)
      wb_motor_set_position(hand_motors[i], 0.85);
  } else if (strcmp(cmd, "ROTATING_ARM") == 0) {
    for (i = 0; i < 4; ++i)
      wb_motor_set_position(ur_motors[i], target_positions[i]);
  } else if (strcmp(cmd, "RELEASING_CAN") == 0) {
    for (i = 0; i < 3; ++i)
      wb_motor_set_position(hand_motors[i], wb_motor_get_min_position(hand_motors[i]));
  } else if (strcmp(cmd, "ROTATING_ARM_BACK") == 0) {
    for (i = 0; i < 4; ++i)
      wb_motor_set_position(ur_motors[i], 0.0);
  }
}

static int set_nonblocking(int fd) {
  int flags = fcntl(fd, F_GETFL, 0);
  if (flags < 0)
    return -1;
  return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static int connect_tcp(const char *host, int port) {
  struct sockaddr_in a;
  int s;
  memset(&a, 0, sizeof(a));
  a.sin_family = AF_INET;
  a.sin_port = htons((unsigned short)port);
  if (inet_pton(AF_INET, host, &a.sin_addr) != 1)
    return -1;
  s = socket(AF_INET, SOCK_STREAM, 0);
  if (s < 0)
    return -1;
  if (connect(s, (struct sockaddr *)&a, sizeof(a)) < 0) {
    close(s);
    return -1;
  }
  return s;
}

static int coordinator_port(void) {
  const char *e = getenv("COORDINATOR_TCP_PORT");
  if (e && e[0])
    return atoi(e);
  return 9099;
}

static void coordinator_host(char *out, size_t outsz) {
  const char *e = getenv("COORDINATOR_HOST");
  if (e && e[0])
    snprintf(out, outsz, "%s", e);
  else
    snprintf(out, outsz, "127.0.0.1");
}

static void drain_socket_commands(int *sock_ptr, char *line_buf, size_t *line_len, WbDeviceTag hand_motors[3],
                                  WbDeviceTag ur_motors[4], const double target_positions[4]) {
  ssize_t n;
  char *nl;
  int sock = *sock_ptr;
  if (sock < 0)
    return;
  n = read(sock, line_buf + *line_len, 256 - 1 - *line_len);
  if (n == 0) {
    close(sock);
    *sock_ptr = -1;
    return;
  }
  if (n < 0) {
    if (errno != EAGAIN && errno != EWOULDBLOCK) {
      close(sock);
      *sock_ptr = -1;
    }
    return;
  }
  *line_len += (size_t)n;
  line_buf[*line_len] = '\0';
  for (;;) {
    nl = strchr(line_buf, '\n');
    if (!nl)
      break;
    *nl = '\0';
    if (strncmp(line_buf, "CMD ", 4) == 0) {
      const char *c = line_buf + 4;
      apply_command(c, hand_motors, ur_motors, target_positions);
      snprintf(g_last_ur_cmd, sizeof(g_last_ur_cmd), "%s", c);
    }
    {
      size_t rest = *line_len - (size_t)(nl - line_buf) - 1;
      memmove(line_buf, nl + 1, rest);
      *line_len = rest;
      line_buf[*line_len] = '\0';
    }
  }
}

int main(int argc, char **argv) {
  signal(SIGPIPE, SIG_IGN);
  wb_robot_init();
  const int time_step = (int)wb_robot_get_basic_time_step();
  double speed = 1.0;
  const double target_positions[] = {-1.88, -2.14, -2.38, -1.51};
  const char *role = "UR3e";
  char host[64];
  char line_buf[256];
  size_t line_len = 0;
  int coord_sock = -1;
  int port = coordinator_port();

  if (argc >= 2)
    sscanf(argv[1], "%lf", &speed);
  if (argc >= 3)
    role = argv[2];

  coordinator_host(host, sizeof(host));

  WbDeviceTag hand_motors[3];
  hand_motors[0] = wb_robot_get_device("finger_1_joint_1");
  hand_motors[1] = wb_robot_get_device("finger_2_joint_1");
  hand_motors[2] = wb_robot_get_device("finger_middle_joint_1");
  WbDeviceTag ur_motors[4];
  ur_motors[0] = wb_robot_get_device("shoulder_lift_joint");
  ur_motors[1] = wb_robot_get_device("elbow_joint");
  ur_motors[2] = wb_robot_get_device("wrist_1_joint");
  ur_motors[3] = wb_robot_get_device("wrist_2_joint");
  int i;
  for (i = 0; i < 4; ++i)
    wb_motor_set_velocity(ur_motors[i], speed);
  /* example_code/ure_can_grasper.c does not set velocity on finger motors. */

  WbDeviceTag distance_sensor = wb_robot_get_device("distance sensor");
  wb_distance_sensor_enable(distance_sensor, time_step);

  WbDeviceTag position_sensor = wb_robot_get_device("wrist_1_joint_sensor");
  wb_position_sensor_enable(position_sensor, time_step);

  while (wb_robot_step(time_step) != -1) {
    const double dist = wb_distance_sensor_get_value(distance_sensor);
    const double wrist = wb_position_sensor_get_value(position_sensor);
    char tbuf[96];
    ssize_t w;
    char reg[80];

    if (coord_sock < 0) {
      coord_sock = connect_tcp(host, port);
      if (coord_sock >= 0) {
        set_nonblocking(coord_sock);
        line_len = 0;
        snprintf(reg, sizeof(reg), "REGISTER %s\n", role);
        w = write(coord_sock, reg, strlen(reg));
        (void)w;
      }
    }

    if (coord_sock >= 0) {
      snprintf(tbuf, sizeof(tbuf), "TELEM %.10g %.10g\n", dist, wrist);
      w = write(coord_sock, tbuf, strlen(tbuf));
      if (w < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
        close(coord_sock);
        coord_sock = -1;
      } else {
        drain_socket_commands(&coord_sock, line_buf, &line_len, hand_motors, ur_motors, target_positions);
        /* Hold finger targets every physics step like the single-process demo loop. */
        if (strcmp(g_last_ur_cmd, "GRASPING_CAN") == 0)
          apply_command("GRASPING_CAN", hand_motors, ur_motors, target_positions);
        else if (strcmp(g_last_ur_cmd, "RELEASING_CAN") == 0)
          apply_command("RELEASING_CAN", hand_motors, ur_motors, target_positions);
      }
      if (coord_sock < 0) {
        line_len = 0;
        g_last_ur_cmd[0] = '\0';
      }
    }
    sim_wall_sleep_after_step(time_step);
  }

  if (coord_sock >= 0)
    close(coord_sock);
  wb_robot_cleanup();
  return 0;
}
