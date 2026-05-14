# # """
# # Natural language conveyor controller using Gemini function calling.

# # Connects to the Webots coordinator as a UI TCP client and sends
# # CONVEYOR_START / CONVEYOR_STOP commands based on natural language input.

# # Usage:
# #     GEMINI_API_KEY=<key> python llm_agent/gemini_agent.py

# # Environment variables (all optional except GEMINI_API_KEY):
# #     GEMINI_API_KEY        — required
# #     COORDINATOR_HOST      — default 127.0.0.1
# #     COORDINATOR_TCP_PORT  — default 9099
# #     GEMINI_MODEL          — default gemini-2.0-flash
# # """

# # import os
# # import socket
# # import sys
# # import threading
# # from pathlib import Path

# # from dotenv import load_dotenv

# # load_dotenv(Path(__file__).parent / ".env")

# # from google import genai
# # from google.genai import types

# # # ---------------------------------------------------------------------------
# # # Config
# # # ---------------------------------------------------------------------------

# # COORDINATOR_HOST = os.environ.get("COORDINATOR_HOST", "127.0.0.1")
# # COORDINATOR_PORT = int(os.environ.get("COORDINATOR_TCP_PORT", "9099"))
# # GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# # # ---------------------------------------------------------------------------
# # # Tool definitions
# # # ---------------------------------------------------------------------------

# # _CONVEYOR_PARAM = types.Schema(
# #     type=types.Type.STRING,
# #     enum=["can", "fruit"],
# #     description=(
# #         "'can' — the three UR robot can belts; "
# #         "'fruit' — the SCARA fruit sorting belt"
# #     ),
# # )

# # TOOLS = types.Tool(
# #     function_declarations=[
# #         types.FunctionDeclaration(
# #             name="start_conveyor",
# #             description="Start a conveyor belt that is currently stopped.",
# #             parameters=types.Schema(
# #                 type=types.Type.OBJECT,
# #                 properties={"conveyor": _CONVEYOR_PARAM},
# #                 required=["conveyor"],
# #             ),
# #         ),
# #         types.FunctionDeclaration(
# #             name="stop_conveyor",
# #             description="Stop a running conveyor belt.",
# #             parameters=types.Schema(
# #                 type=types.Type.OBJECT,
# #                 properties={"conveyor": _CONVEYOR_PARAM},
# #                 required=["conveyor"],
# #             ),
# #         ),
# #     ]
# # )

# # # ---------------------------------------------------------------------------
# # # Coordinator TCP helpers
# # # ---------------------------------------------------------------------------

# # def _drain(sock: socket.socket) -> None:
# #     """Discard all incoming data so the coordinator's send buffer never fills up."""
# #     try:
# #         while True:
# #             if not sock.recv(4096):
# #                 break
# #     except OSError:
# #         pass


# # def connect_coordinator() -> socket.socket:
# #     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# #     s.connect((COORDINATOR_HOST, COORDINATOR_PORT))
# #     s.sendall(b"REGISTER UI\n")
# #     threading.Thread(target=_drain, args=(s,), daemon=True).start()
# #     return s


# # def send_tcp(sock: socket.socket, cmd: str) -> None:
# #     sock.sendall(f"{cmd}\n".encode())

# # # ---------------------------------------------------------------------------
# # # Function call dispatch
# # # ---------------------------------------------------------------------------

# # def execute_function_call(sock: socket.socket, name: str, args: dict) -> str:
# #     conveyor = args.get("conveyor", "")
# #     if conveyor not in ("can", "fruit"):
# #         return f"Unknown conveyor '{conveyor}' — expected 'can' or 'fruit'."

# #     if name == "start_conveyor":
# #         send_tcp(sock, f"CONVEYOR_START {conveyor}")
# #         label = "can belts" if conveyor == "can" else "fruit belt"
# #         return f"Started {label}."

# #     if name == "stop_conveyor":
# #         send_tcp(sock, f"CONVEYOR_STOP {conveyor}")
# #         label = "can belts" if conveyor == "can" else "fruit belt"
# #         return f"Stopped {label}."

