"""

File:   get_camera_v4l2_paras.py

2026.0527.  Added core function to parse 'media-ctl -p' command outputs.

By:			jye@videologyinc.com

"""

import argparse
import json
import subprocess
import re
from pathlib import Path


# Camera driver names with extrac 'streams' line in media-ctl command outputs.
Driver_Streams_List = ["gs_ar0234", "crosslink", "flir_boson"]

# Run media-ctl command and get entities containing above 3 camera driver names.
# return dict of detected entities.
def parse_media_ctl(device=None):
    cmd = ['media-ctl', '-p']
    if device:
        cmd.extend(['-d', device])
    
    # Run the command and capture output
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"media-ctl failed: {result.stderr}")
    
    output = result.stdout
    topology = {
        'device_info': {},
        'entities': {}
    }
    
    # Regex patterns
    entity_regex = re.compile(r"entity\s+(\d+):\s+(\w+)")
    type_regex = re.compile(r"type\s+(.*?)\s+subtype\s+(.*?)\s+flags\s+(.*)")
    node_regex = re.compile(r"device node name\s+(.*)")
    pad_regex = re.compile(r"\s+pad(\d+):\s+(Sink|Source)")
    format_regex = re.compile(r"\[stream:(.*?)/(.*?) field:(.*?)\]")
    linkto_regex = re.compile(r"->\s+\"(.*?)\":(\d+)\s+\[(.*?)\]")
    linkfrom_regex = re.compile(r"<-\s+\"(.*?)\":(\d+)\s+\[(.*?)\]")

    current_entity_id = None
    
    for line in output.splitlines():
        # Parse Device Information Header
        if line.startswith("Media device information"):
            continue
        if "driver" in line or "model" in line:
            parts = line.strip().split(':', 1)
            if len(parts) == 2:
                topology['device_info'][parts[0].strip()] = parts[1].strip()

        # Parse Entities
        entity_match = entity_regex.search(line)
        if entity_match:
            current_entity_id = int(entity_match.group(1))
            name = entity_match.group(2).strip()

            # print(current_entity_id, name)

            if name not in Driver_Streams_List:
                current_entity_id = None
                continue
            topology['entities'][current_entity_id] = {
                'name': name,
                'pads': {},
            }
            continue
            
        if current_entity_id is not None:
            # Parse Entity details
            if "type" in line:
                t_match = type_regex.search(line)
                if t_match:
                    topology['entities'][current_entity_id]['type'] = t_match.group(1).strip()
                    topology['entities'][current_entity_id]['subtype'] = t_match.group(2).strip()
                    topology['entities'][current_entity_id]['flags'] = t_match.group(3).strip()
            
            elif "device node name" in line:
                n_match = node_regex.search(line)
                if n_match:
                    topology['entities'][current_entity_id]['device_node'] = n_match.group(1).strip()
            
            # Parse Pads
            elif "pad" in line:
                p_match = pad_regex.search(line)
                if p_match:
                    pad_id = int(p_match.group(1))
                    pad_type = p_match.group(2)
                    topology['entities'][current_entity_id]['pads'][pad_id] = {
                        'type': pad_type,
                        'link': {}
                    }
            
            # Parse Formats
            elif ("[stream:" in line) and (pad_id is not None):
                has_stream = 1
            # Parse Links
            elif ("->" in line) and (pad_id is not None) and (has_stream is not None):
                l_match = linkto_regex.search(line)
                if l_match:
                    topology['entities'][current_entity_id]['pads'][pad_id]['link'] = {
                        'target_entity': l_match.group(1),
                        'target_pad': int(l_match.group(2)),
                        'flags': l_match.group(3).split(',')
                    }
            elif ("<-" in line) and (pad_id is not None) and (has_stream is not None):
                l_match = linkfrom_regex.search(line)
                if l_match:
                    topology['entities'][current_entity_id]['pads'][pad_id]['link'] = {
                        'source_entity': l_match.group(1),
                        'source_pad': int(l_match.group(2)),
                        'flags': l_match.group(3).split(',')
                    }

    for key, val in topology['entities'].items():
        for kp in list(val['pads'].keys()):
            if val['pads'][kp]['link']=={}:
                val['pads'].pop(kp)

    return topology


