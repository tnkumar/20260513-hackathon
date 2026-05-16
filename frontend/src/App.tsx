import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://127.0.0.1:8765";
const AGENT_URL = import.meta.env.VITE_AGENT_URL ?? "http://127.0.0.1:8787";

type Lines = string[];
type Robots = "UR3e" | "UR5e" | "UR10e" | "ScaraT6";
type View = "dashboard" | "logs";

type Workcell = {
  mode: string;
  lines: Record<"can" | "fruit", string>;
  robots: Record<Robots, string>;
  counts: Record<"cans" | "apples" | "oranges" | "fruits", number>;
  armCans: Record<"UR3e" | "UR5e" | "UR10e", number>;
  target: { type: string; count: number };
};

type AgentEntry = {
  role: "operator" | "agent";
  text: string;
  commands?: string[];
  planner?: string;
};

const MAX = 400;
const ROBOTS: Robots[] = ["UR3e", "UR5e", "UR10e", "ScaraT6"];

const DEFAULT_WORKCELL: Workcell = {
  mode: "balanced",
  lines: { can: "running", fruit: "running" },
  robots: { UR3e: "enabled", UR5e: "enabled", UR10e: "enabled", ScaraT6: "enabled" },
  counts: { cans: 0, apples: 0, oranges: 0, fruits: 0 },
  armCans: { UR3e: 0, UR5e: 0, UR10e: 0 },
  target: { type: "none", count: 0 },
};

function push(lines: Lines, line: string): Lines {
  const next = [...lines, line];
  return next.length > MAX ? next.slice(-MAX) : next;
}

