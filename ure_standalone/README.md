# Webots Universal Robots sample — standalone copy

These steps copy the Webots **Universal Robots** sample off the application bundle and add the **`conveyor_belt`** controller next to your project so conveyors do not rely on another folder under `/Applications/Webots.app`.

You still need **Webots installed** to run the simulation and to **compile** controllers (the Makefile includes Webots headers from `WEBOTS_HOME`).

---

## Quick start (script)

From this directory, run:

```bash
chmod +x setup_webots_ure_standalone.sh
./setup_webots_ure_standalone.sh
```

By default the script uses **this folder** as the project root (`PROJECT_DIR` defaults to the directory that contains the script). To use another directory:

```bash
mkdir -p "$HOME/Desktop/universal_robots"
PROJECT_DIR="$HOME/Desktop/universal_robots" ./setup_webots_ure_standalone.sh
```

If Webots is not at `/Applications/Webots.app`:

```bash
WEBOTS_HOME="/path/to/Webots.app" ./setup_webots_ure_standalone.sh
```

Then open **`$PROJECT_DIR/worlds/ure.wbt`** in Webots and run the simulation.

---

## 0. Choose a project directory (manual steps)

Set where the world and controllers will live. All commands below use this variable.

**Example A — use this folder (`ure_standalone`) as the project root**:

```bash
export PROJECT_DIR="$HOME/Desktop/ure_standalone"
```

**Example B — a separate folder on the Desktop**:

```bash
export PROJECT_DIR="$HOME/Desktop/universal_robots"
mkdir -p "$PROJECT_DIR"
```

---

## To-do 1 — Copy the `universal_robots` sample

Use `cp` with `/.` so hidden files (for example `.ure.wbproj`) are included:

```bash
mkdir -p "$PROJECT_DIR"
cp -R "/Applications/Webots.app/Contents/projects/robots/universal_robots/." "$PROJECT_DIR/"
```

---

## To-do 2 — Copy the `conveyor_belt` controller

The `ure.wbt` world uses `ConveyorBelt` PROTOs that reference the controller name `conveyor_belt`. That controller is **not** in the `universal_robots` sample; it ships with the factory conveyors project. Copy it into **your** project’s `controllers` folder:

```bash
mkdir -p "$PROJECT_DIR/controllers"
cp -R \
  "/Applications/Webots.app/Contents/projects/objects/factory/conveyors/controllers/conveyor_belt" \
  "$PROJECT_DIR/controllers/"
```

---

## To-do 3 — Register `conveyor_belt` in the project Makefile

Edit **`$PROJECT_DIR/controllers/Makefile`**.

Change the `TARGETS` line from:

```makefile
TARGETS = ure_can_grasper.Makefile
```

to:

```makefile
TARGETS = ure_can_grasper.Makefile conveyor_belt.Makefile
```

Save the file.

---

## To-do 4 — Rebuild controllers and run in Webots

### Build from Terminal (macOS)

```bash
export WEBOTS_HOME="/Applications/Webots.app"
cd "$PROJECT_DIR/controllers"
make clean
make release
```

If `make release` is not available in your setup, use:

```bash
make clean
make
```

### Build from Webots

1. Start Webots.
2. **File → Open World…** and open **`$PROJECT_DIR/worlds/ure.wbt`**.
3. Use **Build → Build** (or rebuild controllers) so Webots compiles controllers in the current project.

### Verify

Run the simulation. You should see the UR arms and conveyors behave as in the original sample, and the console should not complain about a missing `conveyor_belt` controller.

---

## Notes

- **First run / PROTOs**: `ure.wbt` uses `EXTERNPROTO` URLs on GitHub. You need network the first time Webots fetches them (or a cached copy). That is separate from “controllers living outside the `.app` bundle.”
- **Architecture**: Rebuilding on your Mac avoids using a prebuilt binary from the bundle that might not match your CPU (for example Apple Silicon vs Intel).
