/**
 * Bridges browser WebSocket (dashboard) <-> coordinator TCP (REGISTER UI).
 * Env: COORDINATOR_TCP_PORT (default 9099), FRONTEND_WS_PORT (default 8765), AGENT_HTTP_PORT (default 8787),
 * ADK_AGENT_URL (default http://127.0.0.1:8790/plan), USE_ADK (default enabled unless set to 0).
 */
import http from "http";
import net from "net";
import { WebSocketServer } from "ws";

const TCP_PORT = parseInt(process.env.COORDINATOR_TCP_PORT || "9099", 10);
const WS_PORT = parseInt(process.env.FRONTEND_WS_PORT || "8765", 10);
const AGENT_PORT = parseInt(process.env.AGENT_HTTP_PORT || "8787", 10);
const ADK_AGENT_URL = process.env.ADK_AGENT_URL || "http://127.0.0.1:8790/plan";

const EXAMPLES = [
  "Run balanced production",
  "Prioritize fruit handling until 6 fruits are sorted",
  "Prioritize can handling",
  "Run low power mode",
  "Run high capacity mode",
  "Disable UR10e and continue production",
  "Start can line",
  "Stop fruit line",
  "Handle 5 cans then return to balanced mode",
  "Pause simulation",
  "Generate a production summary"
];

function normalize(text) {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}

function numberFrom(text, fallback = 0) {
  const m = text.match(/\b(\d+)\b/);
  return m ? parseInt(m[1], 10) : fallback;
}

function commandForTool(action) {
  const args = action.args || {};
  switch (action.tool) {
    case "pause_simulation":
      return "CONTROL PAUSE";
    case "resume_simulation":
      return "CONTROL RUN";
    case "fast_simulation":
      return "CONTROL FAST";
    case "set_operation_mode": {
      const mode = String(args.mode || "").toUpperCase();
      if (["BALANCED", "FRUIT_PRIORITY", "CAN_PRIORITY", "LOW_POWER", "HIGH_CAPACITY"].includes(mode))
        return `CONTROL MODE ${mode}`;
      return null;
    }
    case "enable_robot":
    case "disable_robot": {
      const robot = String(args.robot || "");
      if (!["UR3e", "UR5e", "UR10e", "ScaraT6"].includes(robot))
        return null;
      return `CONTROL ${action.tool === "enable_robot" ? "ENABLE" : "DISABLE"} ${robot}`;
    }
    case "start_line":
    case "stop_line": {
      const line = String(args.line || "");
      if (line === "can_line")
        return `CONTROL LINE CAN ${action.tool === "start_line" ? "START" : "STOP"}`;
      if (line === "fruit_line")
        return `CONTROL LINE FRUIT ${action.tool === "start_line" ? "START" : "STOP"}`;
      return null;
    }
    case "set_production_target": {
      const itemType = String(args.item_type || "").toUpperCase();
      const count = Number(args.count || 0);
      if (!["CANS", "FRUITS", "APPLES", "ORANGES"].includes(itemType) || count <= 0)
        return null;
      return `CONTROL TARGET ${itemType} ${Math.floor(count)}`;
    }
    case "clear_production_target":
      return "CONTROL TARGET CLEAR";
    case "get_workcell_status":
      return "CONTROL STATUS";
    default:
      return null;
  }
}

function makeAction(tool, args = {}) {
  return { tool, args };
}

