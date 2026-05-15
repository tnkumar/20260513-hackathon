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

/*
 * Supervisor coordinator: drives UR arms and optional ScaraT6 over TCP
 * (no Webots Emitter/Receiver). UI clients register as REGISTER UI and
 * receive pipe-delimited lines (LOG|…, CMD|…, TELEM|…).
 */

#include <webots/robot.h>
#include <webots/supervisor.h>

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* Extra real-time delay after each wb_robot_step so wall clock ~= SIM_SLOWDOWN x slower (default 10). */
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

#define NUM_ARMS 3
#define MAX_CLIENTS 32
#define LOG_PREFIX "coordinator: "

static const char *const ARM_NAME[NUM_ARMS] = {"UR3e", "UR5e", "UR10e"};

enum OperationMode { MODE_BALANCED, MODE_FRUIT_PRIORITY, MODE_CAN_PRIORITY, MODE_LOW_POWER, MODE_HIGH_CAPACITY };
enum TargetType { TARGET_NONE, TARGET_CANS, TARGET_FRUITS, TARGET_APPLES, TARGET_ORANGES };

typedef struct {
  int robot_enabled[NUM_ARMS];
  int scara_enabled;
  int can_line_enabled;
  int fruit_line_enabled;
  enum OperationMode mode;
  enum TargetType target_type;
  int target_count;
  int cans;
  int arm_cans[NUM_ARMS];
  int apples;
  int oranges;
} WorkcellState;

static WorkcellState workcell;

typedef struct {
  double distance;
  double wrist;
} ArmTelemetry;

enum State { WAITING, GRASPING, ROTATING, RELEASING, ROTATING_BACK };

typedef struct {
  int state;
  int counter;
} ArmState;

enum ClientRole {
  ROLE_NONE,
  ROLE_UI,
  ROLE_UR3e,
  ROLE_UR5e,
  ROLE_UR10e,
  ROLE_SCARA
};

typedef struct {
  int fd;
  enum ClientRole role;
  char buf[512];
  size_t len;
} Client;

static Client clients[MAX_CLIENTS];
static int listen_fd = -1;
static int ur_fd[NUM_ARMS];
static int scara_fd = -1;

static void send_arm_cmd(int arm_index, const char *cmd);
static void send_scara_cmd(const char *msg);

static int set_nonblocking(int fd) {
  int flags = fcntl(fd, F_GETFL, 0);
  if (flags < 0)
    return -1;
  return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static int tcp_listen(int port) {
  int s = socket(AF_INET, SOCK_STREAM, 0);
  if (s < 0)
    return -1;
  int one = 1;
  setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
  struct sockaddr_in a;
  memset(&a, 0, sizeof(a));
  a.sin_family = AF_INET;
  a.sin_port = htons((unsigned short)port);
  a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(s, (struct sockaddr *)&a, sizeof(a)) < 0) {
    perror(LOG_PREFIX "bind");
    close(s);
    return -1;
  }
  if (listen(s, 8) < 0) {
    perror(LOG_PREFIX "listen");
    close(s);
    return -1;
  }
  set_nonblocking(s);
  return s;
}

static void strip_trailing_crlf(char *s) {
  size_t n = strlen(s);
  while (n > 0 && (s[n - 1] == '\r' || s[n - 1] == '\n')) {
    s[n - 1] = '\0';
    n--;
  }
}

static void ui_broadcast_raw(const char *msg, size_t len) {
  int i;
  for (i = 0; i < MAX_CLIENTS; ++i) {
    if (clients[i].fd >= 0 && clients[i].role == ROLE_UI) {
      ssize_t w = write(clients[i].fd, msg, len);
      (void)w;
    }
  }
}