# #     return f"Unrecognised function '{name}'."

# # # ---------------------------------------------------------------------------
# # # Main loop
# # # ---------------------------------------------------------------------------

# # def main() -> None:
# #     api_key = os.environ.get("GEMINI_API_KEY")
# #     if not api_key:
# #         sys.exit("Error: GEMINI_API_KEY environment variable is not set.")

# #     client = genai.Client(api_key=api_key)

# #     print(f"Connecting to coordinator at {COORDINATOR_HOST}:{COORDINATOR_PORT} …")
# #     try:
# #         sock = connect_coordinator()
# #     except OSError as exc:
# #         sys.exit(f"Could not connect to coordinator: {exc}")
# #     print("Connected. Type a command, e.g.:")
# #     print('  "stop the fruit conveyor"')
# #     print('  "start the can conveyor"')
# #     print("Ctrl+C or Ctrl+D to exit.\n")

# #     try:
# #         while True:
# #             try:
# #                 user_input = input("> ").strip()
# #             except EOFError:
# #                 break
# #             if not user_input:
# #                 continue

# #             response = client.models.generate_content(
# #                 model=GEMINI_MODEL,
# #                 contents=user_input,
# #                 config=types.GenerateContentConfig(tools=[TOOLS]),
# #             )

# #             part = response.candidates[0].content.parts[0]

# #             if part.function_call:
# #                 fn = part.function_call
# #                 result = execute_function_call(sock, fn.name, dict(fn.args))
# #                 print(result)
# #             else:
# #                 # Gemini responded with text — command wasn't understood as a tool call
# #                 print(f"[Gemini] {part.text}")

# #     except KeyboardInterrupt:
# #         pass
# #     finally:
# #         sock.close()
# #         print("\nDisconnected.")


# # if __name__ == "__main__":
# #     main()



# """
# LLM-powered intelligent factory orchestration agent.

# Supports:
# - conveyor orchestration
# - production modes
# - intelligent load balancing
# - robot enable/disable
# - autonomous balancing
# - simulation control

# Works with the upgraded coordinator.py.
# """

# import os
# import socket
# import sys
# import threading
# from pathlib import Path

# from dotenv import load_dotenv

# load_dotenv(Path(__file__).parent / ".env")

# from google import genai
# from google.genai import types


# # ---------------------------------------------------------------------------
# # CONFIG
# # ---------------------------------------------------------------------------

# COORDINATOR_HOST = os.environ.get(
#     "COORDINATOR_HOST",
#     "127.0.0.1"
# )

# COORDINATOR_PORT = int(
#     os.environ.get(
#         "COORDINATOR_TCP_PORT",
#         "9099"
#     )
# )

# GEMINI_MODEL = os.environ.get(
#     "GEMINI_MODEL",
#     "gemini-2.0-flash"
# )


# # ---------------------------------------------------------------------------
# # PARAMETER SCHEMAS
# # ---------------------------------------------------------------------------

# _CONVEYOR_PARAM = types.Schema(
#     type=types.Type.STRING,

#     enum=[
#         "can",
#         "fruit"
#     ],

#     description=(
#         "'can' = UR robot can conveyors, "
#         "'fruit' = SCARA fruit conveyor"
#     )
# )

# _ARM_PARAM = types.Schema(
#     type=types.Type.STRING,

#     enum=[
#         "UR3e",
#         "UR5e",
#         "UR10e"
#     ],

#     description="Industrial robot arm"
# )

# _MODE_PARAM = types.Schema(
#     type=types.Type.STRING,

#     enum=[
#         "balanced",
#         "prioritize_fruit",
#         "maximize_cans",
#         "low_power",
#         "high_capacity"
#     ],

#     description=(
#         "Factory production orchestration mode"
#     )
# )

# _SIM_PARAM = types.Schema(
#     type=types.Type.STRING,

#     enum=[
#         "RUN",
#         "PAUSE",
#         "FAST"
#     ],

#     description="Simulation execution mode"
# )


# # ---------------------------------------------------------------------------
# # TOOL DEFINITIONS
# # ---------------------------------------------------------------------------

