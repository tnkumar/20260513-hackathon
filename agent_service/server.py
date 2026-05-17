from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import uuid

from factory_agent import plan


HOST = os.environ.get("ADK_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADK_AGENT_PORT", "8790"))


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._json(204, {})

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "factoryflow-adk"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/plan":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length", "0"))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            message = str(body.get("message", "")).strip()
            if not message:
                self._json(400, {"error": "message is required"})
                return
            request_id = str(body.get("request_id") or uuid.uuid4().hex[:8])
            context = body.get("context") or {}
            print(f"adk-agent[{request_id}]: prompt={message!r}", flush=True)
            print(f"adk-agent[{request_id}]: context={json.dumps(context, sort_keys=True)}", flush=True)
            result = plan(message, context, request_id=request_id)
            print(f"adk-agent[{request_id}]: result={json.dumps(result, sort_keys=True)}", flush=True)
            self._json(200, result)
        except Exception as exc:
            print(f"adk-agent: error={exc}", flush=True)
            self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("adk-agent:", fmt % args, flush=True)


if __name__ == "__main__":
    print(f"adk-agent: http://{HOST}:{PORT}/plan", flush=True)
    HTTPServer((HOST, PORT), Handler).serve_forever()
