#!/usr/bin/env python3

"""

File:   v4l2_detect_formats.py

2026.0227.  Detect formats by parsing from v4l2 command v4l2-ctl -d /dev/video0 --list-formats-ext outputs.
2026.0302.  Added Zoom Block camera format full list (resolution, fps, formats) from Visca commands.

By:			jye@videologyinc.com

"""

import argparse
import time
import subprocess
import re
import json
import glob
import copy
import math

# Camera key words in device tree and its regular names
camera_dict = {
    "AR0234": "ar0234",
    "lvds2mipi": "zoomblock",
    "flir": "boson",
    "imx900": "imx900",
    "imx678": "imx678",
    "imx662": "imx662",
}

Format_Exclude_List = ["NM12", "YUV4", "YM24"]
Desc_Exclude_List = ["Bayer", "JPEG", "10-bit", "12-bit", "5-6-5"]
Fourcc_Dict = {"YUYV" : "YUY2", "NV12" : "NV12",
    "GREY" : "GRAY8", "Y16 " : "GRAY16_LE", "RGB3" : "RGB", 
    "BGR3" : "BGR", "XR24" : "BGRx", "AR24" : "BGRA"
    }

# Use system chosen device tree name to detect camera type:   ar0234, imx, boson, or ZoomBlock "lvds"
def detect_camera_type(device="/dev/video0"):
    if "/dev/video" in device:
        # Extract camera id
        dev_str_len = len("/dev/video")
        id = int(device[dev_str_len:])
        # Find matching device tree name id.
        cam_list = glob.iglob("/proc/device-tree/chosen/overlays/cam*")
        cam_name = "cam" + str(id)
        for s in cam_list:
            if cam_name in s:
                for key, val in camera_dict.items():
                    if key in s:
                        return val

    # Cannot find: return default
    return "ar0234"    


def parse_v4l2_formats(device="/dev/video0"):
    # Run the command
    cmd = f"v4l2-ctl -d {device} --list-formats-ext"
    try:
        output = subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        print("Device not found or error running v4l2-ctl")
        return []

    formats = []
    current_format = None

    # Regex patterns
    fmt_pattern = re.compile(r"\[\d+\]:\s+'(.+?)'\s+\((.+)\)")
    size_pattern = re.compile(r"Size:\s+Discrete\s+(\d+)x(\d+)")
    fps_pattern = re.compile(r"Interval:\s+Discrete\s+.*?\s+\(([\d\.]+)\s+fps\)")

    for line in output.splitlines():
        line = line.strip()

        # Match Format line
        fmt_match = fmt_pattern.search(line)
        if fmt_match:
            current_format = {
                "pixelformat": fmt_match.group(1),
                "description": fmt_match.group(2),
                "sizes": [],
            }
            formats.append(current_format)
            continue

        # Match Size line
        size_match = size_pattern.search(line)
        if size_match and current_format is not None:
            current_size = {
                "width": int(size_match.group(1)),
                "height": int(size_match.group(2)),
                "fps": [],
            }
            current_format["sizes"].append(current_size)
            continue

        # Match FPS line
        fps_match = fps_pattern.search(line)
        if fps_match and current_format is not None:
            current_format["sizes"][-1]["fps"].append(float(fps_match.group(1)))

    return formats

# Given format list from above, filter out 3 big conditions:
# empty sizes, some special formats, and description containing Bayer, JPEG, 10-bit or 12-bit.
def formats_filter_out_unwanted(format_list):
    format_list_filtered = []
    for fdict in format_list:
        if fdict["pixelformat"] in Format_Exclude_List:
            continue
        if len(fdict["sizes"])==0:
            continue
        if any(sub in fdict["description"] for sub in Desc_Exclude_List):
            continue
        format_list_filtered.append(fdict)
    
    return format_list_filtered

# For Zoom Block cameras connecte to LVDS port, add fps = 25,30,50,60 and 1920 x 1080, plus 1280 x 720 to the list.
def add_formats_lvds(format_list):
    formats = {"YUYV" : "YUYV 4:2:2", "NV12" : "Y/UV 4:2:0"}
    resolution_list = [(1920,1080), (1280, 720)]
    fps_list = [25.0, 30.0, 50.0, 60.0]
    # Add all combinations 2 x 2 x 4 = 16 total possible formats
    sample = {
        "pixelformat": "YUYV",
        "description": "YUYV 4:2:2",
        "sizes": [
            {
                "width": 1920,
                "height": 1080,
                "fps": [25.0]
            }
        ]
    }

    format_list = []
    for f in formats.keys():
        for w,h in resolution_list:
            for fps in fps_list:

                print(f, w, h, fps)
                one = copy.deepcopy(sample)
                one["pixelformat"] = f
                one["description"] = formats[f]
                one["sizes"][0]["width"] = w
                one["sizes"][0]["height"] = h
                one["sizes"][0]["fps"][0] = fps
                format_list.append(one)

    return format_list


def fourcc_to_gst(fourcc_str):
    if fourcc_str in Fourcc_Dict:
        return Fourcc_Dict[fourcc_str]
    else:
        return Fourcc_Dict["NV12"]

def v4l2_format_mapto_gst(format_list):
    for fdict in format_list:
        print(fdict["pixelformat"], "=>", fourcc_to_gst(fdict["pixelformat"]))


# Given one format dict, return its gstreamer string.
def v4l2_format_to_gst(format_dict):
    s_list = []
    for sz in format_dict["sizes"]:
        w = sz["width"]
        h = sz["height"]
        fps = int(math.ceil(sz["fps"][0]))
        f = format_dict["pixelformat"]
        f_gst = fourcc_to_gst(f)
        s = f"video/x-raw,width={w},height={h},framerate={fps}/1,format={f_gst} ! videoconvert"
        t = (w, h, f"fps={fps},format={f_gst}", s)
        s_list.append(t)

    return s_list

# Given camera device path, return supported gstreamer str list.
def camera_to_gst_list(device):
    camera_type = detect_camera_type(device)

    camera_formats = formats_filter_out_unwanted(parse_v4l2_formats(device))
    # Add full resolution and framerate support for ZoomBlock (from visca commands)
    print(camera_type)
    if "zoomblock"==camera_type:
        print("Create new format list for ZoomBlock cameras.")
        camera_formats = add_formats_lvds(camera_formats)

    # print(json.dumps(camera_formats, indent=2))

    info_list = []
    for fd in camera_formats:
        s_list = v4l2_format_to_gst(fd)
        info_list += s_list

    return info_list

# Example Usage
if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Detect camera formats by parsing v4l2 command outputs",
        prog="v4l2_detect_formats",
    )
    parser.add_argument(
        "-d", "--device", type=str, default="/dev/video0", help="camera device path"
    )

    args = parser.parse_args()

    info_list = camera_to_gst_list(args.device)

    for info in info_list:
        print(info)
    