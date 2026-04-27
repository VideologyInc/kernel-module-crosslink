#!/usr/bin/env python3

"""

File:   detect_imx_live.py

2026.0408.  Added json file containing user-specified 'WINDOW NAME' : 'values' parameters to load and parse as dict to set by vvget.
2026.0406.  Detect one imx camera live stream on/off status using lsof and let user choose to Reset AEC and/or AWB with optimized values.

By:			jye@videologyinc.com

"""

import argparse
import time
import subprocess
import json
import jc
import sys
import time

from vdlg_lvds.detect_cameras_live import detect_camera_type
from vdlg_lvds.read_imx_json import read_imx, default_imx, AEC_LIST, AWB_LIST, parse_vvget_output, save_dict_txt


# Given jc parsed lsof output list of dict, check command containing isp_media (imx is available) or gst-launc (imx stream on).
# return (bool, bool) of (camera on, stream on)
def check_lsof_output(data_list_dict):
    camera_on = False
    stream_on = False
    for d in data_list_dict:
        if d["command"] == "isp_media":
            camera_on = True
        elif d["command"] == "gst-launc":
            stream_on = True

    return camera_on, stream_on


# Call lsof to detect camera stream on/off
def detect_imx(device_path):
    # Run the command
    cmd = f"lsof {device_path}"
    try:
        # output = subprocess.check_output(cmd, shell=True)
        # Get the raw output
        cmd_output = subprocess.check_output(cmd, shell=True, text=True)

        # Parse into a list of dictionaries
        data_list_dict = jc.parse("lsof", cmd_output)
        status = check_lsof_output(data_list_dict)
        # print(data)
        return status

    except subprocess.CalledProcessError:
        print("Device not found or error running lsof")
        return False, False


def restart_go2rtc():

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

# Turn off
def vvget_off(camera_id, feature_name):
    # 1. Turn off
    cmd1 = f"vvget {camera_id} '{feature_name} On/Off' 0"
    result = subprocess.run(
        cmd1,
        shell=True,
        capture_output=True,
        text=True,
        check=True,
    )

# Reset
def vvget_reset(camera_id, feature_name):
    # 2. Reset
    cmd1 = f"vvget {camera_id} '{feature_name} Reset' 1"
    result = subprocess.run(
        cmd1,
        shell=True,
        capture_output=True,
        text=True,
        check=True,
    )

# Turn AEC or AWB off, and reset.
def vvget_set_feature_off(camera_id, feature_name):
    # AEC or AWB correct values must follow steps: off, reset, set values; or reset, off, set values.
    # AEC OFF => AEC Reset
    if feature_name=="AEC":
        # Keep trying to turn AEC off until get 0 ;-)
        while True:
            cmd2 = f"vvget {camera_id} '{feature_name} On/Off'"
            result2 = subprocess.run(
                cmd2,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
            )
            valstr = parse_vvget_output(result2.stdout, feature_name+":")
            if "0" in valstr:
                break
            vvget_off(camera_id, feature_name)
    else:
    # AWB Reset => AWB OFF
        vvget_off(camera_id, feature_name)
        vvget_reset(camera_id, feature_name)
        vvget_off(camera_id, feature_name)

        # 2.2. Get bool status
        cmd2 = f"vvget {camera_id} '{feature_name} On/Off'"
        result2 = subprocess.run(
            cmd2,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )
    return parse_vvget_output(result2.stdout, feature_name+":")


# Set values by para dict.
def vvget_set_feature_values(camera_id, imx_para, aec, awb):

    for key, value in imx_para.items():
        if (key in AEC_LIST) and (not aec):
            continue
        if (key in AWB_LIST) and (not awb):
            continue
        # 3.1. Set value first
        cmd3 = f"vvget {camera_id} '{key}' '{value}'"
        result3 = subprocess.run(
            cmd3,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )

    message = ""
    for key, value in imx_para.items():
        if (key in AEC_LIST) and (not aec):
            continue
        if (key in AWB_LIST) and (not awb):
            continue
        # 3.2 Get value
        cmd3 = f"vvget {camera_id} '{key}'"
        result3 = subprocess.run(
            cmd3,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )
        message += parse_vvget_output(result3.stdout, ":")
    return message


