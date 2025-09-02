#!/usr/bin/env python3

__author__ = "Matteo Golinelli"
__copyright__ = "Copyright (C) 2025 Matteo Golinelli"
__license__ = "MIT"

import subprocess
import traceback
import argparse
import logging
import asyncio
import shutil
import signal
import shlex
import yaml
import json
import time
import sys
import os


class EventListener:
    '''
    This class is copy-pasted from the hyprland-py project.
    All rights reserved to the original author.
    The original code can be found here:
    https://github.com/hyprland-community/hyprland-py/blob/master/hyprland/socket.py

    Class to listen to events from hyprland
    The events are received from a unix socket
    '''
    async def start(self):
        reader, _ = await asyncio.open_unix_connection(f'{os.getenv('XDG_RUNTIME_DIR')}/hypr/{os.getenv('HYPRLAND_INSTANCE_SIGNATURE')}/.socket2.sock')
        yield 'connect'

        buffer = b''
        while True:
            new_data = await reader.read(8192)
            if not new_data:
                break
            buffer += new_data
            while b'\n' in buffer:
                data, buffer = buffer.split(b'\n', 1)
                yield data.decode('utf-8')

class Monitor:
    '''
    Class to represent a monitor
    The monitor is represented by its id and name
    The id is the name of the monitor from `hyprctl monitors`
    The name is the name of the monitor from the configuration file
    The monitor can have a resolution, position, scale and align
    The monitor can also have monitors above, below, left and right
    '''
    def __init__(self, id, name):
        self.id     = id
        self.name   = name
        # above, below, left, right are the name of the monitors that are positioned relative to this monitor
        self.above  = None
        self.below  = None
        self.left   = None
        self.right  = None
        self.resolution = None
        self.position = None
        self.align = 'center'
        self.scale  = 1
        self.extra  = None

    def set_above(self, above):
        '''
        Set the monitor above this monitor
        :param above: monitor above this monitor
        :type above: str
        :return: None
        '''
        self.above = above

    def set_below(self, below):
        '''
        Set the monitor below this monitor
        :param below: monitor below this monitor
        :type below: str
        :return: None
        '''
        self.below = below

    def set_left(self, left):
        '''
        Set the monitor to the left of this monitor
        :param left: monitor to the left of this monitor
        :type left: str
        :return: None
        '''
        self.left = left

    def set_right(self, right):
        '''
        Set the monitor to the right of this monitor
        :param right: monitor to the right of this monitor
        :type right: str
        :return: None
        '''
        self.right = right

    def set_resolution(self, resolution):
        '''
        Set the resolution of the monitor
        :param resolution: resolution of the monitor
        :type resolution: str
        :return: None
        '''
        self.resolution = resolution

    def set_position(self, position):
        '''
        Set the position of the monitor
        :param position: position of the monitor in format "XxY"
        :type position: str
        :return: None
        '''
        self.position = position

    def set_align(self, align):
        '''
        Set the alignment of the monitor relative to adjacent monitors
        :param align: alignment value ('left', 'right', 'top', 'bottom', 'center')
        :type align: str
        :return: None
        '''
        if align not in ['left', 'right', 'top', 'bottom', 'center']:
            logging.error(f'Invalid align value {align} for monitor {self.name}')
            sys.exit(1)
        self.align = align

    def set_scale(self, scale):
        '''
        Set the scaling factor of the monitor
        :param scale: scaling factor
        :type scale: float
        :return: None
        '''
        self.scale = scale

    def set_extra(self, extra):
        '''
        Set the extra options for the monitor
        :param extra: extra options
        :type extra: str
        :return: None
        '''
        self.extra = extra

    def __str__(self):
        monitor_str = f'Monitor {self.name} ({self.id})\n'
        monitor_str += f'  Resolution: {self.resolution}\n'
        monitor_str += f'  Scale: {self.scale}\n'
        monitor_str += f'  Position: {self.position}\n'
        if self.above:
            monitor_str += f'  Above: {self.above}\n'
        if self.below:
            monitor_str += f'  Below: {self.below}\n'
        if self.left:
            monitor_str += f'  Left: {self.left}\n'
        if self.right:
            monitor_str += f'  Right: {self.right}\n'
        if self.align:
            monitor_str += f'  Align: {self.align}\n'
        return monitor_str

