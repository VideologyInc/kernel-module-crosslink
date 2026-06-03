#!/usr/bin/env python3

"""

File:   get_v4l2_linuxpy.py

2026.0602.  Use linuxpy (aka old name v4l2py) package to get camera v4l2 parameter controls.

By:			jye@videologyinc.com

"""

import argparse
import json

from linuxpy.video.device import Device, IntegerControl, BooleanControl, MenuControl

def show_control_status(device: str) -> None:
    with Device(device) as cam:
        # Group controls by class
        class_controls = {}
        classes = {}
        for control in cam.controls.values():
            classes[control.control_class.id] = control.control_class
            control_ids = class_controls.setdefault(control.control_class.id, [])
            control_ids.append(control)

        print("Showing current status of all controls ...\n")
        print(f"*** {cam.info.card} ***")

        for control_class_id, controls in class_controls.items():
            control_class = classes[control_class_id]
            print(f"\n{control_class.name.decode().title()}\n")

            for ctrl in controls:
                print(f"0x{ctrl.id:08x}:", ctrl)
                if isinstance(ctrl, MenuControl):
                    for key, value in ctrl.items():
                        print(11 * " ", f" +-- {key}: {value}")

        print("")


def get_camera_controls(device: str):
    try:
        with Device(device) as cam:
            ctrl_dict = {}
            for ctrl in cam.controls.values():
                if isinstance(ctrl, IntegerControl):
                    ctrl_dict[ctrl.name] = ["Int", ctrl.value, ctrl.minimum, ctrl.maximum, ctrl.step, ctrl.default, str(ctrl.flags)]
                elif isinstance(ctrl, BooleanControl):
                    ctrl_dict[ctrl.name] = ["Bool", ctrl.value, ctrl.default, str(ctrl.flags)]
                elif isinstance(ctrl, MenuControl):
                    ctrl_menu = {}
                    for key, value in ctrl.items():
                        ctrl_menu[key] = value
                    ctrl_dict[ctrl.name] = ["Menu", ctrl.value, ctrl.default, ctrl_menu]

            return ctrl_dict
    except:
        return {}

    return {}

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Get Camera v4l2 parameter controls using linuxpy",
        prog="get_v4l2_linuxpy",
    )
    parser.add_argument(
        "-d", "--device", type=str, default="/dev/video0", help="camera device path"
    )
    parser.add_argument(
        "-o", "--output", type=str, default="cam_controls.json", help="Output camera controls json file"
    )

    args = parser.parse_args()

    # show_control_status(args.device)

    cam_paras = get_camera_controls(args.device)
    print(cam_paras)

    # Save to a jsonb file.
    if args.output !="":
        with open(args.output, "w") as f:
            json.dump(cam_paras, f, indent=4)