# Set values by para dict => txt file.
def vvget_set_feature_txt(camera_id, txt_name):
    tmp_values_name = "imx_para_values.txt"
    cmd = f"vvget {camera_id} -i {txt_name} -o {tmp_values_name}"
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_vvget_output(result.stdout, ":")


def turn_off_aec_awb(device_path, txt_name, aec):
    dlen = len("/dev/video")
    # Do nothing if device path is not /dev/video?
    if len(device_path) <= dlen:
        return

    id = int(device_path[dlen:])

    try:
        # AEC off.
        print("========================================================")
        if aec:
            print("vvget AEC Status: ", vvget_set_feature_off(id, "AEC"))
        """
        # AWB off.
        if awb:
            print("vvget AWB Status: ", vvget_set_feature_off(id, "AWB"))
        """

        # print(vvget_set_feature_values(id, imx_para, aec, awb))
        # Now use new version of vvget to set multiple features by one subprocess call.
        print(vvget_set_feature_txt(id, txt_name))
        print("========================================================")

    except Exception as e:
        print(f"vvget failed: {e}")


# Given initial camera status, use infinite loopt to check camera stream status every few seconds.
def monitor_cameras_loop(
    device_path, camera_status, stream_status, interval, txt_name, aec
):

    print(f"Camera {camera_status} and stream {stream_status}")
    try:
        while True:
            current_camera_status, current_stream_status = detect_imx(device_path)
            if (
                current_camera_status == camera_status
                and current_stream_status == stream_status
            ):
                time.sleep(interval)
                continue
            elif current_camera_status != camera_status:
                print("Camera status changed: ", current_camera_status)
                # update status for next time check.
                camera_status = current_camera_status
                stream_status = current_stream_status
                # Camera connection changed: restart go2rtc service.
                restart_go2rtc()
            elif current_stream_status != stream_status:
                print("Stream status changed: ", current_stream_status)
                # update status for next time check.
                stream_status = current_stream_status
                # Off => On change: need to turn off AEC and AWB
                if current_stream_status:
                    turn_off_aec_awb(device_path, txt_name, aec)

            # sleep a few seconds for next check.
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nLoop stopped by user.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Detect imx camera stream on/off",
        prog="detect_imx_live",
    )
    parser.add_argument(
        "-d", "--device", type=str, default="/dev/video0", help="camera device path"
    )
    parser.add_argument(
        "--aec",
        type=int,
        default=1,
        help="Turn Off and Reset AEC with optimized exposure time value.",
    )
    parser.add_argument(
        "--awb",
        type=int,
        default=1,
        help="Turn Off and Reset AWB with optimized gain input values.",
    )
    parser.add_argument(
        "-j",
        "--json",
        type=str,
        default="",
        help="Read Window Name : values parameter dict from a json file.",
    )

    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=0.2,
        help="Interval in seconds to check camera status.",
    )

    args = parser.parse_args()

    # detect camera type to ensure it is imx
    camera_type, cam_path = detect_camera_type(args.device)
    print(f"Camera at {args.device} is {camera_type}, devicetree path = {cam_path}")
    if "imx" not in camera_type:
        print(f"Camera at {args.device} is not a Sony imx camera.")
        sys.exit()

    imx_para = (
        read_imx(args.json) if args.json.endswith(".json") else default_imx(camera_type)
    )
    # Save para dict to txt file for new vvget to read it and set features all at once.
    txt_name = "imx_para_tmp.txt"
    save_dict_txt(imx_para, txt_name, args.aec or args.awb)

    # Get current camera status
    camera_status, stream_status = detect_imx(args.device)
    print(f"Initial camera status: camera {camera_status}, stream {stream_status}")

    monitor_cameras_loop(
        args.device,
        camera_status,
        stream_status,
        args.interval,
        txt_name,
        args.aec
    )
