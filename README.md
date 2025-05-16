# Hmonitors

Set up monitors in Hyprland using a YAML configuration file.

## How to Use

You can run this script once to setup your monitors with the following command:

```bash
python monitors.py -c config.yaml
```

Where `config.yaml` is the path to your configuration file.

If you want to run the script in the background and have it automatically update your monitors when they change, you can run it with the `--hook` flag:

```bash
python monitors.py --hook -c config.yaml &
```

You can enable verbose logging with the `-v` flag.

### Configuring Hmonitors

The configuration is done with a YAML file. The default location is `~/.config/hmonitors/config.yaml`.

The configuration includes a top-level key `monitors` which is a list of monitor configurations. Each monitor configuration is a dictionary with the following keys:

- `match`: A list of key-value pairs to match the monitor. The key is the name of the property to match, and the value is the value to match. The supported properties are all those that can be found in the output of the `hyprctl monitors -j` command. Some notable properties are:
  - `serial`: The serial number of the monitor. Allows to uniquely identify a monitor, but not all monitors report this value.
  - `width` and `height`: The width and height of the monitor in pixels. This is useful to match a monitor by its resolution.
  - `name`: The name of the output of the monitor (e.g., `DP-1`, `HDMI-1`, etc.).
- `position`: The position of the monitor relative to another monitor by name. This value is optional.
  - `left-of <monitor>`: The monitor is to the left of the specified monitor.
  - `right-of <monitor>`: The monitor is to the right of the specified monitor.
  - `above <monitor>`: The monitor is above the specified monitor.
  - `below <monitor>`: The monitor is below the specified monitor.
  - `same-as <monitor>`: The monitor mirrors the specified monitor.
- `align`: Align the monitors to the `center`, `left`, `right`, `top`, or `bottom` of the specified monitor. This value is optional and defaults to `center`.
- `resolution`: The resolution of the monitor. Defaults to `auto`.
- `refresh_rate`: The refresh rate of the monitor. Defaults to `auto`.
- `scale`: The scale of the monitor. Defaults to 1.
- `extra`: Extra arguments to pass to `hyprctl`. Can be used to change the monitor's rotation, mirror it, etc.

An example configuration file is placed in the `examples` directory.

## Why not Pyprland?

Pyprland's [monitors](https://hyprland-community.github.io/pyprland/monitors.html) plugin should do the same thing as this script, but 1) I discovered its existence after I wrote this script and 2) the documentation is unclear.
