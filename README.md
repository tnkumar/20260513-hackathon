# FactoryFlow Copilot

FactoryFlow Copilot is a Webots-based robotic workcell demo that shows how a factory manager can operate industrial robots through intent instead of low-level robot commands.

The project combines:

- A Universal Robots can-handling cell with `UR3e`, `UR5e`, and `UR10e`
- An Epson `ScaraT6` fruit-sorting cell
- A Webots supervisor coordinator that owns the real simulation state
- A React SaaS-style dashboard for operators
- An agent service that turns natural-language factory goals into safe workcell tools

The main idea is abstraction: the operator should not need to know motor positions, robot-specific command names, TCP messages, Webots APIs, conveyor speed fields, or SCARA motion phases. They should be able to say things like:

```text
Increase can production
Sort 6 fruits
Disable UR10e
Run low power mode
Give me a production report
```

The agent maps that intent to a small, controlled set of workcell tools. The coordinator then translates those high-level tools into the robot-specific behavior needed inside the simulation.

## Why This Matters

Industrial workcells often contain robots from different vendors, each with different APIs, motion programs, state machines, and safety constraints. A factory manager usually cares about production goals:

- Make more cans
- Prioritize fruit sorting
- Take a robot offline
- Stop a line
- Save power
- Check production counts

They usually should not have to care about:

- Which motor joint moves first
- What TCP string gets sent to a controller
- Whether the can cell is driven by UR robots and the fruit cell by a SCARA robot
- Whether Webots uses supervisor fields, position sensors, or controller-specific scripts

FactoryFlow demonstrates an abstraction layer where the agent is the intent interpreter and the coordinator is the execution boundary.

## Abstraction Model

The application separates the system into three levels.

### 1. Operator Intent

The factory manager uses the dashboard chat panel and types natural-language requests.

Examples:

```text
Increase can production
Prioritize fruit sorting
Handle 5 cans
Stop the fruit line
Take UR10e offline for maintenance
```

The operator does not issue raw robot commands.

### 2. Agent Tools

The agent receives the operator request and must choose exactly one safe tool:

```text
set_operation_mode
set_production_target
enable_robot
disable_robot
start_line
stop_line
pause_simulation
resume_simulation
fast_simulation
clear_production_target
get_workcell_status
```

These tools are intentionally robot-agnostic. For example:

- `set_operation_mode(mode="can_priority")` means optimize the workcell toward can output.
- `set_operation_mode(mode="fruit_priority")` means optimize the workcell toward fruit sorting.
- `disable_robot(robot="UR10e")` means remove that robot from production.
- `set_production_target(item_type="fruits", count=6)` means sort six fruits, regardless of the lower-level SCARA sequence.

The agent does not send Webots commands directly. It does not call robot motors. It does not generate TCP control strings.

### 3. Coordinator Execution

The Webots coordinator is the trusted execution layer. It receives validated commands from the UI bridge and applies them to the simulation.

For example:

```text
Operator: Increase can production
Agent tool: set_operation_mode(mode="can_priority")
Bridge command: CONTROL MODE CAN_PRIORITY
Coordinator behavior: increase can conveyor speed and reduce fruit/SCARA priority
```

The coordinator knows the lower-level details:

- How to adjust conveyor speeds
- How to sequence UR arm phases
- How to send `CMD` messages to UR executors
- How to send `SCARA_*` messages to the SCARA controller
- How to count cans, apples, oranges, and fruits
- How to return to balanced mode after a target is reached

This keeps the agent high-level and the execution layer deterministic.

## Architecture

```text
React dashboard
  |
  | POST /agent
  v
frontend/server.mjs
  |
  | POST /plan
  v
agent_service/server.py
  |
  | Google ADK tool call
  v
agent_service/factory_agent.py
  |
  | validated tool action
  v
frontend/server.mjs
  |
  | CONTROL ... over TCP
  v
Webots coordinator
  |
  | CMD / SCARA_* / conveyor changes
  v
Robot controllers in Webots
```

Dashboard telemetry flows back in the other direction:

```text
Robot controllers / coordinator
  |
  | STATE / COUNT / LOG / CMD lines
  v
Node WebSocket bridge
  |
  v
React dashboard
```

## Key Components

| Path | Purpose |
| --- | --- |
| `agent_service/factory_agent.py` | Defines the agent instruction and tool functions. |
| `agent_service/server.py` | Exposes `POST /plan` for the ADK planner. |
| `frontend/server.mjs` | Bridges the dashboard to the coordinator and calls the agent service. |
| `frontend/src/App.tsx` | React dashboard, logs, and assistant panel. |
| `combined_world/controllers/coordinator/coordinator.c` | Webots supervisor and trusted workcell coordinator. |
| `combined_world/controllers/ur_arm_executor/ur_arm_executor.c` | UR robot executor that applies coordinator commands. |
| `combined_world/controllers/scara_food_industry/scara_food_industry.py` | SCARA controller that applies `SCARA_*` commands. |
| `combined_world/worlds/ure_plus_scara.wbt` | Combined Webots world. |
| `start_all.sh` | One-shot script for build, services, dashboard, and Webots. |

## Agent Behavior

The agent is expected to understand the operator's goal and choose the most appropriate tool.

Examples:

| Operator request | Expected tool |
| --- | --- |
| `Increase can production` | `set_operation_mode(mode="can_priority")` |
| `Prioritize fruit sorting` | `set_operation_mode(mode="fruit_priority")` |
| `Run balanced production` | `set_operation_mode(mode="balanced")` |
| `Run high capacity mode` | `set_operation_mode(mode="high_capacity")` |
| `Run low power mode` | `set_operation_mode(mode="low_power")` |
| `Handle 5 cans` | `set_production_target(item_type="cans", count=5)` |
| `Sort 6 fruits` | `set_production_target(item_type="fruits", count=6)` |
| `Disable UR10e` | `disable_robot(robot="UR10e")` |
| `Enable UR10e` | `enable_robot(robot="UR10e")` |
| `Stop the fruit line` | `stop_line(line="fruit_line")` |
| `Start the fruit line` | `start_line(line="fruit_line")` |
| `Give me a production report` | `get_workcell_status()` |

The agent currently requires Google ADK to work. If ADK, credentials, or the model call are unavailable, the app returns an error instead of falling back to deterministic keyword logic.

## Prerequisites

Install:

- Webots, preferably R2025a or compatible
- Node.js and npm
- Python 3
- Make / C compiler toolchain for Webots C controllers
- A Google API key or Vertex AI configuration for Google ADK

On macOS, the default Webots path expected by the script is:

```bash
/Applications/Webots.app
```

If Webots is installed somewhere else, set `WEBOTS_HOME`.

## Setup

From the repository root:

```bash
cd /path/to/20260513-hackathon
```

### 1. Set up the agent service

```bash
cd agent_service
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_API_KEY="your_api_key_here"
cd ..
```

You can also use Vertex AI instead of `GOOGLE_API_KEY` if your ADK environment is configured for it.

Optional model override:

```bash
export ADK_MODEL="gemini-flash-latest"
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 3. Configure Webots

If needed:

```bash
export WEBOTS_HOME="/Applications/Webots.app"
```

## Run Everything

From the repository root:

```bash
./start_all.sh
```

This script will:

1. Build the Webots C controllers.
2. Start the Node WebSocket/TCP bridge.
3. Start the ADK agent service.
4. Start the Vite React dashboard.
5. Open the dashboard at `http://127.0.0.1:5173/`.
6. Launch Webots with `combined_world/worlds/ure_plus_scara.wbt`.

## Testing the Demo

After Webots and the dashboard are running:

1. Open `http://127.0.0.1:5173/`.
2. Make sure the dashboard shows the coordinator as connected.
3. Open the assistant panel if it is collapsed.
4. Try one command at a time.

Recommended demo prompts:

```text
Run balanced production
```

```text
Increase can production
```

```text
Prioritize fruit sorting
```

```text
Handle 5 cans
```

```text
Sort 6 fruits
```

```text
Run low power mode
```

```text
Run high capacity mode
```

```text
Disable UR10e
```

```text
Enable UR10e
```

```text
Stop the fruit line
```

```text
Start the fruit line
```

```text
Give me a production report
```

For best demo reliability, use one intent per message. The agent is intentionally constrained to one tool call per operator request.

## Manual Run

If you do not want to use `start_all.sh`, run the pieces manually.

Build Webots controllers:

```bash
export WEBOTS_HOME="/Applications/Webots.app"
cd combined_world/controllers
make release WEBOTS_HOME="$WEBOTS_HOME"
cd ../..
```

Start the agent service:

```bash
cd agent_service
. .venv/bin/activate
export GOOGLE_API_KEY="your_api_key_here"
python server.py
```

Start the frontend bridge and dashboard in another terminal:

```bash
cd frontend
node server.mjs
```

In another terminal:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the Webots world:

```bash
open combined_world/worlds/ure_plus_scara.wbt
```

Or open it from Webots with **File -> Open World**.

## Ports

Defaults:

| Service | Default |
| --- | --- |
| Dashboard | `http://127.0.0.1:5173` |
| Browser WebSocket bridge | `ws://127.0.0.1:8765` |
| Agent HTTP endpoint | `http://127.0.0.1:8787/agent` |
| ADK planner endpoint | `http://127.0.0.1:8790/plan` |
| Webots coordinator TCP | `127.0.0.1:9099` |

Useful environment variables:

```bash
export COORDINATOR_TCP_PORT=9099
export FRONTEND_WS_PORT=8765
export AGENT_HTTP_PORT=8787
export ADK_AGENT_PORT=8790
export ADK_AGENT_URL="http://127.0.0.1:8790/plan"
export WEBOTS_HOME="/Applications/Webots.app"
```

Simulation pacing:

```bash
export SIM_SLOWDOWN=1
export UR_SPEED_MULT=1
export SCARA_SPEED_DIV=4
```

## Troubleshooting

### Agent error in the chat panel

The project requires ADK now. Check:

```bash
cd agent_service
. .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_API_KEY="your_api_key_here"
python server.py
```

Then retry the chat request.

### Dashboard cannot connect to coordinator

Make sure Webots is running the combined world and the coordinator controller has started. The coordinator listens on `127.0.0.1:9099` by default.

### Port already in use

Stop old `node`, `vite`, or Webots processes, or override the relevant port environment variables.

### Webots cannot find PROTOs

The world uses Webots `EXTERNPROTO` references. The first run may need network access so Webots can cache the referenced assets.

## Extending the Abstraction

To add a new robot or production cell, avoid exposing robot-specific details directly to the agent. Instead:

1. Add or update coordinator-level commands/state.
2. Add robot-specific execution logic inside the appropriate Webots controller.
3. Expose only a high-level tool if the operator needs a new kind of intent.
4. Describe that tool in terms of factory outcomes, not motor details.

The intended pattern is:

```text
operator goal -> agent tool -> coordinator command -> robot-specific controller
```

That keeps the operator experience consistent even as the underlying robot hardware changes.