# TOOLS = types.Tool(

#     function_declarations=[

#         # --------------------------------------------------
#         # Conveyor Control
#         # --------------------------------------------------

#         types.FunctionDeclaration(

#             name="start_conveyor",

#             description=(
#                 "Start a conveyor system."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={
#                     "conveyor": _CONVEYOR_PARAM
#                 },

#                 required=["conveyor"]
#             )
#         ),

#         types.FunctionDeclaration(

#             name="stop_conveyor",

#             description=(
#                 "Stop a conveyor system."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={
#                     "conveyor": _CONVEYOR_PARAM
#                 },

#                 required=["conveyor"]
#             )
#         ),

#         # --------------------------------------------------
#         # Production Modes
#         # --------------------------------------------------

#         types.FunctionDeclaration(

#             name="set_production_mode",

#             description=(
#                 "Configure intelligent "
#                 "factory production mode."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={
#                     "mode": _MODE_PARAM
#                 },

#                 required=["mode"]
#             )
#         ),

#         # --------------------------------------------------
#         # Robot Allocation
#         # --------------------------------------------------

#         types.FunctionDeclaration(

#             name="enable_arm",

#             description=(
#                 "Enable a robot arm "
#                 "for production."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={
#                     "arm": _ARM_PARAM
#                 },

#                 required=["arm"]
#             )
#         ),

#         types.FunctionDeclaration(

#             name="disable_arm",

#             description=(
#                 "Disable a robot arm "
#                 "from production."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={
#                     "arm": _ARM_PARAM
#                 },

#                 required=["arm"]
#             )
#         ),

#         # --------------------------------------------------
#         # Auto Balancing
#         # --------------------------------------------------

#         types.FunctionDeclaration(

#             name="toggle_auto_balance",

#             description=(
#                 "Enable or disable "
#                 "automatic intelligent "
#                 "load balancing."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={

#                     "enabled": types.Schema(
#                         type=types.Type.BOOLEAN
#                     )
#                 },

#                 required=["enabled"]
#             )
#         ),

#         # --------------------------------------------------
#         # Simulation Control
#         # --------------------------------------------------

#         types.FunctionDeclaration(

#             name="set_simulation_mode",

#             description=(
#                 "Control Webots simulation mode."
#             ),

#             parameters=types.Schema(

#                 type=types.Type.OBJECT,

#                 properties={
#                     "mode": _SIM_PARAM
#                 },

#                 required=["mode"]
#             )
#         )
#     ]
# )


# # ---------------------------------------------------------------------------
# # TCP HELPERS
# # ---------------------------------------------------------------------------

# def _drain(sock: socket.socket):

#     """
#     Drain coordinator responses continuously.
#     """

#     try:

#         while True:

#             if not sock.recv(4096):
#                 break

#     except OSError:
#         pass


# def connect_coordinator():

#     s = socket.socket(
#         socket.AF_INET,
#         socket.SOCK_STREAM
#     )

#     s.connect(
#         (
#             COORDINATOR_HOST,
#             COORDINATOR_PORT
#         )
#     )

#     s.sendall(
#         b"REGISTER UI\n"
#     )

#     threading.Thread(
#         target=_drain,
#         args=(s,),
#         daemon=True
#     ).start()

#     return s


# def send_tcp(sock, cmd):

#     print(f"[TCP] {cmd}")

#     sock.sendall(
#         f"{cmd}\n".encode()
#     )


# # ---------------------------------------------------------------------------
# # FUNCTION DISPATCH
# # ---------------------------------------------------------------------------

# def execute_function_call(
#     sock,
#     name,
#     args
# ):

#     # ------------------------------------------------------
#     # Conveyor Start
#     # ------------------------------------------------------

#     if name == "start_conveyor":

#         conveyor = args["conveyor"]

#         send_tcp(
#             sock,
#             f"CONVEYOR_START {conveyor}"
#         )

#         return (
#             f"Started "
#             f"{conveyor} conveyor."
#         )

#     # ------------------------------------------------------
#     # Conveyor Stop
#     # ------------------------------------------------------

