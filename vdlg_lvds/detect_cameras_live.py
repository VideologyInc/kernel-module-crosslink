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
import glob
import os
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["GST_DEBUG"] = "*:0"

import cv2

# Maximum camera index with /dev/video* to detect.
MAX_CAMERA_ID = 10
""" Maximum camera index with /dev/video* to detect. """

# Camera key words in device tree and its regular names
# Currently supports 4 camera types:
# global shutter = AR0234   => ar0234
# ZoomBlock = lvds2mipi     => zoomblock
# Boson = flir or boson     => boson
# imx series = imx          => imx
camera_dict = {
    "AR0234": "ar0234",
    "lvds2mipi": "zoomblock",
    "flir": "boson",
    "imx900": "imx900",
    "imx678": "imx678",
    "imx662": "imx662",
    "usb": "usb",
}
""" Camera key words in device tree and its regular names. """


# Check camera on/off using OpenCV VideoCapture().
def check_camera(device_path="/dev/video0"):
    """
    Given input camera device path, check camera on/off using OpenCV VideoCapture().

    Arguments:
    device_path  --  Camera device path such as /dev/video0, etc.

    Returns:
    bool --  True if camera is ready to start streaming. False if camera is busy or cannot open.

    """

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
    """
    Given input camera device path, check whether camera path is available.

    Arguments:
    device_path  --  Camera device path such as /dev/video0, etc.

    Returns:
    bool --  True if camera path exists. False if it does not and cannot be opened.

    """

    if os.path.exists(device):
        return True
    else:
        return False


# Given camera name in device tree folder, find its real device path.
def devicetree_cam_to_path(camfile):
    """
    Given camera name in device tree folder, find its real device path as return.

    Arguments:
    camfile  --  Camera device tree full path such as /proc/device-tree/chosen/overlays/cam*.

    Returns:
    str --  Camera device path like /dev/video-isp-csi0, etc.

    """

    cam = os.path.basename(camfile)
    camlist = re.findall(r"cam(\d+)-(\w+)", cam)
    if len(camlist) == 0:
        return ""
    idn, typ = camlist[0]
    devlist = glob.glob(f"/dev/video*csi{idn}")
    if len(devlist) == 0:
        return ""
    vdev = devlist[0]
    cam_real_path = Path(vdev).resolve()
    return str(cam_real_path)


# Use system chosen device tree name to detect camera type:   ar0234, imx, boson, or ZoomBlock "lvds".
# Return tuple of (camera name, device tree name), ("unknown", "unknown") or ("", "").
def detect_camera_type(device="/dev/video0"):
    """
    This is reverse function of devicetree_cam_to_path().
    Given camera device path such as /dev/video0, find its device tree path or v4l path for usb cameras as return.

    Arguments:
    device  --  Camera device path such as /dev/video0.

    Returns:
    (str, str) --  Camera normal name in dict, and its matching device tree name or v4l by-path name for usb cameras. Or (empty, empty) if not found.

    """

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
    """
    Detect cameras with /dev/video* and return dict with camera_path : (camera_name, devicetree_name, on/off).

    Arguments:

    Returns:
    dict[str: (str,str,bool)] --  dict of key = camera name, value = camera status tuple = (camera name, device tree or v4l name, is ready for streaming).

    """

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
    """
    Restart go2rtc.service running subprocess.run() and outputs messages.

    Arguments:

    Returns:

    """

    try:
        result = subprocess.run(
            ["systemctl", "restart", "go2rtc.service"],
            capture_output=True,
            text=True,
            check=True,
        )
        print("Restart go2rtc: ", result.stdout)
    except Exception as e:
        print(f"Restart go2rtc failed: {e}")


# Given initial camera status dict, use infinite loopt to check camera status every few seconds.
def monitor_cameras_loop(camera_status, interval):
    """
    Given initial camera status dict, use infinite loop to check camera status every few seconds.
    Restart go2rtc.service if camera number of items in ths dict changed.

    Arguments:
    camera_status  --   dict of camera status from function detect_cameras().
    interval       --   Interval in seconds to sleep between each camera status check. = 5 seconds by default.

    Returns:

    Notes:
    If usb camera is connected or dis-connected, camera number of items will increase or decrease.
    go2rtc.service will restart and camera config yaml is re-generated, which will make webRTC port 1984 GUI stream list change accordingly.

    """

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
    """
    detect_camera_live.py.

    With user input argument of interval gap in seconds, the program loops to check camera status regularly and restart go2rtc.service if number of items changed.

    """

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