static void ui_broadcast_fmt(const char *fmt, ...) {
  char msg[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  ui_broadcast_raw(msg, strlen(msg));
}

static void log_and_ui(const char *fmt, ...) {
  char msg[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  printf("%s", msg);
  ui_broadcast_fmt("LOG|%s", msg);
}

static const char *mode_name(enum OperationMode mode) {
  switch (mode) {
    case MODE_FRUIT_PRIORITY:
      return "fruit_priority";
    case MODE_CAN_PRIORITY:
      return "can_priority";
    case MODE_LOW_POWER:
      return "low_power";
    case MODE_HIGH_CAPACITY:
      return "high_capacity";
    case MODE_BALANCED:
    default:
      return "balanced";
  }
}

static const char *target_name(enum TargetType target) {
  switch (target) {
    case TARGET_CANS:
      return "cans";
    case TARGET_FRUITS:
      return "fruits";
    case TARGET_APPLES:
      return "apples";
    case TARGET_ORANGES:
      return "oranges";
    case TARGET_NONE:
    default:
      return "none";
  }
}

static void broadcast_state(void) {
  ui_broadcast_fmt("STATE|mode|%s\n", mode_name(workcell.mode));
  ui_broadcast_fmt("STATE|line|can|%s\n", workcell.can_line_enabled ? "running" : "stopped");
  ui_broadcast_fmt("STATE|line|fruit|%s\n", workcell.fruit_line_enabled ? "running" : "stopped");
  ui_broadcast_fmt("STATE|robot|UR3e|%s\n", workcell.robot_enabled[0] ? "enabled" : "disabled");
  ui_broadcast_fmt("STATE|robot|UR5e|%s\n", workcell.robot_enabled[1] ? "enabled" : "disabled");
  ui_broadcast_fmt("STATE|robot|UR10e|%s\n", workcell.robot_enabled[2] ? "enabled" : "disabled");
  ui_broadcast_fmt("STATE|robot|ScaraT6|%s\n", workcell.scara_enabled ? "enabled" : "disabled");
  ui_broadcast_fmt("STATE|target|%s|%d\n", target_name(workcell.target_type), workcell.target_count);
  ui_broadcast_fmt("COUNT|cans|%d\n", workcell.cans);
  ui_broadcast_fmt("COUNT|apples|%d\n", workcell.apples);
  ui_broadcast_fmt("COUNT|oranges|%d\n", workcell.oranges);
  ui_broadcast_fmt("COUNT|fruits|%d\n", workcell.apples + workcell.oranges);
}

static int target_reached(void) {
  if (workcell.target_count <= 0)
    return 0;
  switch (workcell.target_type) {
    case TARGET_CANS:
      return workcell.cans >= workcell.target_count;
    case TARGET_FRUITS:
      return workcell.apples + workcell.oranges >= workcell.target_count;
    case TARGET_APPLES:
      return workcell.apples >= workcell.target_count;
    case TARGET_ORANGES:
      return workcell.oranges >= workcell.target_count;
    case TARGET_NONE:
    default:
      return 0;
  }
}

static void maybe_complete_target(void) {
  if (!target_reached())
    return;
  log_and_ui(LOG_PREFIX "production target reached: %s %d; returning to balanced mode\n", target_name(workcell.target_type),
             workcell.target_count);
  workcell.target_type = TARGET_NONE;
  workcell.target_count = 0;
  workcell.mode = MODE_BALANCED;
  workcell.can_line_enabled = 1;
  workcell.fruit_line_enabled = 1;
  broadcast_state();
}

static int arm_index_from_name(const char *name) {
  int i;
  for (i = 0; i < NUM_ARMS; ++i) {
    if (strcmp(name, ARM_NAME[i]) == 0)
      return i;
  }
  return -1;
}

static void apply_mode(enum OperationMode mode) {
  workcell.mode = mode;
  workcell.can_line_enabled = 1;
  workcell.fruit_line_enabled = 1;
  if (mode == MODE_BALANCED || mode == MODE_HIGH_CAPACITY) {
    workcell.robot_enabled[0] = 1;
    workcell.robot_enabled[1] = 1;
    workcell.robot_enabled[2] = 1;
    workcell.scara_enabled = 1;
  } else if (mode == MODE_LOW_POWER) {
    workcell.robot_enabled[2] = 0;
  }
  log_and_ui(LOG_PREFIX "operation mode set to %s\n", mode_name(mode));
  broadcast_state();
}

static void handle_ui_control_line(char *line) {
  char a[64], b[64], c[64];
  int n;
  if (strcmp(line, "CONTROL RUN") == 0) {
    wb_supervisor_simulation_set_mode(WB_SUPERVISOR_SIMULATION_MODE_REAL_TIME);
    printf(LOG_PREFIX "UI: simulation RUN\n");
    ui_broadcast_fmt("LOG|UI|simulation RUN\n");
    return;
  }
  if (strcmp(line, "CONTROL PAUSE") == 0) {
    wb_supervisor_simulation_set_mode(WB_SUPERVISOR_SIMULATION_MODE_PAUSE);
    printf(LOG_PREFIX "UI: simulation PAUSE\n");
    ui_broadcast_fmt("LOG|UI|simulation PAUSE\n");
    return;
  }
  if (strcmp(line, "CONTROL FAST") == 0) {
    wb_supervisor_simulation_set_mode(WB_SUPERVISOR_SIMULATION_MODE_FAST);
    printf(LOG_PREFIX "UI: simulation FAST\n");
    ui_broadcast_fmt("LOG|UI|simulation FAST\n");
    return;
  }
  if (strcmp(line, "CONTROL STATUS") == 0) {
    broadcast_state();
    return;
  }
  if (sscanf(line, "CONTROL MODE %63s", a) == 1) {
    if (strcmp(a, "BALANCED") == 0)
      apply_mode(MODE_BALANCED);
    else if (strcmp(a, "FRUIT_PRIORITY") == 0)
      apply_mode(MODE_FRUIT_PRIORITY);
    else if (strcmp(a, "CAN_PRIORITY") == 0)
      apply_mode(MODE_CAN_PRIORITY);
    else if (strcmp(a, "LOW_POWER") == 0)
      apply_mode(MODE_LOW_POWER);
    else if (strcmp(a, "HIGH_CAPACITY") == 0)
      apply_mode(MODE_HIGH_CAPACITY);
    return;
  }
  if (sscanf(line, "CONTROL %63s %63s", a, b) == 2 && (strcmp(a, "ENABLE") == 0 || strcmp(a, "DISABLE") == 0)) {
    const int enabled = strcmp(a, "ENABLE") == 0;
    int ai = arm_index_from_name(b);
    if (ai >= 0) {
      workcell.robot_enabled[ai] = enabled;
      log_and_ui(LOG_PREFIX "%s %s by operator\n", ARM_NAME[ai], enabled ? "enabled" : "disabled");
      if (!enabled)
        send_arm_cmd(ai, "WAITING");
      broadcast_state();
    } else if (strcmp(b, "ScaraT6") == 0) {
      workcell.scara_enabled = enabled;
      log_and_ui(LOG_PREFIX "ScaraT6 %s by operator\n", enabled ? "enabled" : "disabled");
      if (!enabled)
        send_scara_cmd("SCARA_HOME");
      broadcast_state();
    }
    return;
  }
  if (sscanf(line, "CONTROL LINE %63s %63s", a, b) == 2) {
    int enabled = strcmp(b, "START") == 0;
    if (strcmp(a, "CAN") == 0) {
      workcell.can_line_enabled = enabled;
      log_and_ui(LOG_PREFIX "can line %s\n", enabled ? "started" : "stopped");
    } else if (strcmp(a, "FRUIT") == 0) {
      workcell.fruit_line_enabled = enabled;
      log_and_ui(LOG_PREFIX "fruit line %s\n", enabled ? "started" : "stopped");
      if (!enabled)
        send_scara_cmd("SCARA_HOME");
    }
    broadcast_state();
    return;
  }
  if (strcmp(line, "CONTROL TARGET CLEAR") == 0) {
    workcell.target_type = TARGET_NONE;
    workcell.target_count = 0;
    log_and_ui(LOG_PREFIX "production target cleared\n");
    broadcast_state();
    return;
  }
  n = 0;
  if (sscanf(line, "CONTROL TARGET %63s %d", c, &n) == 2 && n > 0) {
    if (strcmp(c, "CANS") == 0)
      workcell.target_type = TARGET_CANS;
    else if (strcmp(c, "FRUITS") == 0)
      workcell.target_type = TARGET_FRUITS;
    else if (strcmp(c, "APPLES") == 0)
      workcell.target_type = TARGET_APPLES;
    else if (strcmp(c, "ORANGES") == 0)
      workcell.target_type = TARGET_ORANGES;
    else
      return;
    workcell.target_count = n;
    log_and_ui(LOG_PREFIX "production target set: %s %d\n", target_name(workcell.target_type), n);
    broadcast_state();
    return;
  }
}

static int client_slot_for_fd(int fd) {
  int i;
  for (i = 0; i < MAX_CLIENTS; ++i) {
    if (clients[i].fd == fd)
      return i;
  }
  return -1;
}

static void client_remove(int idx) {
  int fd;
  int k;
  if (idx < 0 || idx >= MAX_CLIENTS)
    return;
  fd = clients[idx].fd;
  if (fd < 0)
    return;
  close(fd);
  clients[idx].fd = -1;
  clients[idx].role = ROLE_NONE;
  clients[idx].len = 0;
  for (k = 0; k < NUM_ARMS; ++k) {
    if (ur_fd[k] == fd)
      ur_fd[k] = -1;
  }
  if (scara_fd == fd)
    scara_fd = -1;
}

static int client_add(int fd) {
  int i;
  for (i = 0; i < MAX_CLIENTS; ++i) {
    if (clients[i].fd < 0) {
      clients[i].fd = fd;
      clients[i].role = ROLE_NONE;
      clients[i].len = 0;
      return i;
    }
  }
  close(fd);
  return -1;
}

static int arm_idx_from_role(enum ClientRole r) {
  if (r == ROLE_UR3e)
    return 0;
  if (r == ROLE_UR5e)
    return 1;
  if (r == ROLE_UR10e)
    return 2;
  return -1;
}

static void kick_arm_slot(int slot) {
  int fd = ur_fd[slot];
  int idx;
  if (fd < 0)
    return;
  idx = client_slot_for_fd(fd);
  if (idx >= 0)
    client_remove(idx);
}

static void kick_scara_slot(void) {
  int idx;
  if (scara_fd < 0)
    return;
  idx = client_slot_for_fd(scara_fd);
  if (idx >= 0)
    client_remove(idx);
}

static enum ClientRole parse_register(char *line) {
  strip_trailing_crlf(line);
  if (strncmp(line, "REGISTER ", 9) != 0)
    return ROLE_NONE;
  line += 9;
  while (*line == ' ' || *line == '\t')
    line++;
  if (strcmp(line, "UI") == 0)
    return ROLE_UI;
  if (strcmp(line, "UR3e") == 0)
    return ROLE_UR3e;
  if (strcmp(line, "UR5e") == 0)
    return ROLE_UR5e;
  if (strcmp(line, "UR10e") == 0)
    return ROLE_UR10e;
  if (strcmp(line, "ScaraT6") == 0)
    return ROLE_SCARA;
  return ROLE_NONE;
}

static void process_client_line(int idx, char *line, ArmTelemetry *telemetry) {
  Client *c = &clients[idx];
  if (c->role == ROLE_UI) {
    strip_trailing_crlf(line);
    handle_ui_control_line(line);
    return;
  }
  if (c->role == ROLE_SCARA)
    return;
  if (c->role == ROLE_NONE) {
    enum ClientRole r = parse_register(line);
    if (r != ROLE_NONE) {
      int ai = arm_idx_from_role(r);
      c->role = r;
      if (ai >= 0) {
        kick_arm_slot(ai);
        ur_fd[ai] = c->fd;
        printf(LOG_PREFIX "registered arm %s on fd %d\n", ARM_NAME[ai], c->fd);
        ui_broadcast_fmt("LOG|registered|%s\n", ARM_NAME[ai]);
      } else if (r == ROLE_SCARA) {
        kick_scara_slot();
        scara_fd = c->fd;
        printf(LOG_PREFIX "registered ScaraT6 on fd %d\n", c->fd);
        ui_broadcast_fmt("LOG|registered|ScaraT6\n");
      } else if (r == ROLE_UI) {
        printf(LOG_PREFIX "registered UI on fd %d\n", c->fd);
        ui_broadcast_fmt("LOG|registered|UI\n");
        broadcast_state();
      }
    }
    return;
  }
  {
    int ai = arm_idx_from_role(c->role);
    double d, w;
    if (ai >= 0 && sscanf(line, "TELEM %lf %lf", &d, &w) == 2) {
      telemetry[ai].distance = d;
      telemetry[ai].wrist = w;
      ui_broadcast_fmt("TELEM|%s|%.8g|%.8g\n", ARM_NAME[ai], d, w);
    }
  }
}

static void flush_lines(int idx, ArmTelemetry *telemetry) {
  Client *c = &clients[idx];
  for (;;) {
    char *nl = (char *)memchr(c->buf, '\n', c->len);
    char line[512];
    size_t rest;
    if (!nl)
      break;
    *nl = '\0';
    if ((size_t)(nl - c->buf) < sizeof(line))
      strncpy(line, c->buf, sizeof(line) - 1);
    else {
      strncpy(line, c->buf, sizeof(line) - 1);
      line[sizeof(line) - 1] = '\0';
    }
    rest = c->len - (size_t)(nl - c->buf) - 1;
    memmove(c->buf, nl + 1, rest);
    c->len = rest;
    process_client_line(idx, line, telemetry);
  }
}

static void recv_clients(ArmTelemetry *telemetry) {
  int i;
  for (i = 0; i < MAX_CLIENTS; ++i) {
    ssize_t n;
    if (clients[i].fd < 0)
      continue;
    n = read(clients[i].fd, clients[i].buf + clients[i].len, sizeof(clients[i].buf) - 1 - clients[i].len);
    if (n == 0) {
      client_remove(i);
      continue;
    }
    if (n < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK)
        continue;
      client_remove(i);
      continue;
    }
    clients[i].len += (size_t)n;
    clients[i].buf[clients[i].len] = '\0';
    flush_lines(i, telemetry);
  }
}

static void accept_new(void) {
  for (;;) {
    struct sockaddr_in a;
    socklen_t sl = sizeof(a);
    int fd = accept(listen_fd, (struct sockaddr *)&a, &sl);
    int idx;
    if (fd < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK)
        break;
      break;
    }
    set_nonblocking(fd);
    idx = client_add(fd);
    if (idx < 0)
      continue;
    {
      const char *welcome = "OK send REGISTER <UI|UR3e|UR5e|UR10e|ScaraT6> then newline\n";
      ssize_t w = write(fd, welcome, strlen(welcome));
      (void)w;
    }
  }
}