#     elif name == "stop_conveyor":

#         conveyor = args["conveyor"]

#         send_tcp(
#             sock,
#             f"CONVEYOR_STOP {conveyor}"
#         )

#         return (
#             f"Stopped "
#             f"{conveyor} conveyor."
#         )

#     # ------------------------------------------------------
#     # Production Mode
#     # ------------------------------------------------------

#     elif name == "set_production_mode":

#         mode = args["mode"]

#         send_tcp(
#             sock,
#             f"SET_MODE {mode}"
#         )

#         return (
#             f"Production mode changed "
#             f"to {mode}."
#         )

#     # ------------------------------------------------------
#     # Enable Arm
#     # ------------------------------------------------------

#     elif name == "enable_arm":

#         arm = args["arm"]

#         send_tcp(
#             sock,
#             f"ENABLE_ARM {arm}"
#         )

#         return (
#             f"{arm} enabled."
#         )

#     # ------------------------------------------------------
#     # Disable Arm
#     # ------------------------------------------------------

#     elif name == "disable_arm":

#         arm = args["arm"]

#         send_tcp(
#             sock,
#             f"DISABLE_ARM {arm}"
#         )

#         return (
#             f"{arm} disabled."
#         )

#     # ------------------------------------------------------
#     # Auto Balance
#     # ------------------------------------------------------

#     elif name == "toggle_auto_balance":

#         enabled = args["enabled"]

#         cmd = (
#             "AUTO_BALANCE ON"
#             if enabled
#             else "AUTO_BALANCE OFF"
#         )

#         send_tcp(sock, cmd)

#         return (
#             "Automatic load balancing "
#             + (
#                 "enabled."
#                 if enabled
#                 else "disabled."
#             )
#         )

#     # ------------------------------------------------------
#     # Simulation Mode
#     # ------------------------------------------------------

#     elif name == "set_simulation_mode":

#         mode = args["mode"]

#         send_tcp(
#             sock,
#             f"CONTROL {mode}"
#         )

#         return (
#             f"Simulation mode set "
#             f"to {mode}."
#         )

#     return (
#         f"Unknown operation: {name}"
#     )


# # ---------------------------------------------------------------------------
# # MAIN
# # ---------------------------------------------------------------------------

# def main():

#     api_key = os.environ.get(
#         "GEMINI_API_KEY"
#     )

#     if not api_key:

#         sys.exit(
#             "Error: GEMINI_API_KEY "
#             "environment variable "
#             "is not set."
#         )

#     client = genai.Client(
#         api_key=api_key
#     )

#     print(
#         f"Connecting to coordinator at "
#         f"{COORDINATOR_HOST}:"
#         f"{COORDINATOR_PORT} ..."
#     )

#     try:

#         sock = connect_coordinator()

#     except OSError as exc:

#         sys.exit(
#             f"Could not connect "
#             f"to coordinator: {exc}"
#         )

#     print("\nConnected.\n")

#     print("Example commands:")
#     print("-----------------------------")
#     print("Start can conveyor")
#     print("Stop fruit conveyor")
#     print("Run balanced production")
#     print("Prioritize fruit handling")
#     print("Run low power mode")
#     print("Run high capacity mode")
#     print("Enable UR10e")
#     print("Disable UR3e")
#     print("Enable automatic balancing")
#     print("Pause simulation")
#     print("-----------------------------\n")

#     try:

#         while True:

#             try:

#                 user_input = (
#                     input("> ")
#                     .strip()
#                 )

#             except EOFError:
#                 break

#             if not user_input:
#                 continue

#             response = client.models.generate_content(

#                 model=GEMINI_MODEL,

#                 contents=user_input,

#                 config=types.GenerateContentConfig(
#                     tools=[TOOLS]
#                 )
#             )

#             part = (
#                 response.candidates[0]
#                 .content.parts[0]
#             )

#             if part.function_call:

#                 fn = part.function_call

#                 result = execute_function_call(
#                     sock,
#                     fn.name,
#                     dict(fn.args)
#                 )

