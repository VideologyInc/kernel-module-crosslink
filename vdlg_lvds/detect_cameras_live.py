#!/usr/bin/env python3

"""

File:   detect_cameras_live.py

2026.0306.  Detect camera live connection using device tree and camera path.

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
import os
from pathlib import Path
import io
import warnings

warnings.filterwarnings('ignore')
os.environ['OPENCV_LOG_LEVEL'] = 'OFF'
os.environ['GST_DEBUG'] = '*:0' 

import cv2

# Maximum camera index with /dev/video* to detect.
MAX_CAMERA_ID = 3

# Camera key words in device tree and its regular names
camera_dict = {
    "AR0234": "ar0234",
    "lvds2mipi": "zoomblock",
    "flir": "boson",
    "imx900": "imx900",
    "imx678": "imx678",
    "imx662": "imx662",
    "usb" : "usb",
}

# Check camera on/off using OpenCV VideoCapture().
def check_camera(device_path="/dev/video0"):
    cap = cv2.VideoCapture(device_path)
    
    # Check if the camera is opened successfully
    if cap.isOpened():
        ret, frame = cap.read()
        cap.release()
        if ret:
            return True
        else:
            return False
    else:
    # print("Camera is OFF or not accessible.")
        return False

# Check whether camera path is available.
def is_device_available(device="/dev/video0"):
    if os.path.exists(device):
        return True
    else:
        return False

# Given camera name in device tree folder, find its real device path.
def devicetree_cam_to_path(camfile):
    cam = os.path.basename(camfile)
    camlist = re.findall(r"cam(\d+)-(\w+)", cam)
    if len(camlist)==0:
        return ""
    idn, typ = camlist[0]
    devlist = glob.glob(f"/dev/video*csi{idn}")
    if len(devlist)==0:
        return ""
    vdev = devlist[0]
    cam_real_path = Path(vdev).resolve()
    return str(cam_real_path)
    

# Use system chosen device tree name to detect camera type:   ar0234, imx, boson, or ZoomBlock "lvds".
# Return tuple of (camera name, device tree name), ("unknown", "unknown") or ("", "").
def detect_camera_type(device="/dev/video0"):
    if is_device_available(device) and ("/dev/video" in device):
        # Find matching device tree name id.
        cam_list = glob.iglob("/proc/device-tree/chosen/overlays/cam*")
        for s in cam_list:
            cam_real_path = devicetree_cam_to_path(s)
            if cam_real_path == device:
                # print(s, " => ", cam_real_path)
                for key, val in camera_dict.items():
                    if key in s:
                        return val, s

        # Cannot find in device tree, try usb device path in "/dev/v4l/by-path/"
        usb_list = glob.glob("/dev/v4l/by-path/*")
        for s in usb_list:
            # Only check usb camera path
            if "usb" not in s:
                continue
            cam_real_path = str(Path(s).resolve())
            if cam_real_path == device:
                # Found in usb device path
                for key, val in camera_dict.items():
                    if key in s:
                        return val, s

        # Device is available but cannot find: return unknown
        return "unknown", "unknown"
    else:
        return "", ""


# Detect cameras with /dev/video* and return dict with camera_path : (camera_name, devicetree_name, on/off).
def detect_cameras():
    camera_status = {}
    prefix = "/dev/video"
    for id in range(0, MAX_CAMERA_ID):
        camera_path = prefix + str(id)
        camera_name, devicetree_name = detect_camera_type(camera_path)
        if camera_name != "":
            # Check camera on/off using OpenCV.
            is_on = check_camera(camera_path)
            camera_status[camera_path] = (camera_name, devicetree_name, is_on)

    return camera_status


def restart_go2rtc():
    try:
        result = subprocess.run(["systemctl", "restart", "go2rtc.service"], capture_output=True, text=True, check=True)
        print("Restart go2rtc: ", result.stdout)
    except Exception as e:
        print(f"Restart go2rtc failed: {e}")


# Given initial camera status dict, use infinite loopt to check camera status every few seconds.
def monitor_cameras_loop(camera_status, interval):
    nitems = len(camera_status)
    while True:
        current_camera_status = detect_cameras()
        if current_camera_status == camera_status:
            print("Camera status unchanged")
        else:
            print("Camera status changed: ", current_camera_status)
            camera_status = current_camera_status
            new_items = len(camera_status)
            if nitems != new_items:
                # Camera connection changed: restart go2rtc service.
                nitems = new_items
                restart_go2rtc()

        time.sleep(interval)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Detect cameras live",
        prog="detect_cameras_live",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default="5",
        help="Interval in seconds to check cameras",
    )

    args = parser.parse_args()

    # Get current camera status
    camera_status = detect_cameras()
    print(camera_status)

    monitor_cameras_loop(camera_status, args.interval)
