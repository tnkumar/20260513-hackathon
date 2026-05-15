import asyncio
import contextvars
import json
import os
import re
import uuid


ACTIONS = contextvars.ContextVar("factoryflow_actions", default=None)

TOOLS = {
    "pause_simulation",
    "resume_simulation",
    "fast_simulation",
    "set_operation_mode",
    "enable_robot",
    "disable_robot",
    "start_line",
    "stop_line",
    "set_production_target",
    "clear_production_target",
    "get_workcell_status",
}

MODES = {"balanced", "fruit_priority", "can_priority", "low_power", "high_capacity"}
ROBOTS = {"UR3e", "UR5e", "UR10e", "ScaraT6"}
LINES = {"can_line", "fruit_line"}
ITEM_TYPES = {"cans", "fruits", "apples", "oranges"}


def _record(tool, args=None):
    args = args or {}
    action = {"tool": tool, "args": args}
    actions = ACTIONS.get()
    if actions is not None:
        actions.append(action)
    return {"status": "planned", "action": action}


def set_operation_mode(mode: str) -> dict:
    """Choose the overall production strategy for the workcell.

    Use this when the operator wants to change how production is optimized,
    balanced, accelerated, prioritized, or made more efficient.

    mode meanings:
    - balanced: normal steady operation for both can and fruit lines.
    - can_priority: optimize the cell toward can output and UR can handling.
    - fruit_priority: optimize the cell toward fruit/apple/orange sorting and ScaraT6 work.
    - low_power: reduce energy use and run a lighter production strategy.
    - high_capacity: maximize total throughput across the whole workcell.

    If the user asks to increase, improve, boost, speed up, prioritize, or produce
    more of a category without giving a specific numeric count, this is usually
    the correct tool. Choose can_priority for can-related production goals and
    fruit_priority for fruit/apple/orange-related production goals.
    """
    mode = str(mode).lower()
    if mode not in MODES:
        return {"status": "error", "error": f"invalid mode: {mode}"}
    return _record("set_operation_mode", {"mode": mode})


def enable_robot(robot: str) -> dict:
    """Return one robot to service so it can participate in production.

    Use this for requests to bring a named robot online, restore it, enable it,
    re-enable it, make it available, or put it back into production.
    Valid robots: UR3e, UR5e, UR10e, ScaraT6.
    """
    if robot not in ROBOTS:
        return {"status": "error", "error": f"invalid robot: {robot}"}
    return _record("enable_robot", {"robot": robot})


def disable_robot(robot: str) -> dict:
    """Remove one robot from active production.

    Use this for requests to take a named robot offline, disable it, stop using
    it, put it in maintenance, isolate it, or remove it from the workcell flow.
    Valid robots: UR3e, UR5e, UR10e, ScaraT6.
    """
    if robot not in ROBOTS:
        return {"status": "error", "error": f"invalid robot: {robot}"}
    return _record("disable_robot", {"robot": robot})


def start_line(line: str) -> dict:
    """Start or resume one physical conveyor line.

    Use this when the operator wants material to flow again on a specific line,
    independent of changing the overall production strategy.
    Valid lines: can_line, fruit_line.
    """
    line = str(line).lower()
    if line not in LINES:
        return {"status": "error", "error": f"invalid line: {line}"}
    return _record("start_line", {"line": line})


def stop_line(line: str) -> dict:
    """Stop one physical conveyor line.

    Use this when the operator wants to halt, hold, shut down, or stop material
    flow on a specific line, independent of changing the overall production
    strategy. Valid lines: can_line, fruit_line.
    """
    line = str(line).lower()
    if line not in LINES:
        return {"status": "error", "error": f"invalid line: {line}"}
    return _record("stop_line", {"line": line})


def set_production_target(item_type: str, count: int) -> dict:
    """Set a concrete quantity goal for production.

    Use this when the operator gives a numeric count to produce, handle, sort,
    process, complete, or reach for an item type.
    Valid item_type values: cans, fruits, apples, oranges.
    """
    item_type = str(item_type).lower()
    count = int(count)
    if item_type not in ITEM_TYPES:
        return {"status": "error", "error": f"invalid item_type: {item_type}"}
    if count <= 0:
        return {"status": "error", "error": "count must be positive"}
    return _record("set_production_target", {"item_type": item_type, "count": count})


def clear_production_target() -> dict:
    """Cancel the active quantity goal.

    Use this when the operator wants to clear, cancel, remove, reset, or stop
    pursuing the current production target.
    """
    return _record("clear_production_target")


def get_workcell_status() -> dict:
    """Read the current workcell state without changing production.

    Use this for reports, summaries, diagnostics, counts, current mode, robot
    availability, line state, target status, or questions where the operator is
    asking what is happening rather than asking you to change what happens.
    Do not use this for an actionable production-change request.
    """
    return _record("get_workcell_status")


