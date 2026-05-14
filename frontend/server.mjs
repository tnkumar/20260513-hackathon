/**
 * Bridges browser WebSocket (dashboard) <-> coordinator TCP (REGISTER UI).
 * Env: COORDINATOR_TCP_PORT (default 9099), FRONTEND_WS_PORT (default 8765).
 */
import net from "net";
import { WebSocketServer } from "ws";

const TCP_PORT = parseInt(process.env.COORDINATOR_TCP_PORT || "9099", 10);
const WS_PORT = parseInt(process.env.FRONTEND_WS_PORT || "8765", 10);

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