# Run v4l2-ctl --list-devices-ext to parse output as device dict.
def get_v4l2_devices():
    # Run the bash command and capture the output
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                                capture_output=True, text=True, check=True)
        output = result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print("Error executing v4l2-ctl. Is v4l-utils installed?")
        return {}

    devices = {}
    current_device = None

    # Process the output line by line
    for line in output.splitlines():
        # Strip trailing spaces and ignore empty lines
        stripped_line = line.strip()
        if not stripped_line:
            continue
            
        # Detect device header (does not start with /dev)
        if not stripped_line.startswith('/dev/'):
            # Remove bus info in parentheses if present, e.g., "(usb-0000:00:14.0-2)"
            current_device = re.sub(r'\s*\(usb-.*?\)', '', stripped_line).strip()
            devices[current_device] = []
        # Detect device nodes (starts with /dev/video or similar)
        elif current_device and stripped_line.startswith('/dev/'):
            devices[current_device].append(stripped_line)

    return devices

# Given device dict, detect all /dev/media? nodes and output their list
def get_media_list(device_dict):
    media_list = []
    for camera_name, nodes in device_dict.items():
        if "/dev/media" in nodes[0]:
            media_list.append(nodes[0])
    
    return media_list

# Given detected entities, extract camera path and subdev path with v4l2 controls.
def extract_media_subdev(topo):
    ret_list = []
    for key, val in topo["entities"].items():
        # print(val)
        name = val["name"]
        mipi = val["pads"][0]["link"]["target_entity"]
        mipi_csi = "csi0" if "csi2.0" in mipi else "csi1"
        mipi_path = Path("/dev/video-isi-" + mipi_csi)
        if mipi_path.exists():
            mipi_str = str(mipi_path) 
            subdev = val["device_node"]
            ret_list.append((name, mipi_str, subdev))
    
    return ret_list

# Given input device dict, extract its subdev with corresponding csi list.
def extract_v4l2_subdev(device_dict):
    ret_list = []

    for camera_name, nodes in device_dict.items():
        if "csi" in camera_name:
            name = "vvcam_isp"
            matches = re.search(r'csi\d+', camera_name)
            mipi = matches.group()
            mipi_path = Path("/dev/video-isp-" + mipi)
            if mipi_path.exists():
                mipi_str = str(mipi_path) 
                subdev = nodes[0]
                ret_list.append((name, mipi_str, subdev))

    return ret_list

# Run both media-ctl and v4l2-ctl commands to get valid (name, mipi path, subdev path) list 
def get_v4l2_subdev(show=False):
    # Run v4l2-ctl --list-devices command
    device_mapping = get_v4l2_devices()
    media_list = get_media_list(device_mapping)

    full_subdev_list = []
    # Run media-ctl command on each /dev/media? media device.
    for media in media_list:
        parsed_topology = parse_media_ctl(media)
        if show:
            print(json.dumps(parsed_topology, indent=4))

        subdev_list = extract_media_subdev(parsed_topology)

        # extend subdev list
        full_subdev_list.extend(subdev_list)

        if show:
            for camera_name, nodes in device_mapping.items():
                print(f"Camera: {camera_name}")
                print(f"  Nodes: {', '.join(nodes)}\n")

    v4l2_subdev_list = extract_v4l2_subdev(device_mapping)
    # Also extend list from v4l2 command.
    full_subdev_list.extend(v4l2_subdev_list)

    return full_subdev_list

# Given mipi_str and subdev list, detect match and return or "".
def mipi_to_subdev(mipi_str, subdev_list):
    for sub in subdev_list:
        if mipi_str == sub[1]:
            return sub[2]
    return ""

# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get camera v4l2 parameters using media-ct command outputs",
        prog="get_camera_v4l2_paras",
    )
    parser.add_argument(
        "-t", "--topology", type=int, default=0, help="Show topology. Default = 0 (off)"
    )
    args = parser.parse_args()

    v4l2_subdev_list = get_v4l2_subdev(args.topology)

    print(v4l2_subdev_list)
    