def get_monitors():
    '''
    Get the monitors from hyprctl
    :return: list of monitors
    '''
    result = subprocess.run(['hyprctl', 'monitors', 'all', '-j'], capture_output=True, text=True)
    return json.loads(result.stdout)

def kill_existing_instances():
    '''
    Kill other running instances of this script (exclude current PID).
    Uses pgrep -f to find processes whose command line contains the script name,
    sends SIGTERM, waits briefly, then SIGKILL for any remaining PIDs.
    '''
    try:
        script_name = os.path.basename(__file__)
    except Exception:
        script_name = 'hmonitors.py'

    try:
        p = subprocess.run(['pgrep', '-f', script_name], capture_output=True, text=True)
        if p.returncode != 0 or not p.stdout:
            return
        pids = [int(x) for x in p.stdout.split()]
    except Exception:
        logging.debug('Could not query running processes to kill existing instances')
        return

    current = os.getpid()
    # Send SIGTERM
    for pid in pids:
        if pid == current:
            continue
        try:
            logging.debug(f'Sending SIGTERM to existing hmonitors instance {pid}')
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except Exception:
            logging.debug(f'Failed to send SIGTERM to {pid}')

    # Wait for processes to exit, then SIGKILL any remaining
    for _ in range(6):
        alive = []
        for pid in pids:
            if pid == current:
                continue
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except OSError:
                pass
        if not alive:
            return
        time.sleep(0.5)

    for pid in alive:
        try:
            logging.debug(f'Sending SIGKILL to existing hmonitors instance {pid}')
            os.kill(pid, signal.SIGKILL)
        except Exception:
            logging.debug(f'Failed to send SIGKILL to {pid}')

def load_config(config_file):
    '''
    Load the configuration file
    :param config_file: path to the configuration file
    :type config_file: str
    :return: configuration file
    :rtype: dict
    '''
    with open(config_file, 'r') as stream:
        return yaml.safe_load(stream)

def select_monitors(monitors, match):
    '''
    Select the monitors that match the given key-value pairs
    :param monitors: list of monitors
    :type monitors: list
    :param match: list of dictionaries with the key-value pairs to match
    :type match: list
    :return: list of monitors that match the given key-value pairs
    :rtype: list
    '''
    selected_monitor = []

    for monitor in monitors:
        match_found = True
        for match_element in match:
            key, value = list(match_element.items())[0]
            if key not in monitor or monitor[key] != value:
                match_found = False
                break

        if match_found:
            selected_monitor.append(monitor)

    if len(selected_monitor) > 1:
        logging.error(f'Multiple monitors found for {match}. Please provide a more specific match')
        sys.exit(1)

    return selected_monitor[0] if selected_monitor else None

def get_upmost_leftmost_monitor(monitors):
    '''
    Get the upmost leftmost monitor
    :param monitors: list of monitors
    :type monitors: list
    :return: upmost leftmost monitor
    :rtype: Monitor
    '''
    for monitor in monitors:
        if monitors[monitor].position == 'auto':
            continue
        if not monitors[monitor].above and not monitors[monitor].left:
            return monitors[monitor]

def set_position(monitors, monitor, position='0x0'):
    '''
    Set the position of the monitor relative to
    another monitor in a recursive way.
    :param monitors: list of monitors
    :type monitors: list
    :param monitor: monitor to set the position for
    :type monitor: Monitor
    :param position: position of the monitor
    :type position: str
    :return: None
    '''
    monitor.position = position

    # If the monitor has a monitor on the right, set the position of the right monitor
    if monitor.right:
        right_monitor = monitors[monitor.right]

        next_position_x = int(monitor.resolution.split('x')[0])
        if right_monitor.align == 'top':
            next_position_y = int(position.split('x')[1])
        elif right_monitor.align == 'bottom':
            next_position_y = int(monitor.resolution.split('x')[1]) - int(right_monitor.resolution.split('x')[1])
        else:
            if right_monitor.align != 'center':
                logging.error(f'Invalid align value for monitor {right_monitor.name}, using default center')
            next_position_y = (int(monitor.resolution.split('x')[1]) - int(right_monitor.resolution.split('x')[1])) // 2

        next_position = f'{next_position_x}x{next_position_y}'

        set_position(monitors, right_monitor, next_position)

    # If the monitor has a monitor below, set the position of the below monitor
    if monitor.below:
        below_monitor = monitors[monitor.below]

        if below_monitor.align == 'left':
            next_position_x = int(position.split('x')[0])
        elif below_monitor.align == 'right':
            next_position_x = int(monitor.resolution.split('x')[0]) - int(below_monitor.resolution.split('x')[0])
        else:
            if below_monitor.align != 'center':
                logging.error(f'Invalid align value for monitor {below_monitor.name}, using default center')
            next_position_x = (int(monitor.resolution.split('x')[0]) - int(below_monitor.resolution.split('x')[0])) // 2

        next_position_y = int(monitor.resolution.split('x')[1])

        next_position = f'{next_position_x}x{next_position_y}'

        set_position(monitors, below_monitor, next_position)

    # No need for the above and left monitors since we start from the upmost leftmost monitor