#                 print(
#                     f"[ACTION] {result}"
#                 )

#             else:

#                 print(
#                     f"[Gemini] "
#                     f"{part.text}"
#                 )

#     except KeyboardInterrupt:
#         pass

#     finally:

#         sock.close()

#         print("\nDisconnected.")


# if __name__ == "__main__":

#     main()


"""
LLM-powered intelligent factory orchestration agent.

Supports:
- conveyor control
- production modes
- robot allocation
- intelligent load balancing
- simulation control
- semantic factory orchestration
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


# ------------------------------------------------------
# CONFIG
# ------------------------------------------------------

COORDINATOR_HOST = os.environ.get(
    "COORDINATOR_HOST",
    "127.0.0.1"
)

COORDINATOR_PORT = int(
    os.environ.get(
        "COORDINATOR_TCP_PORT",
        "9099"
    )
)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
)


# ------------------------------------------------------
# PARAMETER SCHEMAS
# ------------------------------------------------------

_CONVEYOR_PARAM = types.Schema(
    type=types.Type.STRING,

    enum=[
        "can",
        "fruit"
    ]
)

_ARM_PARAM = types.Schema(
    type=types.Type.STRING,

    enum=[
        "UR3e",
        "UR5e",
        "UR10e"
    ]
)

_MODE_PARAM = types.Schema(
    type=types.Type.STRING,

    enum=[
        "balanced",
        "prioritize_fruit",
        "maximize_cans",
        "low_power",
        "high_capacity"
    ]
)

_SIM_PARAM = types.Schema(
    type=types.Type.STRING,

    enum=[
        "RUN",
        "PAUSE",
        "FAST"
    ]
)


# ------------------------------------------------------
# TOOL DEFINITIONS
# ------------------------------------------------------

TOOLS = types.Tool(

    function_declarations=[

        # --------------------------------------------------
        # Conveyor Control
        # --------------------------------------------------

        types.FunctionDeclaration(

            name="start_conveyor",

            description=(
                "Start conveyor system."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={
                    "conveyor": _CONVEYOR_PARAM
                },

                required=["conveyor"]
            )
        ),

        types.FunctionDeclaration(

            name="stop_conveyor",

            description=(
                "Stop conveyor system."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={
                    "conveyor": _CONVEYOR_PARAM
                },

                required=["conveyor"]
            )
        ),

        # --------------------------------------------------
        # Production Modes
        # --------------------------------------------------

        types.FunctionDeclaration(

            name="set_production_mode",

            description=(
                "Configure intelligent "
                "factory production mode."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={
                    "mode": _MODE_PARAM
                },

                required=["mode"]
            )
        ),

        # --------------------------------------------------
        # Robot Allocation
        # --------------------------------------------------

        types.FunctionDeclaration(

            name="enable_arm",

            description=(
                "Enable a robot arm."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={
                    "arm": _ARM_PARAM
                },

                required=["arm"]
            )
        ),

        types.FunctionDeclaration(

            name="disable_arm",

            description=(
                "Disable a robot arm."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={
                    "arm": _ARM_PARAM
                },

                required=["arm"]
            )
        ),

        # --------------------------------------------------
        # Auto Balancing
        # --------------------------------------------------

        types.FunctionDeclaration(

            name="toggle_auto_balance",

            description=(
                "Enable or disable "
                "automatic load balancing."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={

                    "enabled": types.Schema(
                        type=types.Type.BOOLEAN
                    )
                },

                required=["enabled"]
            )
        ),

        # --------------------------------------------------
        # Simulation Control
        # --------------------------------------------------

        types.FunctionDeclaration(

            name="set_simulation_mode",

            description=(
                "Control Webots simulation."
            ),

            parameters=types.Schema(

                type=types.Type.OBJECT,

                properties={
                    "mode": _SIM_PARAM
                },

                required=["mode"]
            )
        )
    ]
)


# ------------------------------------------------------
# TCP HELPERS
# ------------------------------------------------------

def _drain(sock):

    try:

        while True:

            if not sock.recv(4096):
                break

    except OSError:
        pass


def connect_coordinator():

    s = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    s.connect(
        (
            COORDINATOR_HOST,
            COORDINATOR_PORT
        )
    )

    s.sendall(
        b"REGISTER UI\n"
    )

    threading.Thread(
        target=_drain,
        args=(s,),
        daemon=True
    ).start()

    return s


def send_tcp(sock, cmd):

    print(f"[TCP] {cmd}")

    sock.sendall(
        f"{cmd}\n".encode()
    )


# ------------------------------------------------------
# FUNCTION DISPATCH
# ------------------------------------------------------

def execute_function_call(
    sock,
    name,
    args
):

    if name == "start_conveyor":

        conveyor = args["conveyor"]

        send_tcp(
            sock,
            f"CONVEYOR_START {conveyor}"
        )

        return (
            f"Started {conveyor} conveyor."
        )

    elif name == "stop_conveyor":

        conveyor = args["conveyor"]

        send_tcp(
            sock,
            f"CONVEYOR_STOP {conveyor}"
        )

        return (
            f"Stopped {conveyor} conveyor."
        )

    elif name == "set_production_mode":

        mode = args["mode"]

        send_tcp(
            sock,
            f"SET_MODE {mode}"
        )

        return (
            f"Production mode changed "
            f"to {mode}."
        )

    elif name == "enable_arm":

        arm = args["arm"]

        send_tcp(
            sock,
            f"ENABLE_ARM {arm}"
        )

        return (
            f"{arm} enabled."
        )

    elif name == "disable_arm":

        arm = args["arm"]

        send_tcp(
            sock,
            f"DISABLE_ARM {arm}"
        )

        return (
            f"{arm} disabled."
        )

    elif name == "toggle_auto_balance":

        enabled = args["enabled"]

        cmd = (
            "AUTO_BALANCE ON"
            if enabled
            else "AUTO_BALANCE OFF"
        )

        send_tcp(sock, cmd)

        return (
            "Automatic load balancing "
            + (
                "enabled."
                if enabled
                else "disabled."
            )
        )

    elif name == "set_simulation_mode":

        mode = args["mode"]

        send_tcp(
            sock,
            f"CONTROL {mode}"
        )

        return (
            f"Simulation mode set "
            f"to {mode}."
        )

    return (
        f"Unknown operation: {name}"
    )


# ------------------------------------------------------
# MAIN
# ------------------------------------------------------

def main():

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        sys.exit(
            "GEMINI_API_KEY "
            "not set."
        )

    client = genai.Client(
        api_key=api_key
    )

    print(
        f"Connecting to coordinator at "
        f"{COORDINATOR_HOST}:"
        f"{COORDINATOR_PORT}"
    )

    try:

        sock = connect_coordinator()

    except OSError as exc:

        sys.exit(
            f"Could not connect: {exc}"
        )

    print("\nConnected.\n")

    print("Example prompts:")
    print("----------------------------------")
    print("Start can conveyor")
    print("Start fruit conveyor")
    print("Stop fruit conveyor")
    print("Run balanced production")
    print("Prioritize fruit handling")
    print("Run low power mode")
    print("Run high capacity mode")
    print("Enable automatic balancing")
    print("Disable UR10e")
    print("Pause simulation")
    print("----------------------------------\n")

    try:

        while True:

            try:

                user_input = (
                    input("> ")
                    .strip()
                )

            except EOFError:
                break

            if not user_input:
                continue

            response = client.models.generate_content(

                model=GEMINI_MODEL,

                contents=user_input,

                config=types.GenerateContentConfig(
                    tools=[TOOLS]
                )
            )

            part = (
                response.candidates[0]
                .content.parts[0]
            )

            if part.function_call:

                fn = part.function_call

                result = execute_function_call(
                    sock,
                    fn.name,
                    dict(fn.args)
                )

                print(
                    f"[ACTION] {result}"
                )

            else:

                print(
                    f"[Gemini] "
                    f"{part.text}"
                )

    except KeyboardInterrupt:
        pass

    finally:

        sock.close()

        print("\nDisconnected.")


if __name__ == "__main__":

    main()