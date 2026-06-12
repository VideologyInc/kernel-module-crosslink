#!/usr/bin/env python3

"""

File:   zoomblock_settings.py

2026.0612.  Created to call lvds set_res.py and get_res.py to set / get resolution + fps of a zoomblock camera.

By:			jye@videologyinc.com

"""

from contextlib import redirect_stdout
import io

import argparse
import glob
import json
import math

from vdlg_lvds.serial import LvdsSerial
from vdlg_lvds.get_res import get_resolution
from vdlg_lvds.set_res import detect_camera_brand, set_resolution

from vdlg_lvds.detect_cameras_live import detect_camera_type, restart_go2rtc

zoomblock_settings_dict = {
    "720p25" : "1280 x 720, fps=25",
    "720p30" : "1280 x 720, fps=30",
    "720p50" : "1280 x 720, fps=50",
    "720p60" : "1280 x 720, fps=60",
    "1080p25" : "1920 x 1080, fps=25",
    "1080p30" : "1920 x 1080, fps=30",
    "1080p50" : "1920 x 1080, fps=50",
    "1080p60" : "1920 x 1080, fps=60"
}

# Given get_res() output string such as 1920 x 1080 @ 59.9, split it as v4l2 parsed struct as input of detect formats function. 
def get_res_string_to_v4l2_struct(str_with_at):
    res_list = str_with_at.split()
    # [0] = w, [2] = h, [4] = fps
    width = int(res_list[0])
    height = int(res_list[2])
    fps = math.ceil(float(res_list[4]))

    one = {
        "pixelformat": "YUYV",
        "description": "YUYV 4:2:2",
        "sizes": [{"width": width, "height": height, "fps": [fps]}],
    }
    two = {
        "pixelformat": "NV12",
        "description": "YUYV 4:2:0",
        "sizes": [{"width": width, "height": height, "fps": [fps]}],
    }

    return [one, two]

# Connection to detect_formats functions
def get_formats_lvds():
    lvds_device, current = zoomblock_get_resolution()

    if current !="":
        return get_res_string_to_v4l2_struct(current)
    else:
        return []
    

def show_zoomblock_settings():
    print("Available resolution + fps strings to set:")
    print(json.dumps(zoomblock_settings_dict, indent=4))


# Check whether there is lvds in /dev/links and get current resolution.
def zoomblock_get_resolution():
    lvds_devs = glob.glob("/dev/links/lvds*")
    default_lvds = lvds_devs[0] if lvds_devs else "/dev/v4l-subdev1"

    f = io.StringIO()
    with redirect_stdout(f):
        get_resolution(default_lvds)
    output_string = f.getvalue()
    return default_lvds, output_string

# Given camera device path and resolution str, set it calling set_resolution function.
def zoomblock_set_resolution(device, resolution):

    try:
        f = io.StringIO()
        with redirect_stdout(f):
            serial_device = LvdsSerial(device)
            brand = detect_camera_brand(serial_device)
            set_resolution(serial_device, resolution, brand)
    except:
        # Maybe wrong format string
        return "", ""

    # check and return real current resolution
    return zoomblock_get_resolution()


# Example Usage
if __name__ == "__main__":
    """
    zoomblock_settings.py main() function.

    With user input argument of camera device path, and setting string, this program calls visca get_res and set_res to set correct resolution + fps.

    """

    parser = argparse.ArgumentParser(
        description="ZoomBlock camera set / get setting",
        prog="zoomblock_settings",
    )
    parser.add_argument(
        "-d", "--device", type=str, default="/dev/video0", help="camera device path"
    )

    parser.add_argument(
        "-r",
        "--resolution",
        type=str,
        default="",
        help="Resolution and fps to set. String format is 1080p60 or 720p25 etc.",
    )

    parser.add_argument(
        "-s", "--show", type=int, default=0, help="Show available setting list to set. Default = 0."
    )

    parser.add_argument(
        "-g", "--go2rtc", type=int, default=0, help="Restart go2rtc after successful new resolution set. Default = 0."
    )

    parser.add_argument(
        "-i", "--input", type=str, default="", help="Input json file with camera setting to set."
    )
    parser.add_argument(
        "-o", "--output", type=str, default="", help="Output json file with current valid camera setting."
    )

    args = parser.parse_args()

    camera_name, tree_name = detect_camera_type(args.device)
    if camera_name != "zoomblock":
        print(f"{args.device} is not a zoomblock camera.")
        exit(1)

    if args.show:
        show_zoomblock_settings()

    lvds_device, current = zoomblock_get_resolution()
    print("Current resolution and framerate is:", current)

    if args.resolution != "":
        lvds_device, new_resolution = zoomblock_set_resolution(lvds_device, args.resolution)
        if new_resolution !="":
            print("New resolution and framerate is:", new_resolution)
            if args.go2rtc:
                restart_go2rtc()
        else:
            print(f"{args.resolution} is not supported.")