import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://127.0.0.1:8765";

type Lines = string[];

const MAX = 400;

function push(lines: Lines, line: string): Lines {
  const next = [...lines, line];
  return next.length > MAX ? next.slice(-MAX) : next;
}

function classify(line: string): string {
  if (line.startsWith("CMD|")) return "line-cmd";
  if (line.startsWith("LOG|")) return "line-log";
  return "line-recv";
}

function routeLine(
  line: string,
  setUr3: Dispatch<SetStateAction<Lines>>,
  setUr5: Dispatch<SetStateAction<Lines>>,
  setUr10: Dispatch<SetStateAction<Lines>>,
  setScara: Dispatch<SetStateAction<Lines>>,
) {
  if (line === "__TCP_CLOSED__") {
    setUr3((g) => push(g, "LOG|(bridge) coordinator TCP disconnected — retrying…"));
    return;
  }
  const parts = line.split("|");
  const head = parts[0];
  if (head === "TELEM")
    return;
  if (head === "CMD") {
    const arm = parts[1] ?? "";
    if (arm === "UR3e") setUr3((x) => push(x, line));
    else if (arm === "UR5e") setUr5((x) => push(x, line));
    else if (arm === "UR10e") setUr10((x) => push(x, line));
    else if (arm === "ScaraT6") setScara((x) => push(x, line));
    else setUr3((x) => push(x, line));
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
    if (!matched) setUr3((x) => push(x, line));
    return;
  }
  setUr3((x) => push(x, line));
}

export default function App() {
  const [wsState, setWsState] = useState<"idle" | "open" | "closed">("idle");
  const [ur3, setUr3] = useState<Lines>([]);
  const [ur5, setUr5] = useState<Lines>([]);
  const [ur10, setUr10] = useState<Lines>([]);
  const [scara, setScara] = useState<Lines>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const bufRef = useRef("");

  const connect = useCallback(() => {
    wsRef.current?.close();
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    bufRef.current = "";
    ws.onopen = () => setWsState("open");
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
        if (line.length) routeLine(line, setUr3, setUr5, setUr10, setScara);
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

  const status = useMemo(() => {
    if (wsState === "open") return { cls: "ok", text: "WebSocket connected" };
    if (wsState === "closed") return { cls: "err", text: "WebSocket disconnected" };
    return { cls: "", text: "Connecting…" };
  }, [wsState]);

  return (
    <div className="app">
      <header>
        <h1>UR + ScaraT6 · coordinator dashboard</h1>
        <div className="controls">
          <span className={`badge ${status.cls}`}>{status.text}</span>
          <button type="button" className="primary" onClick={() => sendControl("CONTROL RUN")}>
            Run simulation
          </button>
          <button type="button" onClick={() => sendControl("CONTROL PAUSE")}>
            Pause
          </button>
          <button type="button" onClick={() => sendControl("CONTROL FAST")}>
            Fast mode
          </button>
          <button type="button" onClick={connect}>
            Reconnect
          </button>
        </div>
      </header>

      <div className="layout">
        <Panel title="UR3e" lines={ur3} />
        <Panel title="UR5e" lines={ur5} />
        <Panel title="UR10e" lines={ur10} />
        <Panel title="ScaraT6" lines={scara} />
      </div>
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