def apply_configuration(monitor):
    '''
    Apply the configuration for the monitor
    using hyprctl
    :param monitor: monitor to apply the configuration for
    :type monitor: Monitor
    :return: None
    '''
    command = f'hyprctl keyword monitor {monitor.id},{monitor.resolution},'
    command += f'{monitor.position},{monitor.scale}'
    if monitor.extra:
        command += f',{monitor.extra}'

    subprocess.run(shlex.split(command), capture_output=True, text=True)
    logging.debug(f'Applied configuration for monitor {monitor.name} ({monitor.id}): {command}')


def send_notification(summary, title='Hmonitors'):
    '''
    Send a desktop notification using notify-send if available.
    '''
    try:
        # Only attempt if notify-send is present on the system
        if shutil.which('notify-send') is None:
            logging.debug('notify-send not found, skipping desktop notification')
            return
        subprocess.run(['notify-send', title, summary], check=False)
    except Exception:
        logging.debug('Failed to send notification', exc_info=True)

def setup_monitors(config_file):
    '''
    Setup the monitors
    :return: None
    '''
    config = load_config(config_file)

    hyprctl_monitors = get_monitors()
    monitors = {}

    # Match the monitors with the configuration
    for monitor in config['monitors']:
        if 'match' in config['monitors'][monitor]:
            match = config['monitors'][monitor]['match']
            selected_monitor = select_monitors(hyprctl_monitors, match)
        else:
            logging.error(f'No match found for {monitor}')
            sys.exit(1)

        if not selected_monitor:
            logging.info(f'No monitor found for {monitor}')
            continue

        # Initialize the monitor
        # The name of the monitor from `hyprctl monitors` is used as the id
        resolution = f'{selected_monitor["width"]}x{selected_monitor["height"]}'
        monitors[monitor] = Monitor(selected_monitor['name'], monitor)
        monitors[monitor].set_resolution(resolution)
        if 'align' in config['monitors'][monitor]:
            monitors[monitor].set_align(config['monitors'][monitor]['align'])

    # Parse the configuration and organize the monitors
    for monitor in config['monitors']:
        if monitor not in monitors:
            continue

        monitor_config = config['monitors'][monitor]

        if 'position' in monitor_config:
            position = monitor_config['position']
            relative_to = position.split()[1]
            if relative_to not in monitors:
                logging.error(f'Monitor {relative_to} not found')
                sys.exit(1)
            # TODO: check for conflicts
            if 'above' in position:
                monitors[monitor].set_below(relative_to)
                monitors[relative_to].set_above(monitor)
            if 'below' in position:
                monitors[monitor].set_above(relative_to)
                monitors[relative_to].set_below(monitor)
            if 'left-of' in position:
                monitors[monitor].set_right(relative_to)
                monitors[relative_to].set_left(monitor)
            if 'right-of' in position:
                monitors[monitor].set_left(relative_to)
                monitors[relative_to].set_right(monitor)
            if 'same-as' in position:
                monitors[monitor].set_position('auto')
                monitors[monitor].set_resolution('preferred')
                monitors[monitor].set_scale('1')
                monitors[monitor].set_extra(f'mirror,{monitors[relative_to].id}')

        if 'scale' in monitor_config:
            monitors[monitor].set_scale(monitor_config['scale'])

    # We need to find the upmost and leftmost monitor
    upmost_leftmost_monitor = get_upmost_leftmost_monitor(monitors)

    # Set the position of the monitors
    # Start from the upmost leftmost monitor
    set_position(monitors, upmost_leftmost_monitor)

    # Get the min x and y of the position of the monitors
    min_x = min([int(monitors[monitor].position.split('x')[0]) for monitor in monitors if monitors[monitor].position != 'auto'])
    min_y = min([int(monitors[monitor].position.split('x')[1]) for monitor in monitors if monitors[monitor].position != 'auto'])

    # If one of the monitors has a negative position, we need to shift all the monitors
    # Since negative positions are not allowed
    # We potentially need to shift all the monitors to the right and down
    if min_x < 0:
        for monitor in monitors:
            x = int(monitors[monitor].position.split('x')[0]) - min_x
            y = int(monitors[monitor].position.split('x')[1])
            monitors[monitor].position = f'{x}x{y}'
    if min_y < 0:
        for monitor in monitors:
            x = int(monitors[monitor].position.split('x')[0])
            y = int(monitors[monitor].position.split('x')[1]) - min_y
            monitors[monitor].position = f'{x}x{y}'

    # Apply the configuration
    applied = []
    for monitor in monitors:
        apply_configuration(monitors[monitor])
        applied.append(monitors[monitor].name)

    # Send a desktop notification summarizing the applied configuration
    if applied:
        send_notification(f'Applied configuration for monitors: {", ".join(applied)}')