static void send_arm_cmd(int arm_index, const char *cmd) {
  char buf[96];
  ssize_t w;
  if (ur_fd[arm_index] < 0)
    return;
  snprintf(buf, sizeof(buf), "CMD %s\n", cmd);
  w = write(ur_fd[arm_index], buf, strlen(buf));
  (void)w;
  log_and_ui(LOG_PREFIX "-> %s: sending command: %s\n", ARM_NAME[arm_index], cmd);
  ui_broadcast_fmt("CMD|%s|%s\n", ARM_NAME[arm_index], cmd);
  if (strcmp(cmd, "RELEASING_CAN") == 0) {
    workcell.cans++;
    workcell.arm_cans[arm_index]++;
    ui_broadcast_fmt("COUNT|cans|%d\n", workcell.cans);
    ui_broadcast_fmt("COUNT|%s|cans|%d\n", ARM_NAME[arm_index], workcell.arm_cans[arm_index]);
    maybe_complete_target();
  }
}

static void send_scara_cmd(const char *msg) {
  char buf[256];
  ssize_t w;
  if (scara_fd < 0)
    return;
  snprintf(buf, sizeof(buf), "%s\n", msg);
  w = write(scara_fd, buf, strlen(buf));
  (void)w;
  log_and_ui(LOG_PREFIX "-> ScaraT6: sending command: %s\n", msg);
  ui_broadcast_fmt("CMD|ScaraT6|%s\n", msg);
}