function localPlan(message) {
  const text = normalize(message);
  const actions = [];
  let reply = "I mapped the request to validated workcell controls.";

  if (text.includes("summary") || text.includes("report")) {
    return {
      reply: "I requested the latest workcell status so the dashboard can summarize mode, counts, targets, and robot availability.",
      actions: [makeAction("get_workcell_status")]
    };
  }
  if (text.includes("pause") || text.includes("stop simulation")) {
    return { reply: "Pausing the Webots simulation.", actions: [makeAction("pause_simulation")] };
  }
  if (text.includes("resume") || text.includes("run simulation") || text === "run") {
    return { reply: "Resuming the Webots simulation.", actions: [makeAction("resume_simulation")] };
  }
  if (text.includes("fast")) {
    actions.push(makeAction("fast_simulation"));
  }

  if (text.includes("disable") || text.includes("down") || text.includes("maintenance")) {
    for (const robot of ["UR3e", "UR5e", "UR10e", "ScaraT6"]) {
      if (text.includes(robot.toLowerCase())) actions.push(makeAction("disable_robot", { robot }));
    }
  }
  if (text.includes("enable") || text.includes("re enable") || text.includes("reenable")) {
    for (const robot of ["UR3e", "UR5e", "UR10e", "ScaraT6"]) {
      if (text.includes(robot.toLowerCase())) actions.push(makeAction("enable_robot", { robot }));
    }
  }

  if (text.includes("start can") || text.includes("can conveyor") && text.includes("start"))
    actions.push(makeAction("start_line", { line: "can_line" }));
  if (text.includes("stop can") || text.includes("can conveyor") && text.includes("stop"))
    actions.push(makeAction("stop_line", { line: "can_line" }));
  if (text.includes("start fruit") || text.includes("fruit conveyor") && text.includes("start"))
    actions.push(makeAction("start_line", { line: "fruit_line" }));
  if (text.includes("stop fruit") || text.includes("fruit conveyor") && text.includes("stop"))
    actions.push(makeAction("stop_line", { line: "fruit_line" }));

  if (text.includes("balanced")) {
    actions.push(makeAction("set_operation_mode", { mode: "balanced" }));
    reply = "Running balanced production across the can and fruit workcells.";
  } else if (text.includes("fruit") && (text.includes("prioritize") || text.includes("priority"))) {
    actions.push(makeAction("set_operation_mode", { mode: "fruit_priority" }));
    actions.push(makeAction("start_line", { line: "fruit_line" }));
    reply = "Prioritizing fruit handling by increasing SCARA cadence while keeping the workcell coordinated.";
  } else if ((text.includes("can") || text.includes("cans")) && (text.includes("prioritize") || text.includes("priority"))) {
    actions.push(makeAction("set_operation_mode", { mode: "can_priority" }));
    actions.push(makeAction("start_line", { line: "can_line" }));
    reply = "Prioritizing can handling while leaving the fruit side available at reduced priority.";
  } else if (text.includes("low power") || text.includes("energy")) {
    actions.push(makeAction("set_operation_mode", { mode: "low_power" }));
    reply = "Switching to low power mode by reducing workcell cadence and taking UR10e out of active production.";
  } else if (text.includes("high capacity") || text.includes("max capacity") || text.includes("throughput")) {
    actions.push(makeAction("set_operation_mode", { mode: "high_capacity" }));
    reply = "Switching to high capacity mode with all robots enabled and faster SCARA cadence.";
  }

  const count = numberFrom(text, 0);
  if (count > 0) {
    if (text.includes("apple"))
      actions.push(makeAction("set_production_target", { item_type: "apples", count }));
    else if (text.includes("orange"))
      actions.push(makeAction("set_production_target", { item_type: "oranges", count }));
    else if (text.includes("fruit"))
      actions.push(makeAction("set_production_target", { item_type: "fruits", count }));
    else if (text.includes("can"))
      actions.push(makeAction("set_production_target", { item_type: "cans", count }));
  }

  if (actions.length === 0) {
    actions.push(makeAction("get_workcell_status"));
    reply = "I could not find a direct production command, so I requested current workcell status. Try one of the example prompts.";
  }

  return { reply, actions };
}

