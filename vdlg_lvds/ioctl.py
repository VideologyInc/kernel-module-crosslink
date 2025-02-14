#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# ioctl definitions to interact with Videology LVDS2MIPI kernel module.
#

import ctypes

# Define the IOCTL commands
LVDS_CMD_SERIAL_SEND_TX     = 0x7601
LVDS_CMD_SERIAL_RECV_RX     = 0x7602
LVDS_CMD_SERIAL_RX_CNT      = 0x7603
LVDS_CMD_SERIAL_BAUD        = 0x7604
LVDS_CMD_GET_FW_VERSION     = 0x7605
LVDS_CMD_GET_LVDS_STATUS    = 0x7606
LVDS_CMD_GET_UART_STATUS    = 0x7607
LVDS_CMD_GET_FRAME_PERIOD   = 0x7608
LVDS_CMD_GET_PIXEL_FREQ     = 0x7609
LVDS_CMD_GET_LINE_COUNT     = 0x760A
LVDS_CMD_GET_COLM_COUNT     = 0x760B
LVDS_CMD_SET_POWERDOWN      = 0x760C
LVDS_CMD_FORCE_HVSYNC_INV   = 0x760D
LVDS_CMD_GET_REGS			= 0x760E
LVDS_CMD_SET_REGS			= 0x760F
LVDS_CMD_SERIAL_RX_LAST	    = 0x7610

# Define the struct
class LvdsIoctlSerial(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_uint32),
        ("data", ctypes.c_uint8 * 64),
    ]