/* Mirrors timestep logic from scara_food_industry.py (same if/elif order, then i++). */
static void scara_coordinator_step(void) {
  static int i = 0;
  static int fruitType = 0;
  static int sorted_this_cycle = 0;
  char buf[80];

  if (scara_fd < 0 || !workcell.scara_enabled || !workcell.fruit_line_enabled)
    return;

  if (i == 0) {
    sorted_this_cycle = 0;
    send_scara_cmd("SCARA_HOME");
  } else if (i > 275) {
    i = -1;
  } else if (i > 200) {
    fruitType = rand() % 2;
    snprintf(buf, sizeof(buf), "SCARA_SET_FRUIT %d", fruitType);
    send_scara_cmd(buf);
  } else if (i > 90) {
    send_scara_cmd("SCARA_MERGE");
    if (i > 125) {
      if (fruitType) {
        send_scara_cmd("SCARA_SORT_ORANGE");
        if (!sorted_this_cycle) {
          workcell.oranges++;
          sorted_this_cycle = 1;
          ui_broadcast_fmt("COUNT|oranges|%d\n", workcell.oranges);
          ui_broadcast_fmt("COUNT|fruits|%d\n", workcell.apples + workcell.oranges);
          maybe_complete_target();
        }
      } else {
        send_scara_cmd("SCARA_SORT_APPLE");
        if (!sorted_this_cycle) {
          workcell.apples++;
          sorted_this_cycle = 1;
          ui_broadcast_fmt("COUNT|apples|%d\n", workcell.apples);
          ui_broadcast_fmt("COUNT|fruits|%d\n", workcell.apples + workcell.oranges);
          maybe_complete_target();
        }
      }
    } else
      send_scara_cmd("SCARA_SHAFT_UP");
  } else if (i > 75) {
    send_scara_cmd("SCARA_MERGE");
  } else if (i > 55) {
    send_scara_cmd("SCARA_SHAFT_DOWN");
  }

  i++;
}