def pause_simulation() -> dict:
    """Pause the Webots simulation clock.

    Use this when the operator wants the simulation itself to freeze, pause, or
    temporarily stop advancing.
    """
    return _record("pause_simulation")


def resume_simulation() -> dict:
    """Resume the Webots simulation in real-time mode.

    Use this when the operator wants the simulation clock to continue running
    normally after being paused or stopped.
    """
    return _record("resume_simulation")


def fast_simulation() -> dict:
    """Run the Webots simulation clock as fast as possible.

    Use this when the operator is asking to accelerate simulation time itself,
    not when they are asking to increase production throughput. For throughput,
    use set_operation_mode.
    """
    return _record("fast_simulation")


INSTRUCTION = """
You are FactoryFlow Copilot, the assistant used by a factory manager to operate a simulated robotic workcell in Webots.
Think of yourself as a calm floor coordinator: the operator gives you a plain-English production request, and your job is to translate that request into exactly one safe, valid workcell tool call.

Application context:
- The workcell has two production areas.
- The can-handling area uses three Universal Robots arms: UR3e, UR5e, and UR10e.
- The fruit-sorting area uses one ScaraT6 robot.
- The can line and fruit line each have a conveyor that can be started, stopped, or run at different speeds through operation modes.
- The dashboard already knows the current state, and the user may ask you to change that state, check that state, or explain what is happening.
- You are not allowed to directly control Webots, motors, TCP messages, or raw coordinator commands. You only express intent by calling one of the provided tools.

Core rule:
- Call exactly one tool for each operator message.
- Do not invent tool names.
- Do not output raw commands such as CONTROL MODE, CMD, SCARA_HOME, or TCP messages.
- After the tool call, reply with one short sentence that tells the operator what you planned.

Available intent categories:

Decision procedure:
- First decide whether the operator is asking you to change production or asking for information.
- If the message asks to change output, throughput, priority, efficiency, power usage, or overall behavior, choose a production-control tool. Do not call get_workcell_status for an actionable change request.
- If the message includes a numeric quantity goal, choose set_production_target.
- If the message names a specific robot and asks to make it available or unavailable, choose enable_robot or disable_robot.
- If the message names a specific line/conveyor and asks to start or stop material flow, choose start_line or stop_line.
- If the message is about the Webots simulation clock itself, choose pause_simulation, resume_simulation, or fast_simulation.
- If the message asks what is happening, asks for counts, asks for a report, asks whether something is running, or asks for diagnosis without requesting a change, choose get_workcell_status.
- When wording is informal, infer the operational goal from the object and desired direction. For example, an operator asking for more of an item type is asking to prioritize that item type, not asking for status.

1. Simulation control
- If the operator wants to pause, freeze, hold, or temporarily stop the simulation itself, call pause_simulation.
- If the operator wants the simulation to run, resume, continue, or return to normal real-time execution, call resume_simulation.
- If the operator wants to speed through time, run quickly, or use fast simulation mode, call fast_simulation.

2. Operation modes
- Use set_operation_mode when the operator asks for an overall production strategy.
- balanced: use when the operator wants normal production, steady production, equal priority, or both lines running normally.
- fruit_priority: use when the operator wants fruit, apples, oranges, sorting, or ScaraT6 work prioritized.
- can_priority: use when the operator wants cans, can handling, can throughput, or UR can-picking prioritized.
- low_power: use when the operator wants energy saving, reduced power, slower production, or lighter robot usage.
- high_capacity: use when the operator wants maximum throughput, peak output, fastest production, or all robots working aggressively.
- If the operator wants more output for an item category but does not provide a numeric count, use the priority mode for that category.
- Use can_priority for goals centered on cans or UR can handling.
- Use fruit_priority for goals centered on fruits, apples, oranges, ScaraT6, or sorting.
- Use high_capacity only when the operator wants maximum total output across the entire workcell, not just one product category.

Mode behavior the operator expects:
- balanced starts both can and fruit lines at normal speed.
- fruit_priority starts both lines, increases ScaraT6 cadence, increases fruit conveyor speed, and reduces can conveyor speed to half.
- can_priority starts both lines, increases can conveyor speed, and reduces fruit/ScaraT6 priority.
- low_power starts both lines, disables UR10e, slows ScaraT6, and reduces can conveyor speed to half.
- high_capacity starts both lines, enables all robots, increases can conveyor speed, increases fruit conveyor speed, and uses the fastest ScaraT6 cadence.

3. Robot availability
- Use enable_robot when the operator wants a robot brought back online, restored, enabled, re-enabled, or returned to production.
- Use disable_robot when the operator wants a robot removed from service, taken offline, disabled, put into maintenance, or stopped from participating.
- Valid robots are UR3e, UR5e, UR10e, and ScaraT6.
- If the message names one robot and asks for availability changes, choose the enable/disable robot tool.
- If the message asks for an overall energy-saving strategy rather than just one robot, use low_power mode instead of disabling an individual robot.

4. Line control
- Use start_line when the operator asks to start, restart, open, resume, or feed a specific line.
- Use stop_line when the operator asks to stop, close, halt, hold, or shut down a specific line.
- Valid lines are can_line and fruit_line.
- Stopping a line physically stops that line's conveyor.
- Starting a line physically starts that line's conveyor at the current mode speed.

5. Production targets
- Use set_production_target when the operator gives a quantity goal, such as "handle 5 cans" or "sort 8 fruits".
- Valid item types are cans, fruits, apples, and oranges.
- A cans target behaves like can priority.
- A fruits, apples, or oranges target behaves like fruit priority.
- The coordinator will return to balanced mode after the target is reached.
- If the operator gives both a target and a priority, prefer set_production_target because the target already implies the correct priority.
- Use clear_production_target when the operator wants to cancel, clear, remove, or reset the current production target.

6. Status, questions, and unclear requests
- Use get_workcell_status when the operator asks for a summary, report, status, current state, counts, what changed, what is running, which robots are active, or whether a target has been reached.
- If the operator asks a question that cannot be answered by changing production, inspect the workcell state with get_workcell_status.
- If the operator uses vague language but the operational goal is still recognizable, choose the closest safe tool instead of using status.
- If the operator gives conflicting instructions in one message, choose the part that is most concrete and operational. For example, "stop fruit line and prioritize fruit" contains a direct physical line command, so call stop_line for fruit_line.
- If the operator asks for multiple operational changes at once, choose the single tool that best represents the main goal. For example, "enable everyone and run flat out" means high_capacity.
- If there is no clear production action, treat the message as a request to understand the workcell before acting, and use get_workcell_status.

Examples:

Operator intent: normalize the overall workcell.
Operator: "Run normal production."
Tool: set_operation_mode with mode="balanced"
Response: "I planned balanced production across both lines."

Operator intent: improve output for one product category without a numeric target.
Operator: "We need to get through cans faster."
Tool: set_operation_mode with mode="can_priority"
Response: "I planned can-priority production."

Operator intent: improve sorting throughput for the fruit side without a numeric target.
Operator: "The fruit side is falling behind."
Tool: set_operation_mode with mode="fruit_priority"
Response: "I planned fruit-priority production."

Operator intent: reach a concrete count.
Operator: "Prioritize apples until we have 6."
Tool: set_production_target with item_type="apples" and count=6
Response: "I planned an apples target of 6."

Operator intent: remove a specific robot from production.
Operator: "Take UR10e offline for maintenance."
Tool: disable_robot with robot="UR10e"
Response: "I planned to disable UR10e."

Operator intent: restore a specific robot to production.
Operator: "Bring the SCARA back online."
Tool: enable_robot with robot="ScaraT6"
Response: "I planned to enable ScaraT6."

Operator intent: stop physical material flow on one line.
Operator: "Stop feeding fruit for now."
Tool: stop_line with line="fruit_line"
Response: "I planned to stop the fruit line."

Operator intent: resume physical material flow on one line.
Operator: "Start the cans again."
Tool: start_line with line="can_line"
Response: "I planned to start the can line."

Operator intent: ask for information, not a production change.
Operator: "Give me a production report."
Tool: get_workcell_status
Response: "I requested the latest workcell status."

Operator intent: remove an active quantity goal.
Operator: "Cancel the current goal."
Tool: clear_production_target
Response: "I planned to clear the production target."

Operator intent: maximize total workcell output, not one category.
Operator: "Run everything as fast as possible."
Tool: set_operation_mode with mode="high_capacity"
Response: "I planned high-capacity production."

Operator intent: reduce energy use while continuing production.
Operator: "Save energy but keep production moving."
Tool: set_operation_mode with mode="low_power"
Response: "I planned low-power production."
"""