async def main():
    parser = argparse.ArgumentParser(description='Monitor configuration')
    parser.add_argument('-c', '--config', help='Config file', default='~/.config/hmonitors/config.yaml')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--hook', action='store_true', help='Listen to hyprland events and apply the configuration')
    parser.add_argument('-w', '--watch', action='store_true', help='Watch config file for changes and re-apply configuration. On by default when hook mode is enabled')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    # Ensure only one instance runs at a time
    kill_existing_instances()

    config_file = os.path.expanduser(args.config)
    if not os.path.exists(config_file):
        logging.error(f'Config file {config_file} does not exist')
        sys.exit(1)

    watch_enabled = args.watch or args.hook  # Enable watching if requested or when in hook mode

    async def monitor_config_changes(config_path, poll_interval=1.0):
        '''
        Async polling watcher for the config file. When a change in mtime
        is detected, call setup_monitors to apply the new configuration.
        '''
        try:
            last_mtime = os.path.getmtime(config_path)
        except Exception:
            last_mtime = None

        while True:
            await asyncio.sleep(poll_interval)
            try:
                mtime = os.path.getmtime(config_path)
            except Exception:
                # The file might have been deleted or is temporarily unavailable
                continue
            if last_mtime is None:
                last_mtime = mtime
                continue
            if mtime != last_mtime:
                logging.info(f'Config file {config_path} changed, re-applying configuration')
                try:
                    # Run the (blocking) setup in a thread
                    await asyncio.to_thread(setup_monitors, config_path)
                except Exception as e:
                    logging.error(f'Failed to re-apply configuration: {e}')
                    logging.debug(traceback.format_exc())
                last_mtime = mtime

    if args.hook:
        logging.info('Running in hook mode, listening to events')
        # Setup the monitors once
        setup_monitors(config_file)

        # Start the config watcher if requested
        watcher_task = None
        if watch_enabled:
            watcher_task = asyncio.create_task(monitor_config_changes(config_file))

        # Listen to events concurrently with the watcher
        listener = EventListener()

        async def event_loop():
            async for event in listener.start():
                if any(event_name in event for event_name in ['monitoradded', 'monitorremoved']):
                    # Run the potentially blocking setup in a thread
                    await asyncio.to_thread(setup_monitors, config_file)

        # Run both tasks and wait until they finish
        try:
            if watcher_task:
                await asyncio.gather(event_loop(), watcher_task)
            else:
                await event_loop()
        except asyncio.CancelledError:
            pass
    else:
        # Non-hook mode: apply once, then optionally watch for changes
        setup_monitors(config_file)
        if watch_enabled:
            # Run watcher forever
            await monitor_config_changes(config_file)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('Exiting...')
        sys.exit(0)
    except Exception as e:
        logging.error(f'Error: {e}')
        logging.debug(traceback.format_exc())
        sys.exit(1)
