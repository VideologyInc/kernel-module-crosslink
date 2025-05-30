#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# ioctl based access to I2C <-> Serial adapter of the FPGA.
#

from time import sleep, time_ns
import argparse
import threading
import fcntl
from vdlg_lvds.ioctl import *
import glob

class LvdsSerial():
    def __init__(self, dev_path, start_wait_ms=100, stop_wait_ms=120, baud=9600):
        self.lock = threading.Lock()
        self.dev = dev_path
        self.baud = baud
        self.bwms = start_wait_ms
        self.ewms = stop_wait_ms
        self.set_baud(self.baud)
        self.recv()        # clear RX fifo

    # Open the device file
    def send(self, data: bytes):
        ioctl_serial = LvdsIoctlSerial()
        ioctl_serial.len = len(data)
        ioctl_serial.data = (ctypes.c_uint8 * 64)(*data)
        # Call an IOCTL
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_SERIAL_SEND_TX, ioctl_serial)

    def recv(self, count:int=0):
        ioctl_serial = LvdsIoctlSerial()
        ioctl_serial.len = count
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_SERIAL_RECV_RX, ioctl_serial)
        return bytes(ioctl_serial.data[:ioctl_serial.len])

    def get_rx_count(self):
        ioctl_serial = LvdsIoctlSerial()
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_SERIAL_RX_CNT, ioctl_serial)
        return ioctl_serial.len

    def get_rx_last_byte(self):
        ioctl_serial = LvdsIoctlSerial()
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_SERIAL_RX_LAST, ioctl_serial)
        return ioctl_serial.len

    def get_uart_status(self):
        ioctl_serial = LvdsIoctlSerial()
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_GET_UART_STATUS, ioctl_serial)
        empty_rx = ioctl_serial.len & 0x1
        full_rx  = ioctl_serial.len & 0x2
        empty_tx = ioctl_serial.len & 0x4
        full_tx  = ioctl_serial.len & 0x8
        busy_rx  = ioctl_serial.len & 0x10
        busy_tx  = ioctl_serial.len & 0x20
        return empty_rx, full_rx, empty_tx, full_tx, busy_rx, busy_tx

    def get_baud(self):
        ioctl_serial = LvdsIoctlSerial()
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_SERIAL_BAUD, ioctl_serial)
        return ioctl_serial.len

    def set_baud(self, baud:int):
        ioctl_serial = LvdsIoctlSerial()
        ioctl_serial.len = baud
        with open(self.dev) as f:
            fcntl.ioctl(f, LVDS_CMD_SERIAL_BAUD, ioctl_serial)

    def wait_for_rx_stable(self, start_wait_ms, stop_wait_ms):
        start = time_ns()
        while self.get_rx_count() == 0:
            sleep(0.002)
            if time_ns() - start > start_wait_ms*1e6:
                return False
        byte_count = self.get_rx_count()
        start = time_ns()
        while time_ns() - start < stop_wait_ms*1e6:
            sleep(0.002)
            cnt = self.get_rx_count()
            if cnt != byte_count:
                byte_count = cnt
                start = time_ns()
        return True

    def transceive(self, data: bytes, count:int=0, start_wait_ms=None, stop_wait_ms=None):
        if start_wait_ms is None:
            start_wait_ms = self.bwms
        if stop_wait_ms is None:
            stop_wait_ms = self.ewms
        with self.lock:
            self.recv()
            self.send(data)
            self.wait_for_rx_stable(start_wait_ms, stop_wait_ms)
            data = self.recv(count)
        return data

example_text = '''
example:
    %(prog)s -d /dev/links/lvds2mipi_1 81090002FF
'''

def main():
    lvds_devs = glob.glob("/dev/links/lvds*")
    default_lvds = lvds_devs[0] if lvds_devs else "/dev/v4l-subdev1"
    # get argparse for dev, baudrate, data
    parser = argparse.ArgumentParser(prog='Lvds_Visca')
    parser.epilog = example_text
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.add_argument('-d', '--dev', type=str, default=default_lvds, help='device path')
    parser.add_argument('-t', '--timeout', type=int, default=None, help='read timeout to wait for RX data')
    parser.add_argument('data', type=str, help='data to send, as hex string')
    args = parser.parse_args()
    data = bytearray.fromhex(args.data)
    crtvx = LvdsSerial(args.dev)

    data = crtvx.transceive(data, start_wait_ms=args.timeout)

    print(data.hex())

if __name__ == "__main__":
    main()