/* UR phase wait in coordinator steps (legacy base 8). Never below 8 so the gripper
 * can close / open before the arm moves (GRASPING_CAN / RELEASING_CAN need physics time). */
static int ur_phase_ticks_from_env(void) {
  const char *e = getenv("UR_SPEED_MULT");
  int mult = 1;
  if (e && e[0]) {
    mult = atoi(e);
    if (mult < 1)
      mult = 1;
    if (mult > 1000)
      mult = 1000;
  }
  {
    const int base = 8;
    int t = (base + mult - 1) / mult;
    if (t < 8)
      t = 8;
    if (t > 64)
      t = 64;
    return t;
  }
}

/* Run scara_coordinator_step only every N supervisor steps (slow SCARA script vs sim time). */
static int scara_stride_from_env(void) {
  const char *e = getenv("SCARA_SPEED_DIV");
  int div = 10;
  if (e && e[0]) {
    div = atoi(e);
    if (div < 1)
      div = 1;
    if (div > 1000)
      div = 1000;
  }
  return div;
}

static int scara_stride_for_mode(int env_stride) {
  switch (workcell.mode) {
    case MODE_FRUIT_PRIORITY:
      return env_stride > 4 ? 4 : env_stride;
    case MODE_CAN_PRIORITY:
      return env_stride < 18 ? 18 : env_stride;
    case MODE_LOW_POWER:
      return env_stride < 24 ? 24 : env_stride;
    case MODE_HIGH_CAPACITY:
      return env_stride > 3 ? 3 : env_stride;
    case MODE_BALANCED:
    default:
      return env_stride;
  }
}