def _load_adk():
    try:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai.types import Content, Part
    except Exception as exc:
        return None, exc
    return (LlmAgent, Runner, InMemorySessionService, Content, Part), None


def _make_content(Content, Part, text):
    try:
        return Content(role="user", parts=[Part(text=text)])
    except Exception:
        return Content(role="user", parts=[Part.from_text(text=text)])


def _event_text(event):
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    chunks = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    if chunks:
        return "".join(chunks)
    try:
        return event.stringify_content()
    except Exception:
        return ""


async def _run_adk_async(message, context):
    loaded, error = _load_adk()
    if error:
        raise RuntimeError(f"google-adk unavailable: {error}")
    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
        raise RuntimeError("GOOGLE_API_KEY or Vertex AI env is required for ADK model calls")

    LlmAgent, Runner, InMemorySessionService, Content, Part = loaded
    model = os.environ.get("ADK_MODEL", "gemini-flash-latest")
    agent = LlmAgent(
        model=model,
        name="factoryflow_copilot",
        instruction=INSTRUCTION,
        tools=[
            pause_simulation,
            resume_simulation,
            fast_simulation,
            set_operation_mode,
            enable_robot,
            disable_robot,
            start_line,
            stop_line,
            set_production_target,
            clear_production_target,
            get_workcell_status,
        ],
    )
    session_service = InMemorySessionService()
    app_name = "factoryflow"
    user_id = "dashboard"
    session_id = f"turn-{uuid.uuid4().hex}"
    if hasattr(session_service, "create_session"):
        maybe = session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state={})
        if hasattr(maybe, "__await__"):
            await maybe

    prompt = f"Operator request: {message}\n\nCurrent dashboard context JSON: {json.dumps(context or {}, sort_keys=True)}"
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    content = _make_content(Content, Part, prompt)
    reply = ""
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        text = _event_text(event).strip()
        if text:
            reply = text
    return reply