async function geminiPlan(message) {
  const key = process.env.GEMINI_API_KEY;
  if (!key || process.env.USE_GEMINI !== "1")
    return null;
  const model = process.env.GEMINI_MODEL || "gemini-1.5-flash";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`;
  const tools = [
    "pause_simulation", "resume_simulation", "fast_simulation", "set_operation_mode",
    "enable_robot", "disable_robot", "start_line", "stop_line", "set_production_target",
    "clear_production_target", "get_workcell_status"
  ];
  const prompt = `You are FactoryFlow Copilot. Convert the operator request into JSON only.
Allowed tools: ${tools.join(", ")}.
Modes: balanced, fruit_priority, can_priority, low_power, high_capacity.
Robots: UR3e, UR5e, UR10e, ScaraT6. Lines: can_line, fruit_line.
Target item_type: cans, fruits, apples, oranges.
Schema: {"reply":"short operator-facing explanation","actions":[{"tool":"name","args":{}}]}
Request: ${message}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
  });
  if (!res.ok)
    throw new Error(`Gemini HTTP ${res.status}`);
  const data = await res.json();
  const text = data?.candidates?.[0]?.content?.parts?.map((p) => p.text || "").join("") || "";
  const jsonText = text.replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/```$/i, "").trim();
  const parsed = JSON.parse(jsonText);
  if (!parsed || !Array.isArray(parsed.actions))
    throw new Error("Gemini returned invalid plan");
  return parsed;
}

async function adkPlan(message, context) {
  if (process.env.USE_ADK === "0")
    throw new Error("ADK planner is disabled by USE_ADK=0");
  const requestId = `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    console.log(`agent[${requestId}]: prompt=${JSON.stringify(message)}`);
    console.log(`agent[${requestId}]: calling ADK ${ADK_AGENT_URL}`);
    const res = await fetch(ADK_AGENT_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ request_id: requestId, message, context: context || {} }),
      signal: controller.signal
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => "");
      console.log(`agent[${requestId}]: ADK error status=${res.status} body=${errorText}`);
      throw new Error(`ADK HTTP ${res.status}: ${errorText || "empty response body"}`);
    }
    const data = await res.json();
    if (!data || !Array.isArray(data.actions))
      throw new Error("ADK returned invalid plan");
    if (data.planner === "deterministic-fallback")
      console.log(`agent[${requestId}]: ADK service used deterministic fallback=${JSON.stringify(data)}`);
    else
      console.log(`agent[${requestId}]: ADK response=${JSON.stringify(data)}`);
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function sendCoordinatorCommands(commands) {
  return new Promise((resolve) => {
    if (commands.length === 0) {
      resolve({ ok: true, sent: [] });
      return;
    }
    const sock = net.createConnection(TCP_PORT, "127.0.0.1");
    const sent = [];
    let done = false;
    const finish = (ok, error = "") => {
      if (done) return;
      done = true;
      sock.destroy();
      resolve({ ok, sent, error });
    };
    sock.setTimeout(1200);
    sock.once("connect", () => {
      sock.write("REGISTER UI\n");
      for (const cmd of commands) {
        sock.write(`${cmd}\n`);
        sent.push(cmd);
      }
      setTimeout(() => finish(true), 150);
    });
    sock.on("timeout", () => finish(false, "coordinator connection timed out"));
    sock.on("error", (err) => finish(false, err.message));
  });
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        req.destroy();
        reject(new Error("request too large"));
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

function writeJson(res, status, payload) {
  res.writeHead(status, {
    "content-type": "application/json",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type"
  });
  res.end(JSON.stringify(payload));
}

const wss = new WebSocketServer({ port: WS_PORT, host: "127.0.0.1" });

wss.on("connection", (ws) => {
  let sock = null;
  let retryTimer = null;

  const clearRetry = () => {
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const scheduleRetry = () => {
    clearRetry();
    if (ws.readyState === 1) retryTimer = setTimeout(tryTcp, 400);
  };

  const tryTcp = () => {
    if (sock || ws.readyState !== 1) return;
    const s = net.createConnection(TCP_PORT, "127.0.0.1");
    s.setEncoding("utf8");
    s.once("connect", () => {
      sock = s;
      clearRetry();
      s.write("REGISTER UI\n");
      s.on("data", (chunk) => {
        if (ws.readyState === 1) ws.send(chunk);
      });
      s.on("close", () => {
        sock = null;
        if (ws.readyState === 1) ws.send("__TCP_CLOSED__\n");
        scheduleRetry();
      });
    });
    s.on("error", () => {
      s.destroy();
      scheduleRetry();
    });
  };

  tryTcp();

  ws.on("message", (data) => {
    const text = typeof data === "string" ? data : data.toString();
    if (sock && !sock.destroyed) {
      sock.write(text.endsWith("\n") ? text : `${text}\n`);
    }
  });

  ws.on("close", () => {
    clearRetry();
    if (sock) sock.destroy();
    sock = null;
  });
});

console.log(`bridge ws://127.0.0.1:${WS_PORT}  ->  tcp 127.0.0.1:${TCP_PORT}`);

const agentServer = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    writeJson(res, 204, {});
    return;
  }
  if (req.method === "GET" && req.url === "/examples") {
    writeJson(res, 200, { examples: EXAMPLES });
    return;
  }
  if (req.method !== "POST" || req.url !== "/agent") {
    writeJson(res, 404, { error: "not found" });
    return;
  }
  try {
    const body = await readJson(req);
    const message = String(body.message || "").trim();
    if (!message) {
      writeJson(res, 400, { error: "message is required" });
      return;
    }
    console.log(`agent: received UI prompt=${JSON.stringify(message)}`);
    const plan = await adkPlan(message, body.context || {});
    const planner = plan.planner || "adk";
    const commands = plan.actions.map(commandForTool).filter(Boolean);
    console.log(`agent: planner=${planner} actions=${JSON.stringify(plan.actions)} commands=${JSON.stringify(commands)}`);
    const execution = await sendCoordinatorCommands(commands);
    console.log(`agent: coordinator execution=${JSON.stringify(execution)}`);
    const reply = execution.ok ? plan.reply : `${plan.reply} Coordinator is not connected yet, so the plan is staged in the UI but was not applied.`;
    writeJson(res, 200, { planner, reply, actions: plan.actions, commands, execution });
  } catch (err) {
    console.log(`agent: planning error=${err.message}`);
    writeJson(res, 502, { error: `Agent planning failed: ${err.message}` });
  }
});

agentServer.listen(AGENT_PORT, "127.0.0.1", () => {
  console.log(`agent http://127.0.0.1:${AGENT_PORT}/agent`);
});
