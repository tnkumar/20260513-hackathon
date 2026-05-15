import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://127.0.0.1:8765";
const AGENT_URL = import.meta.env.VITE_AGENT_URL ?? "http://127.0.0.1:8787";

type Lines = string[];
type Robots = "UR3e" | "UR5e" | "UR10e" | "ScaraT6";

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

const DEFAULT_WORKCELL: Workcell = {
  mode: "balanced",
  lines: { can: "running", fruit: "running" },
  robots: { UR3e: "enabled", UR5e: "enabled", UR10e: "enabled", ScaraT6: "enabled" },
  counts: { cans: 0, apples: 0, oranges: 0, fruits: 0 },
  armCans: { UR3e: 0, UR5e: 0, UR10e: 0 },
  target: { type: "none", count: 0 },
};

const EXAMPLES = [
  "Run balanced production",
  "Prioritize fruit handling until 6 fruits are sorted",
  "Prioritize can handling",
  "Run low power mode",
  "Run high capacity mode",
  "Disable UR10e and continue production",
  "Stop fruit line",
  "Handle 5 cans then return to balanced mode",
  "Pause simulation",
  "Generate a production summary",
];

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
      if (parts[1] === "robot" && ["UR3e", "UR5e", "UR10e", "ScaraT6"].includes(parts[2] ?? ""))
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
  const [wsState, setWsState] = useState<"idle" | "open" | "closed">("idle");
  const [workcell, setWorkcell] = useState<Workcell>(DEFAULT_WORKCELL);
  const [ur3, setUr3] = useState<Lines>([]);
  const [ur5, setUr5] = useState<Lines>([]);
  const [ur10, setUr10] = useState<Lines>([]);
  const [scara, setScara] = useState<Lines>([]);
  const [events, setEvents] = useState<Lines>([]);
  const [prompt, setPrompt] = useState("Run balanced production");
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentLog, setAgentLog] = useState<AgentEntry[]>([
    {
      role: "agent",
      text: "FactoryFlow Copilot is ready. Send a production goal and I will translate it into validated workcell controls.",
    },
  ]);
  const wsRef = useRef<WebSocket | null>(null);
  const bufRef = useRef("");

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

  const sendControl = (cmd: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(cmd);
  };

  const runAgent = async (message = prompt) => {
    const text = message.trim();
    if (!text || agentBusy) return;
    setPrompt(text);
    setAgentBusy(true);
    setAgentLog((x) => [...x, { role: "operator", text }]);
    try {
      const res = await fetch(`${AGENT_URL}/agent`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: text }),
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
      setAgentLog((x) => [...x, { role: "agent", text: `Agent error: ${(err as Error).message}` }]);
    } finally {
      setAgentBusy(false);
    }
  };

  const status = useMemo(() => {
    if (wsState === "open") return { cls: "ok", text: "Coordinator connected" };
    if (wsState === "closed") return { cls: "err", text: "Coordinator disconnected" };
    return { cls: "", text: "Connecting" };
  }, [wsState]);

  return (
    <div className="app">
      <header>
        <div>
          <h1>FactoryFlow Copilot</h1>
          <p>Intent-based robotic workcell orchestration for UR can handling and ScaraT6 fruit sorting.</p>
        </div>
        <div className="controls">
          <span className={`badge ${status.cls}`}>{status.text}</span>
          <button type="button" className="primary" onClick={() => sendControl("CONTROL RUN")}>
            Run
          </button>
          <button type="button" onClick={() => sendControl("CONTROL PAUSE")}>
            Pause
          </button>
          <button type="button" onClick={() => sendControl("CONTROL FAST")}>
            Fast
          </button>
          <button type="button" onClick={connect}>
            Reconnect
          </button>
        </div>
      </header>

      <main className="shell">
        <section className="command-center">
          <div className="agent">
            <div className="agent-head">
              <h2>AI Command Center</h2>
              <span>{agentBusy ? "planning" : "ready"}</span>
            </div>
            <form
              className="prompt-row"
              onSubmit={(event) => {
                event.preventDefault();
                void runAgent();
              }}
            >
              <input value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              <button type="submit" className="primary" disabled={agentBusy}>
                Send
              </button>
            </form>
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" onClick={() => void runAgent(example)}>
                  {example}
                </button>
              ))}
            </div>
            <div className="conversation">
              {agentLog.slice(-8).map((entry, index) => (
                <div className={`bubble ${entry.role}`} key={`${entry.role}-${index}-${entry.text.slice(0, 16)}`}>
                  <div className="bubble-role">{entry.role === "operator" ? "Operator" : `Copilot${entry.planner ? ` · ${entry.planner}` : ""}`}</div>
                  <div>{entry.text}</div>
                  {entry.commands && entry.commands.length > 0 && (
                    <ul>
                      {entry.commands.map((cmd) => (
                        <li key={cmd}>{cmd}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="metrics">
            <Metric label="Mode" value={titleCaseMode(workcell.mode)} />
            <Metric label="Can Line" value={titleCaseMode(workcell.lines.can)} />
            <Metric label="Fruit Line" value={titleCaseMode(workcell.lines.fruit)} />
            <Metric label="Target" value={workcell.target.type === "none" ? "None" : `${workcell.target.count} ${workcell.target.type}`} />
            <Metric label="Cans" value={String(workcell.counts.cans)} />
            <Metric label="Apples" value={String(workcell.counts.apples)} />
            <Metric label="Oranges" value={String(workcell.counts.oranges)} />
            <Metric label="Fruits" value={String(workcell.counts.fruits)} />
          </div>

          <div className="robot-status">
            {(Object.keys(workcell.robots) as Robots[]).map((robot) => (
              <div className="robot-tile" key={robot}>
                <span>{robot}</span>
                <strong className={workcell.robots[robot] === "enabled" ? "enabled" : "disabled"}>{workcell.robots[robot]}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="logs">
          <Panel title="Workcell Events" lines={events} />
          <Panel title="UR3e" lines={ur3} />
          <Panel title="UR5e" lines={ur5} />
          <Panel title="UR10e" lines={ur10} />
          <Panel title="ScaraT6" lines={scara} />
        </section>
      </main>
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

function Panel(props: { title: string; lines: Lines }) {
  const { title, lines } = props;
  return (
    <section className="panel">
      <header>{title}</header>
      <pre className="body">
        {lines.map((line, i) => (
          <div key={`${i}-${line.slice(0, 24)}`} className={classify(line)}>
            {line}
          </div>
        ))}
      </pre>
    </section>
  );
}
