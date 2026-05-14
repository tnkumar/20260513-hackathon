"""
Natural language conveyor controller using Gemini function calling.

Connects to the Webots coordinator as a UI TCP client and sends
CONVEYOR_START / CONVEYOR_STOP commands based on natural language input.

Usage:
    GEMINI_API_KEY=<key> python llm_agent/gemini_agent.py

Environment variables (all optional except GEMINI_API_KEY):
    GEMINI_API_KEY        — required
    COORDINATOR_HOST      — default 127.0.0.1
    COORDINATOR_TCP_PORT  — default 9099
    GEMINI_MODEL          — default gemini-2.0-flash
"""

import os
import socket
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COORDINATOR_HOST = os.environ.get("COORDINATOR_HOST", "127.0.0.1")
COORDINATOR_PORT = int(os.environ.get("COORDINATOR_TCP_PORT", "9099"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_CONVEYOR_PARAM = types.Schema(
    type=types.Type.STRING,
    enum=["can", "fruit"],
    description=(
        "'can' — the three UR robot can belts; "
        "'fruit' — the SCARA fruit sorting belt"
    ),
)

TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="start_conveyor",
            description="Start a conveyor belt that is currently stopped.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"conveyor": _CONVEYOR_PARAM},
                required=["conveyor"],
            ),
        ),
        types.FunctionDeclaration(
            name="stop_conveyor",
            description="Stop a running conveyor belt.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"conveyor": _CONVEYOR_PARAM},
                required=["conveyor"],
            ),
        ),
    ]
)

# ---------------------------------------------------------------------------
# Coordinator TCP helpers
# ---------------------------------------------------------------------------

def _drain(sock: socket.socket) -> None:
    """Discard all incoming data so the coordinator's send buffer never fills up."""
    try:
        while True:
            if not sock.recv(4096):
                break
    except OSError:
        pass


def connect_coordinator() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((COORDINATOR_HOST, COORDINATOR_PORT))
    s.sendall(b"REGISTER UI\n")
    threading.Thread(target=_drain, args=(s,), daemon=True).start()
    return s


def send_tcp(sock: socket.socket, cmd: str) -> None:
    sock.sendall(f"{cmd}\n".encode())

# ---------------------------------------------------------------------------
# Function call dispatch
# ---------------------------------------------------------------------------

def execute_function_call(sock: socket.socket, name: str, args: dict) -> str:
    conveyor = args.get("conveyor", "")
    if conveyor not in ("can", "fruit"):
        return f"Unknown conveyor '{conveyor}' — expected 'can' or 'fruit'."

    if name == "start_conveyor":
        send_tcp(sock, f"CONVEYOR_START {conveyor}")
        label = "can belts" if conveyor == "can" else "fruit belt"
        return f"Started {label}."

    if name == "stop_conveyor":
        send_tcp(sock, f"CONVEYOR_STOP {conveyor}")
        label = "can belts" if conveyor == "can" else "fruit belt"
        return f"Stopped {label}."

    return f"Unrecognised function '{name}'."

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Error: GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

    print(f"Connecting to coordinator at {COORDINATOR_HOST}:{COORDINATOR_PORT} …")
    try:
        sock = connect_coordinator()
    except OSError as exc:
        sys.exit(f"Could not connect to coordinator: {exc}")
    print("Connected. Type a command, e.g.:")
    print('  "stop the fruit conveyor"')
    print('  "start the can conveyor"')
    print("Ctrl+C or Ctrl+D to exit.\n")

    try:
        while True:
            try:
                user_input = input("> ").strip()
            except EOFError:
                break
            if not user_input:
                continue

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_input,
                config=types.GenerateContentConfig(tools=[TOOLS]),
            )

            part = response.candidates[0].content.parts[0]

            if part.function_call:
                fn = part.function_call
                result = execute_function_call(sock, fn.name, dict(fn.args))
                print(result)
            else:
                # Gemini responded with text — command wasn't understood as a tool call
                print(f"[Gemini] {part.text}")

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("\nDisconnected.")


if __name__ == "__main__":
    main()
