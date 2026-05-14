# Combined Webots world: Universal Robots + Epson SCARA T6

This folder is a **single Webots project** that starts from **`ure_standalone`** (Universal Robots can-grasping demo) and adds the **fruit-sorting SCARA cell** from **`scaraT6_standalone`**, arranged so the two work areas **do not overlap** in the horizontal plane.

---

## What is merged

| Source | World file (reference) | In this project |
|--------|------------------------|-----------------|
| `ure_standalone` | `worlds/ure.wbt` | Used **as-is** at the origin (UR arms, conveyors, cans, factory props). |
| `scaraT6_standalone` | `webots_scara_t6_standalone/worlds/industrial_example.wbt` | Only the **SCARA-specific** geometry (floor patch, SCARA robot, fruit belt, walls, fruit) is included—**not** the duplicate office furniture that already exists in the UR world. |

The SCARA cell is wrapped in a `Pose` with **`translation 12 0 0`** (12 m along **+X**). That places it beside the UR layout:

- The UR sample floor is **`17 × 5` m** centered near the origin, so the UR scene occupies roughly **x ∈ [−8.5, 8.5]** (and similar extent along **Z**).
- The SCARA floor patch (**`7.5 × 5` m**, offset locally by **0.75** in X) then sits near **x ∈ [9, 16.5]**, leaving a clear gap between the two islands.

If you add more equipment on the UR side, increase the **12** in `worlds/ure_plus_scara.wbt` (search for the comment *“translated +12 m”*) so the cells stay separated.

---

## One-shot: dashboard + Webots

From the **repository root**:

```bash
export WEBOTS_HOME="/Applications/Webots.app"   # adjust if needed
./start_all.sh
```

This builds C controllers, starts the **WebSocket→TCP bridge** and **Vite** dev server, opens **http://127.0.0.1:5173**, then launches **`combined_world/worlds/ure_plus_scara.wbt`**. The React UI connects to the coordinator (via the bridge), shows **CMD / LOG** traffic in **four columns** (UR3e, UR5e, UR10e, ScaraT6), and can send **CONTROL RUN / PAUSE / FAST** to the Webots supervisor. **`UR_SPEED_MULT`** (default **10**) shortens UR phase waits in the coordinator; **`SCARA_SPEED_DIV`** (default **10**) runs the SCARA script tick **N** times less often per simulation step (slower SCARA sequence). **`SIM_SLOWDOWN`** (default **1**) optionally stretches wall-clock time after each `wb_robot_step` in all controllers.

Environment (optional): **`COORDINATOR_TCP_PORT`** (default **9099**), **`FRONTEND_WS_PORT`** (default **8765**), **`COORDINATOR_HOST`**, **`SIM_SLOWDOWN`** (≥ 1), **`UR_SPEED_MULT`** (≥ 1, default **10**), **`SCARA_SPEED_DIV`** (≥ 1, default **10**).

---

## Open and run (manual)

1. Install **Webots R2025a** (or the version you use for these samples).
2. Build controllers:

   ```bash
   export WEBOTS_HOME="/Applications/Webots.app"
   cd combined_world/controllers
   make clean
   make release
   ```

3. In Webots: **File → Open World…** → `combined_world/worlds/ure_plus_scara.wbt`, then run the simulation.

4. Optional dashboard: in another terminal, from repo root:

   ```bash
   cd frontend && npm install && node server.mjs &
   npm run dev
   ```

   Open **http://127.0.0.1:5173** (bridge defaults: TCP **9099**, WebSocket **8765**).

---

## Controllers in this project

| Controller | Role |
|------------|------|
| **`coordinator`** | C — **Supervisor** TCP server (**`REGISTER …`**, **`CMD`**, **`TELEM`**, UI **`CONTROL *`**). **UR phase timing:** waits **`ceil(8 / UR_SPEED_MULT)`** steps between UR phase edges (default **UR_SPEED_MULT=10** → **1** step vs legacy **8**). **SCARA timing:** `scara_coordinator_step()` runs every **`SCARA_SPEED_DIV`** supervisor steps (default **10** → SCARA script index advances **10×** slower in simulation time). Optional **`SIM_SLOWDOWN`** wall stretch after each `wb_robot_step`. |
| **`ur_arm_executor`** | C — one process per UR; **TCP client** to the coordinator (same port); sends **`TELEM`** each step; applies **`CMD …`** lines. **`controllerArgs`**: `[ speed, UR3e | UR5e | UR10e ]`. Same **`SIM_SLOWDOWN`** post-step delay. |
| **`conveyor_belt`** | C — belt motion; uses the same **`SIM_SLOWDOWN`** delay after each step so conveyors do not outrun the UR/SCARA stack. |
| **`scara_food_industry`** | Python — **TCP client** to the coordinator; receives `SCARA_*` command lines (no console echo of received lines). Same **`SIM_SLOWDOWN`** delay after each `supervisor.step`. |

The legacy **`ure_can_grasper`** binary is no longer used by `ure_plus_scara.wbt`; it remains in the tree only if you want the old single-controller workflow elsewhere.

---

## PROTOs and network

The `.wbt` file uses **`EXTERNPROTO`** URLs pointing at the Webots **R2025a** branch on GitHub. The first run may need network access to cache PROTOs (same behavior as the parent projects).

---

## Repository layout

This repo keeps **`scaraT6_standalone`** unchanged. **`combined_world`** is the derived project. **`ure_standalone`** in this repo has been updated in parallel (same **socket coordinator** + **`ur_arm_executor`**) so you can open **`ure_standalone/worlds/ure.wbt`** with the same build (no SCARA cell in that world).

The **React dashboard** lives in **`frontend/`** (`npm run dev`, `node server.mjs` for the WebSocket bridge).
