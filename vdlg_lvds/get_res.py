import argparse
from time import sleep
from vdlg_lvds.ioctl import *
import fcntl

def get_resolution(dev):
    ioctl_serial = LvdsIoctlSerial()
    with open(dev) as f:
        fcntl.ioctl(f, LVDS_CMD_GET_LINE_COUNT, ioctl_serial)
        vres = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_COLM_COUNT, ioctl_serial)
        hres = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_FRAME_PERIOD, ioctl_serial)
        frame_rate = 1000000.0 / ioctl_serial.len
        print(f"{hres} x {vres} @ {frame_rate:.1f}")

def main():
    parser = argparse.ArgumentParser(description="Get current LVDS camera resolution")
    parser.add_argument("-d", "--dev", type=str, default="/dev/v4l-subdev1", help="Device path")
    args = parser.parse_args()
    get_resolution(args.dev)

if __name__ == "__main__":
    main()
