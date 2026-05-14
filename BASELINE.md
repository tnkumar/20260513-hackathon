# Baseline — known simulation issues

This file marks **git baseline** revisions used to reproduce and track behaviors. Use `git describe --tags --always` or the tag name with `git log -1` at that revision.

---

## Tag `baseline/ur5e-ur10e-gripping` (current)

**Comment:** **UR5e and UR10e are now gripping correctly** (Robotiq grasp aligned with `example_code/ure_can_grasper.c`, per-step grasp/release re-apply in `ur_arm_executor`, coordinator min grasp dwell).

At this baseline, the remaining callouts below are mostly **SCARA pacing** and any **residual UR edge cases** (friction, conveyor speed, distance threshold) rather than systematic UR5e/UR10e misses.

---

## Earlier baseline: `baseline/known-issues`

### 1. UR cans not picked up (largely mitigated at `baseline/ur5e-ur10e-gripping`)

Under the **socket coordinator** + **`ur_arm_executor`** stack, cans could miss if phases advanced before the gripper closed. Mitigations: **minimum 8-step** grasp/release dwell in the coordinator, grasp targets and finger handling matching **`example_code/ure_can_grasper.c`**, and **re-applying** `GRASPING_CAN` / `RELEASING_CAN` each executor step while that command is active.

### 2. ScaraT6 — very fast motion, high command rate

**ScaraT6** can appear to move through the fruit / merge / sort sequence **very quickly**, with **many coordinator commands** in a short wall-clock or simulation window (depending on **`SCARA_SPEED_DIV`**, **`SIM_SLOWDOWN`**, and Webots run mode). The high-level **`SCARA_*`** stream can feel rushed relative to a comfortable demo pace.

---

Adjust **`UR_SPEED_MULT`**, **`SCARA_SPEED_DIV`**, and **`SIM_SLOWDOWN`** (see `combined_world/README.md` and `start_all.sh`) when iterating on fixes.
