#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# ioctl based access to I2C <-> Serial adapter of the FPGA.
#

from time import sleep, time_ns
import argparse
import threading
import fcntl
import ctypes

# Define the struct
class LvdsIoctlSerial(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_uint32),
        ("data", ctypes.c_uint8 * 64),
    ]

# # define UART status bits
# LVDS_UART_STAT_BUSY_TX       = 0b0010_0000
# LVDS_UART_STAT_BUSY_RX       = 0b0001_0000
# LVDS_UART_STAT_DATA_FULLTX   = 0b0000_1000
# LVDS_UART_STAT_DATA_EMPTYTX  = 0b0000_0100
# LVDS_UART_STAT_DATA_FULLRX   = 0b0000_0010
# LVDS_UART_STAT_DATA_EMPTYRX  = 0b0000_0001

# Define the IOCTL commands
LVDS_CMD_SERIAL_SEND_TX    = 0x7601
LVDS_CMD_SERIAL_RECV_RX    = 0x7602
LVDS_CMD_SERIAL_RX_CNT     = 0x7603
LVDS_CMD_SERIAL_BAUD       = 0x7604

class LvdsSerial():
    def __init__(self, dev_path, start_wait_ms=100, stop_wait_ms=25, baud=9600):
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
    # get argparse for dev, baudrate, data
    parser = argparse.ArgumentParser(prog='Lvds_Visca')
    parser.epilog = example_text
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.add_argument('-d', '--dev', type=str, default="/dev/v4l-subdev1", help='device path')
    parser.add_argument('-t', '--timeout', type=int, default=None, help='read timeout to wait for RX data')
    parser.add_argument('data', type=str, help='data to send, as hex string')
    args = parser.parse_args()
    data = bytearray.fromhex(args.data)
    crtvx = LvdsSerial(args.dev)

    data = crtvx.transceive(data, start_wait_ms=args.timeout)

    print(data.hex())

if __name__ == "__main__":
    main()