# Baseline — known simulation issues

This file marks a **git baseline** revision used to reproduce and track the following behaviors.

## 1. UR cans not picked up

Under the current **socket coordinator** + **`ur_arm_executor`** stack (and default timing env such as **`UR_SPEED_MULT`**), **cans are not picked up reliably** on the UR side: grasps may miss, phases may advance before the arm has settled, or telemetry-driven state may not align with the physical can motion.

## 2. ScaraT6 — very fast motion, high command rate

**ScaraT6** can appear to move through the fruit / merge / sort sequence **very quickly**, with **many coordinator commands** in a short wall-clock or simulation window (depending on **`SCARA_SPEED_DIV`**, **`SIM_SLOWDOWN`**, and Webots run mode). The high-level **`SCARA_*`** stream can feel rushed relative to a comfortable demo pace.

---

Use `git log -1 --oneline` and this file at `HEAD` as the reference for “baseline with these issues called out.” Adjust **`UR_SPEED_MULT`**, **`SCARA_SPEED_DIV`**, and **`SIM_SLOWDOWN`** (see `combined_world/README.md` and `start_all.sh`) when iterating on fixes.