def _normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def _number_from(text):
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else 0


def _fallback_plan(message):
    text = _normalize(message)
    actions = []
    reply = "I mapped the request through the ADK service fallback planner."

    def add(tool, args=None):
        actions.append({"tool": tool, "args": args or {}})

    if "summary" in text or "status" in text or "report" in text:
        add("get_workcell_status")
        return {"planner": "adk-fallback", "reply": "I requested the current workcell status.", "actions": actions}
    if "pause" in text or "stop simulation" in text:
        add("pause_simulation")
        return {"planner": "adk-fallback", "reply": "Pausing the Webots simulation.", "actions": actions}
    if "resume" in text or "run simulation" in text or text == "run":
        add("resume_simulation")
        return {"planner": "adk-fallback", "reply": "Resuming the Webots simulation.", "actions": actions}
    if "fast" in text:
        add("fast_simulation")

    for robot in ["UR3e", "UR5e", "UR10e", "ScaraT6"]:
        token = robot.lower()
        if token in text and ("disable" in text or "down" in text or "maintenance" in text):
            add("disable_robot", {"robot": robot})
        if token in text and ("enable" in text or "re enable" in text or "reenable" in text):
            add("enable_robot", {"robot": robot})

    if ("start can" in text) or ("can conveyor" in text and "start" in text):
        add("start_line", {"line": "can_line"})
    if ("stop can" in text) or ("can conveyor" in text and "stop" in text):
        add("stop_line", {"line": "can_line"})
    if ("start fruit" in text) or ("fruit conveyor" in text and "start" in text):
        add("start_line", {"line": "fruit_line"})
    if ("stop fruit" in text) or ("fruit conveyor" in text and "stop" in text):
        add("stop_line", {"line": "fruit_line"})

    if "balanced" in text:
        add("set_operation_mode", {"mode": "balanced"})
        reply = "Running balanced production."
    elif "fruit" in text and ("prioritize" in text or "priority" in text):
        add("set_operation_mode", {"mode": "fruit_priority"})
        reply = "Prioritizing fruit handling."
    elif ("can" in text or "cans" in text) and ("prioritize" in text or "priority" in text):
        add("set_operation_mode", {"mode": "can_priority"})
        reply = "Prioritizing can handling."
    elif "low power" in text or "energy" in text:
        add("set_operation_mode", {"mode": "low_power"})
        reply = "Switching to low power mode."
    elif "high capacity" in text or "max capacity" in text or "throughput" in text:
        add("set_operation_mode", {"mode": "high_capacity"})
        reply = "Switching to high capacity mode."

    count = _number_from(text)
    if count > 0:
        if "apple" in text:
            add("set_production_target", {"item_type": "apples", "count": count})
        elif "orange" in text:
            add("set_production_target", {"item_type": "oranges", "count": count})
        elif "fruit" in text:
            add("set_production_target", {"item_type": "fruits", "count": count})
        elif "can" in text:
            add("set_production_target", {"item_type": "cans", "count": count})

    if not actions:
        add("get_workcell_status")
        reply = "I requested status because the request did not map to a direct workcell command."
    return {"planner": "adk-fallback", "reply": reply, "actions": actions}


def plan(message, context=None):
    actions = []
    token = ACTIONS.set(actions)
    try:
        reply = asyncio.run(_run_adk_async(message, context or {}))
        if not actions:
            raise RuntimeError("ADK did not call a workcell tool")
        return {"planner": "adk", "reply": reply or "I planned validated workcell controls.", "actions": actions}
    finally:
        ACTIONS.reset(token)
