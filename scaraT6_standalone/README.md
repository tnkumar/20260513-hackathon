# SCARA T6 Webots standalone project helper

This folder contains a script that copies Cyberbotics’ **Epson SCARA T6** food-industry sample and the **conveyor_belt** controller from your local Webots installation into a single project directory. After copying, Webots runs those controllers from your tree instead of under `/Applications/Webots.app/Contents/projects/...`.

## Requirements

- **Webots** installed at the default macOS location: `/Applications/Webots.app` (R2025a matches the sample world).
- `rsync` (preinstalled on macOS).

## What gets copied

| Source | Destination |
|--------|-------------|
| `.../robots/epson/scara_t6/worlds`, `webots.yaml` | `<DEST>/` |
| `.../robots/epson/scara_t6/controllers/*` | `<DEST>/controllers/` |
| `.../objects/factory/conveyors/controllers/conveyor_belt/` | `<DEST>/controllers/conveyor_belt/` |

The world file still uses `EXTERNPROTO` URLs pointing at GitHub (`raw.githubusercontent.com/...`). That is unrelated to the app-bundle controller path; protos load over the network unless you vendor them separately.

## Usage

From this directory:

```bash
chmod +x scripts/copy_webots_scara_standalone.sh
./scripts/copy_webots_scara_standalone.sh
```

Optional: pass a custom destination as the first argument:

```bash
./scripts/copy_webots_scara_standalone.sh /path/to/my_scara_project
```

Default destination (no argument): `webots_scara_t6_standalone/` inside this repo (so the copy stays in the workspace). To place the project on the Desktop or elsewhere, pass an absolute path:

```bash
./scripts/copy_webots_scara_standalone.sh "$HOME/Desktop/scaraT6_webots_standalone"
```

## After copying

1. Open Webots.
2. **File → Open World…** and choose `industrial_example.wbt` inside your destination, e.g. `webots_scara_t6_standalone/worlds/` when using the default path.
3. In the console, confirm `conveyor_belt` starts from `<DEST>/controllers/conveyor_belt/`, not from `/Applications/Webots.app/...`.

## Limitations

- You still need **Webots installed** to simulate: the Python `controller` module and physics are part of Webots. This script only removes **project-file** dependence on paths inside the Webots.app bundle for the bundled controllers.
- The copied `conveyor_belt` binary is built for your platform; other machines may need to rebuild from the copied sources in Webots.

## License

The copied sample and conveyor code remain under Cyberbotics’ licensing (see files in the Webots distribution). This README and script are helper material for your local workflow.