function titleCaseMode(mode: string) {
  return mode
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function classify(line: string): string {
  if (line.startsWith("CMD|")) return "line-cmd";
  if (line.startsWith("LOG|")) return "line-log";
  if (line.startsWith("STATE|")) return "line-state";
  if (line.startsWith("COUNT|")) return "line-count";
  return "line-recv";
}

function lineLabel(line: string) {
  if (line.startsWith("CMD|")) return "Command";
  if (line.startsWith("STATE|")) return "State";
  if (line.startsWith("COUNT|")) return "Count";
  if (line.startsWith("LOG|")) return "Log";
  return "Event";
}

function commandChanges(command: string): string[] {
  const parts = command.trim().split(/\s+/);

  if (command === "CONTROL MODE BALANCED") {
    return [
      "All robots returned to standard production cadence.",
      "Can conveyor running at 1.0x speed.",
      "Fruit conveyor running at 1.0x speed.",
      "Estimated power consumption: 62%.",
    ];
  }
  if (command === "CONTROL MODE CAN_PRIORITY") {
    return [
      "Can handling moved to priority production.",
      "Can conveyor increased to 6.0x speed.",
      "Fruit conveyor reduced to 0.5x speed.",
      "ScaraT6 cadence reduced while UR arms focus on cans.",
      "Estimated power consumption: 78%.",
    ];
  }
  if (command === "CONTROL MODE FRUIT_PRIORITY") {
    return [
      "Fruit sorting moved to priority production.",
      "ScaraT6 cadence increased for faster pick-and-place cycles.",
      "UR10e removed from can handling and moved to a safe stow position.",
      "Fruit conveyor increased to 3.0x speed.",
      "Can conveyor reduced to 0.5x speed.",
      "Estimated power consumption: 72%.",
    ];
  }
  if (command === "CONTROL MODE LOW_POWER") {
    return [
      "Low power production mode enabled.",
      "UR10e removed from active production.",
      "Can conveyor reduced to 0.5x speed.",
      "ScaraT6 cadence reduced to conserve energy.",
      "Estimated power consumption: 45%.",
    ];
  }
  if (command === "CONTROL MODE HIGH_CAPACITY") {
    return [
      "High capacity production mode enabled.",
      "All robots assigned to active production.",
      "Can conveyor increased to 6.0x speed.",
      "Fruit conveyor increased to 2.0x speed.",
      "ScaraT6 running at fastest demo cadence.",
      "Estimated power consumption: 95%.",
    ];
  }
  if (parts[0] === "CONTROL" && parts[1] === "TARGET" && parts[2] === "CANS") {
    return [
      `Production target set to ${parts[3]} cans.`,
      "Can handling moved to priority production until the target is reached.",
      "Can conveyor increased to 6.0x speed.",
      "Estimated power consumption: 78%.",
    ];
  }
  if (parts[0] === "CONTROL" && parts[1] === "TARGET" && ["FRUITS", "APPLES", "ORANGES"].includes(parts[2] ?? "")) {
    return [
      `Production target set to ${parts[3]} ${parts[2].toLowerCase()}.`,
      "Fruit sorting moved to priority production until the target is reached.",
      "ScaraT6 cadence increased for faster sorting.",
      "UR10e removed from can handling and moved to a safe stow position.",
      "Fruit conveyor increased to 3.0x speed.",
      "Estimated power consumption: 72%.",
    ];
  }
  if (command === "CONTROL TARGET CLEAR") {
    return ["Production target cleared.", "Workcell is ready for the next production goal."];
  }
  if (parts[0] === "CONTROL" && parts[1] === "DISABLE" && parts[2]) {
    return [`${parts[2]} removed from active production.`, "Remaining enabled robots continue under the current workcell mode."];
  }
  if (parts[0] === "CONTROL" && parts[1] === "ENABLE" && parts[2]) {
    return [`${parts[2]} returned to active production.`, "Robot availability updated on the dashboard."];
  }
  if (parts[0] === "CONTROL" && parts[1] === "LINE" && parts[2] && parts[3] === "STOP") {
    return [`${titleCaseMode(parts[2].toLowerCase())} line stopped.`, "Conveyor speed set to 0.0x for that line."];
  }
  if (parts[0] === "CONTROL" && parts[1] === "LINE" && parts[2] && parts[3] === "START") {
    return [`${titleCaseMode(parts[2].toLowerCase())} line started.`, "Conveyor resumed at the current mode speed."];
  }
  if (command === "CONTROL PAUSE") {
    return ["Simulation paused.", "Robots and conveyors are holding their current state."];
  }
  if (command === "CONTROL RUN") {
    return ["Simulation resumed in real-time mode.", "Workcell execution continues from the current state."];
  }
  if (command === "CONTROL FAST") {
    return ["Simulation switched to fast mode.", "Webots will advance the workcell faster than real time."];
  }
  if (command === "CONTROL STATUS") {
    return ["Dashboard status refreshed.", "Latest mode, robot, line, count, and target state requested."];
  }
  return ["Workcell command applied successfully."];
}

function appliedChanges(commands?: string[]) {
  return (commands ?? []).flatMap(commandChanges);
}

function friendlyAgentError(error: Error) {
  const message = error.message.toLowerCase();
  if (message.includes("503") || message.includes("unavailable") || message.includes("high demand")) {
    return "The AI planner is temporarily busy. Please wait a moment and try the same request again.";
  }
  if (message.includes("api key") || message.includes("credential") || message.includes("permission") || message.includes("unauthorized")) {
    return "The AI planner is not configured correctly. Please check the API key and restart the service.";
  }
  if (message.includes("timeout") || message.includes("abort")) {
    return "The AI planner took too long to respond. Please try again.";
  }
  if (message.includes("coordinator")) {
    return "The workcell coordinator is not connected. Please restart the simulation and try again.";
  }
  return "I could not plan that request right now. Please try again in a moment.";
}

function routeLine(
  line: string,
  setUr3: Dispatch<SetStateAction<Lines>>,
  setUr5: Dispatch<SetStateAction<Lines>>,
  setUr10: Dispatch<SetStateAction<Lines>>,
  setScara: Dispatch<SetStateAction<Lines>>,
  setEvents: Dispatch<SetStateAction<Lines>>,
  setWorkcell: Dispatch<SetStateAction<Workcell>>,
) {
  if (line === "__TCP_CLOSED__") {
    setEvents((g) => push(g, "LOG|(bridge) coordinator TCP disconnected - retrying"));
    return;
  }
  const parts = line.split("|");
  const head = parts[0];
  if (head === "TELEM") return;
  if (head === "STATE") {
    setEvents((x) => push(x, line));
    setWorkcell((state) => {
      const next: Workcell = {
        ...state,
        lines: { ...state.lines },
        robots: { ...state.robots },
        counts: { ...state.counts },
        armCans: { ...state.armCans },
        target: { ...state.target },
      };
      if (parts[1] === "mode") next.mode = parts[2] ?? state.mode;
      if (parts[1] === "line" && (parts[2] === "can" || parts[2] === "fruit")) next.lines[parts[2]] = parts[3] ?? "unknown";
      if (parts[1] === "robot" && ROBOTS.includes((parts[2] ?? "") as Robots))
        next.robots[parts[2] as Robots] = parts[3] ?? "unknown";
      if (parts[1] === "target") next.target = { type: parts[2] ?? "none", count: Number(parts[3] ?? 0) };
      return next;
    });
    return;
  }
  if (head === "COUNT") {
    setEvents((x) => push(x, line));
    setWorkcell((state) => {
      const next: Workcell = {
        ...state,
        lines: { ...state.lines },
        robots: { ...state.robots },
        counts: { ...state.counts },
        armCans: { ...state.armCans },
        target: { ...state.target },
      };
      if (["cans", "apples", "oranges", "fruits"].includes(parts[1] ?? ""))
        next.counts[parts[1] as keyof Workcell["counts"]] = Number(parts[2] ?? 0);
      if (["UR3e", "UR5e", "UR10e"].includes(parts[1] ?? "") && parts[2] === "cans")
        next.armCans[parts[1] as keyof Workcell["armCans"]] = Number(parts[3] ?? 0);
      return next;
    });
    return;
  }
  if (head === "CMD") {
    const arm = parts[1] ?? "";
    if (arm === "UR3e") setUr3((x) => push(x, line));
    else if (arm === "UR5e") setUr5((x) => push(x, line));
    else if (arm === "UR10e") setUr10((x) => push(x, line));
    else if (arm === "ScaraT6") setScara((x) => push(x, line));
    else setEvents((x) => push(x, line));
    setEvents((x) => push(x, line));
    return;
  }
  if (head === "LOG") {
    const rest = parts.slice(1).join("|");
    let matched = false;
    if (rest.includes("UR3e") || rest.includes("registered|UR3e")) {
      setUr3((x) => push(x, line));
      matched = true;
    }
    if (rest.includes("UR5e") || rest.includes("registered|UR5e")) {
      setUr5((x) => push(x, line));
      matched = true;
    }
    if (rest.includes("UR10e") || rest.includes("registered|UR10e")) {
      setUr10((x) => push(x, line));
      matched = true;
    }
    if (rest.includes("ScaraT6") || rest.includes("Scara")) {
      setScara((x) => push(x, line));
      matched = true;
    }
    if (!matched) setEvents((x) => push(x, line));
    setEvents((x) => push(x, line));
    return;
  }
  setEvents((x) => push(x, line));
}

export default function App() {
  const [view, setView] = useState<View>("dashboard");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [wsState, setWsState] = useState<"idle" | "open" | "closed">("idle");
  const [workcell, setWorkcell] = useState<Workcell>(DEFAULT_WORKCELL);
  const [ur3, setUr3] = useState<Lines>([]);
  const [ur5, setUr5] = useState<Lines>([]);
  const [ur10, setUr10] = useState<Lines>([]);
  const [scara, setScara] = useState<Lines>([]);
  const [events, setEvents] = useState<Lines>([]);
  const [prompt, setPrompt] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentLog, setAgentLog] = useState<AgentEntry[]>([
    {
      role: "agent",
      text: "RobotAbstraction is ready. Send a production goal and I will translate it into validated workcell controls.",
    },
  ]);
  const wsRef = useRef<WebSocket | null>(null);
  const bufRef = useRef("");
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const connect = useCallback(() => {
    wsRef.current?.close();
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    bufRef.current = "";
    ws.onopen = () => {
      setWsState("open");
      ws.send("CONTROL STATUS");
    };
    ws.onclose = () => {
      setWsState("closed");
      wsRef.current = null;
    };
    ws.onerror = () => setWsState("closed");
    ws.onmessage = (ev) => {
      bufRef.current += String(ev.data);
      let idx;
      while ((idx = bufRef.current.indexOf("\n")) >= 0) {
        const line = bufRef.current.slice(0, idx).replace(/\r$/, "");
        bufRef.current = bufRef.current.slice(idx + 1);
        if (line.length) routeLine(line, setUr3, setUr5, setUr10, setScara, setEvents, setWorkcell);
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ block: "end" });
  }, [agentLog, agentBusy, assistantOpen]);

  const runAgent = async (message = prompt) => {
    const text = message.trim();
    if (!text || agentBusy) return;
    setView("dashboard");
    setAssistantOpen(true);
    setPrompt("");
    setAgentBusy(true);
    setAgentLog((x) => [...x, { role: "operator", text }]);
    try {
      const res = await fetch(`${AGENT_URL}/agent`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: text, context: workcell }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "agent request failed");
      setAgentLog((x) => [
        ...x,
        {
          role: "agent",
          text: data.reply || "Plan executed.",
          commands: data.commands || [],
          planner: data.planner,
        },
      ]);
    } catch (err) {
      console.error("RobotAbstraction agent error:", err);
      setAgentLog((x) => [...x, { role: "agent", text: friendlyAgentError(err as Error) }]);
    } finally {
      setAgentBusy(false);
    }
  };

  const status = useMemo(() => {
    if (wsState === "open") return { cls: "ok", text: "Coordinator connected" };
    if (wsState === "closed") return { cls: "err", text: "Coordinator disconnected" };
    return { cls: "", text: "Connecting" };
  }, [wsState]);

  const latestEvents = events.slice(-8).reverse();
  const activeRobots = ROBOTS.filter((robot) => workcell.robots[robot] === "enabled").length;

  return (
    <div className={`app ${assistantOpen ? "with-assistant" : "assistant-collapsed"}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">RA</div>
          <div>
            <strong>Robot<span>Abstraction</span></strong>
            <small>Industrial Robot Ops</small>
          </div>
        </div>

        <nav className="nav">
          <button type="button" className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}>
            <span className="nav-icon">D</span>
            Dashboard
          </button>
          <button type="button" className={view === "logs" ? "active" : ""} onClick={() => setView("logs")}>
            <span className="nav-icon">L</span>
            Logs
          </button>
        </nav>

        <div className="sidebar-status">
          <span className={`status-dot ${status.cls}`} />
          <div>
            <strong>{status.text}</strong>
            <span>TCP 9099 via WebSocket 8765</span>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">RobotAbstraction Console</p>
            <h1>{view === "dashboard" ? "Dashboard" : "Robot Logs"}</h1>
          </div>
          <div className="controls">
            <button type="button" onClick={() => setAssistantOpen((open) => !open)}>
              {assistantOpen ? "Hide Agent" : "Show Agent"}
            </button>
          </div>
        </header>

        <main className="content">
          {view === "dashboard" && (
            <Dashboard
              activeRobots={activeRobots}
              assistantOpen={assistantOpen}
              latestEvents={latestEvents}
              setView={setView}
              setAssistantOpen={setAssistantOpen}
              workcell={workcell}
              runAgent={runAgent}
            />
          )}

          {view === "logs" && <LogsView events={events} scara={scara} ur3={ur3} ur5={ur5} ur10={ur10} />}
        </main>
      </section>

      <AssistantPanel
        agentBusy={agentBusy}
        agentLog={agentLog}
        chatEndRef={chatEndRef}
        open={assistantOpen}
        prompt={prompt}
        runAgent={runAgent}
        setOpen={setAssistantOpen}
        setPrompt={setPrompt}
        workcell={workcell}
      />
    </div>
  );
}

function Dashboard(props: {
  activeRobots: number;
  assistantOpen: boolean;
  latestEvents: Lines;
  setView: Dispatch<SetStateAction<View>>;
  setAssistantOpen: Dispatch<SetStateAction<boolean>>;
  workcell: Workcell;
  runAgent: (message?: string) => Promise<void>;
}) {
  const {
    activeRobots,
    assistantOpen,
    latestEvents,
    setAssistantOpen,
    setView,
    workcell,
    runAgent,
  } = props;
  const target = workcell.target.type === "none" ? "None" : `${workcell.target.count} ${workcell.target.type}`;

  return (
    <div className={`dashboard-grid ${assistantOpen ? "assistant-open" : "assistant-closed"}`}>
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Current Workcell Mode</p>
          <h2>{titleCaseMode(workcell.mode)}</h2>
          <div className="mode-meta">
            <span>{activeRobots}/4 robots active</span>
            <span>Can line {workcell.lines.can}</span>
            <span>Fruit line {workcell.lines.fruit}</span>
          </div>
        </div>
        <div className="hero-actions">
          <button type="button" className="success" onClick={() => void runAgent("Run high capacity mode")}>
            High Capacity
          </button>
          <button type="button" onClick={() => void runAgent("Run low power mode")}>
            Low Power
          </button>
          <button type="button" onClick={() => setAssistantOpen((open) => !open)}>
            {assistantOpen ? "Collapse Agent" : "Open Agent"}
          </button>
        </div>
      </section>

      <section className="kpi-grid">
        <Metric label="Production Target" value={target} />
        <Metric label="Cans Handled" value={String(workcell.counts.cans)} />
        <Metric label="Fruit Sorted" value={String(workcell.counts.fruits)} />
        <Metric label="Apples / Oranges" value={`${workcell.counts.apples} / ${workcell.counts.oranges}`} />
      </section>

      <section className="section-block robots-block">
        <div className="section-head">
          <div>
            <p className="eyebrow">Robots</p>
            <h2>Fleet Status</h2>
          </div>
          <span>{activeRobots} online</span>
        </div>
        <div className="robot-grid">
          {ROBOTS.map((robot) => (
            <RobotCard key={robot} robot={robot} state={workcell.robots[robot]} cans={robot === "ScaraT6" ? null : workcell.armCans[robot]} />
          ))}
        </div>
      </section>

      <section className="section-block lines-block">
        <div className="section-head">
          <div>
            <p className="eyebrow">Environment</p>
            <h2>Line Overview</h2>
          </div>
        </div>
        <div className="line-grid">
          <LineCard name="Can Line" state={workcell.lines.can} detail={`${workcell.counts.cans} cans handled`} />
          <LineCard name="Fruit Line" state={workcell.lines.fruit} detail={`${workcell.counts.fruits} fruit sorted`} />
        </div>
      </section>

      <section className="section-block activity-block">
        <div className="section-head">
          <div>
            <p className="eyebrow">Live Events</p>
            <h2>Recent Activity</h2>
          </div>
          <button type="button" onClick={() => setView("logs")}>
            View Logs
          </button>
        </div>
        <EventList lines={latestEvents} empty="No workcell events received yet." />
      </section>
    </div>
  );
}

function AssistantPanel(props: {
  agentBusy: boolean;
  agentLog: AgentEntry[];
  chatEndRef: React.RefObject<HTMLDivElement>;
  open: boolean;
  prompt: string;
  runAgent: (message?: string) => Promise<void>;
  setOpen: Dispatch<SetStateAction<boolean>>;
  setPrompt: Dispatch<SetStateAction<string>>;
  workcell: Workcell;
}) {
  const { agentBusy, agentLog, chatEndRef, open, prompt, runAgent, setOpen, setPrompt, workcell } = props;

  if (!open) {
    return (
      <aside className="assistant-rail">
        <button type="button" onClick={() => setOpen(true)}>
          RA
        </button>
      </aside>
    );
  }

  return (
    <aside className="assistant-panel">
      <header className="assistant-head">
        <div>
          <p className="eyebrow">RobotAbstraction</p>
          <h2>Control Agent</h2>
        </div>
        <button type="button" onClick={() => setOpen(false)}>
          Collapse
        </button>
      </header>

      <section className="assistant-chat">
        <div className="chat-feed">
          {agentLog.map((entry, index) => (
            <ChatMessage entry={entry} key={`${entry.role}-${index}-${entry.text.slice(0, 16)}`} />
          ))}
          {agentBusy && (
            <div className="message-row agent">
              <div className="avatar">AI</div>
              <div className="message">
                <div className="message-meta">RobotAbstraction Agent</div>
                <div>Planning validated workcell controls...</div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className="assistant-bottom">
          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void runAgent();
            }}
          >
            <input
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Ask for a production change..."
            />
            <button type="submit" className="success" disabled={agentBusy}>
              Send
            </button>
          </form>
        </div>
      </section>
    </aside>
  );
}

function LogsView(props: { events: Lines; scara: Lines; ur3: Lines; ur5: Lines; ur10: Lines }) {
  const { events, scara, ur3, ur5, ur10 } = props;

  return (
    <div className="logs-layout">
      <Panel title="Workcell Events" lines={events} />
      <Panel title="UR3e" lines={ur3} />
      <Panel title="UR5e" lines={ur5} />
      <Panel title="UR10e" lines={ur10} />
      <Panel title="ScaraT6" lines={scara} />
    </div>
  );
}

function Metric(props: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function RobotCard(props: { robot: Robots; state: string; cans: number | null }) {
  const enabled = props.state === "enabled";
  return (
    <article className="robot-card">
      <div className="robot-card-top">
        <div className="robot-avatar">{props.robot === "ScaraT6" ? "ST" : props.robot.replace("e", "")}</div>
        <span className={`pill ${enabled ? "ok" : "err"}`}>{props.state}</span>
      </div>
      <h3>{props.robot}</h3>
      <p>{props.cans === null ? "Fruit sorting cell" : `${props.cans} cans handled`}</p>
    </article>
  );
}

function LineCard(props: { name: string; state: string; detail: string }) {
  const running = props.state === "running";
  return (
    <article className="line-card">
      <div>
        <span className={`status-dot ${running ? "ok" : "err"}`} />
        <h3>{props.name}</h3>
      </div>
      <strong>{titleCaseMode(props.state)}</strong>
      <p>{props.detail}</p>
    </article>
  );
}

function ChatMessage(props: { entry: AgentEntry }) {
  const { entry } = props;
  const isAgent = entry.role === "agent";
  const changes = appliedChanges(entry.commands);

  return (
    <div className={`message-row ${entry.role}`}>
      <div className="avatar">{isAgent ? "AI" : "OP"}</div>
      <div className="message">
        <div className="message-meta">{isAgent ? "RobotAbstraction Agent" : "Operator"}</div>
        <div>{entry.text}</div>
        {changes.length > 0 && (
          <div className="applied-changes">
            <span>Applied changes</span>
            <ul>
              {changes.map((change, index) => (
                <li key={`${index}-${change}`}>{change}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function EventList(props: { lines: Lines; empty: string }) {
  if (!props.lines.length) return <p className="empty-state">{props.empty}</p>;
  return (
    <div className="event-list">
      {props.lines.map((line, i) => (
        <div key={`${i}-${line.slice(0, 24)}`} className="event-row">
          <span className={classify(line)}>{lineLabel(line)}</span>
          <code>{line}</code>
        </div>
      ))}
    </div>
  );
}

function Panel(props: { title: string; lines: Lines }) {
  const { title, lines } = props;
  return (
    <section className="panel">
      <header>
        <span>{title}</span>
        <strong>{lines.length}</strong>
      </header>
      <pre className="body">
        {lines.length === 0 ? (
          <div className="empty-log">Waiting for events...</div>
        ) : (
          lines.map((line, i) => (
            <div key={`${i}-${line.slice(0, 24)}`} className={classify(line)}>
              {line}
            </div>
          ))
        )}
      </pre>
    </section>
  );
}