int main(int argc, char **argv) {
  int port = 9099;
  int k;
  const char *env_port;
  (void)argc;
  (void)argv;
  env_port = getenv("COORDINATOR_TCP_PORT");
  if (env_port && env_port[0])
    port = atoi(env_port);
  if (argc >= 2 && argv[1][0])
    port = atoi(argv[1]);

  memset(clients, 0, sizeof(clients));
  for (k = 0; k < MAX_CLIENTS; ++k)
    clients[k].fd = -1;
  for (k = 0; k < NUM_ARMS; ++k)
    ur_fd[k] = -1;
  scara_fd = -1;
  memset(&workcell, 0, sizeof(workcell));
  workcell.robot_enabled[0] = 1;
  workcell.robot_enabled[1] = 1;
  workcell.robot_enabled[2] = 1;
  workcell.scara_enabled = 1;
  workcell.can_line_enabled = 1;
  workcell.fruit_line_enabled = 1;
  workcell.mode = MODE_BALANCED;
  workcell.target_type = TARGET_NONE;

  wb_robot_init();
  const int time_step = (int)wb_robot_get_basic_time_step();

  listen_fd = tcp_listen(port);
  if (listen_fd < 0) {
    fprintf(stderr, LOG_PREFIX "TCP listen on port %d failed (set COORDINATOR_TCP_PORT?)\n", port);
    wb_robot_cleanup();
    return 1;
  }
  printf(LOG_PREFIX "listening on 127.0.0.1:%d (COORDINATOR_TCP_PORT)\n", port);

  {
    ArmState arms[NUM_ARMS] = {{WAITING, 0}, {WAITING, 0}, {WAITING, 0}};
    ArmTelemetry telemetry[NUM_ARMS];
    const int ur_phase_ticks = ur_phase_ticks_from_env();
    const int env_scara_stride = scara_stride_from_env();
    static unsigned scara_stride_ctr = 0;

    for (k = 0; k < NUM_ARMS; ++k) {
      telemetry[k].distance = 10000.0;
      telemetry[k].wrist = 0.0;
    }
    printf(LOG_PREFIX "UR phase ticks=%d (UR_SPEED_MULT, min 8 for grasp physics); SCARA coordinator stride=%d (SCARA_SPEED_DIV)\n",
           ur_phase_ticks, env_scara_stride);

    while (wb_robot_step(time_step) != -1) {
      int scara_stride;
      accept_new();
      recv_clients(telemetry);

      {
        int i;
        for (i = 0; i < NUM_ARMS; i++) {
          if (arms[i].counter <= 0) {
            switch (arms[i].state) {
              case WAITING:
                if (workcell.robot_enabled[i] && workcell.can_line_enabled && telemetry[i].distance < 500) {
                  arms[i].state = GRASPING;
                  arms[i].counter = ur_phase_ticks;
                  send_arm_cmd(i, "GRASPING_CAN");
                }
                break;
              case GRASPING:
                send_arm_cmd(i, "ROTATING_ARM");
                arms[i].state = ROTATING;
                break;
              case ROTATING:
                if (telemetry[i].wrist < -2.3) {
                  arms[i].counter = ur_phase_ticks;
                  arms[i].state = RELEASING;
                  send_arm_cmd(i, "RELEASING_CAN");
                }
                break;
              case RELEASING:
                send_arm_cmd(i, "ROTATING_ARM_BACK");
                arms[i].state = ROTATING_BACK;
                break;
              case ROTATING_BACK:
                if (telemetry[i].wrist > -0.1) {
                  arms[i].state = WAITING;
                  send_arm_cmd(i, "WAITING");
                }
                break;
            }
          }
          arms[i].counter--;
        }
      }

      scara_stride = scara_stride_for_mode(env_scara_stride);
      if ((++scara_stride_ctr % (unsigned)scara_stride) == 0u)
        scara_coordinator_step();
      sim_wall_sleep_after_step(time_step);
    }
  }

  if (listen_fd >= 0)
    close(listen_fd);
  wb_robot_cleanup();
  return 0;
}
