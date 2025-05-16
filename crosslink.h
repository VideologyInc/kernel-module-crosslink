/* SPDX-License-Identifier: GPL-2.0 */

#ifndef CROSSLINK_H
#define CROSSLINK_H

#include <linux/i2c.h>
#include <media/v4l2-async.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-device.h>
#include <media/v4l2-event.h>
#include <media/v4l2-fwnode.h>
#include <media/v4l2-subdev.h>
#include <linux/tty.h>
#include <linux/tty_driver.h>
#include <linux/tty_flip.h>
#include <linux/pm_runtime.h>

#define MIN_HEIGHT			720
#define MIN_WIDTH			1280
#define MAX_HEIGHT			1080
#define MAX_WIDTH			1920

#define PAD_SINK			0
#define PAD_SOURCE			1
#define NUM_PADS			1

#define FIRMWARE_VERSION	0xb6

#define FIRWARE_NAME_MDF6000	"LVDS_MIPI_bridge_MDF6000_B6.bit"
#define FIRWARE_NAME_MD6000 	"LVDS_MIPI_bridge_MD6000_B6.bit"

#define CROSSLINKPLUS_IDCODE	0x43002F01
#define CROSSLINK_IDCODE		0x43002C01
#define CROSSLINK_RESET_RETRY_CNT	2

struct resolution {
	u16 width;
	u16 height;
	u16 framerate;
	u16 reg_val;
};

struct crosslink_dev {
	struct device *dev;
	struct regmap *regmap;
	struct i2c_client *i2c_client;
	struct v4l2_subdev sd;
	struct media_pad pad;
	struct v4l2_fwnode_endpoint ep; /* the parsed DT endpoint info */
	struct gpio_desc *reset_gpio;
	struct mutex lock;
	struct v4l2_mbus_framefmt fmt;
	struct resolution current_res_fr;
	struct tty_port port;
	struct device *tty_port_dev;
	struct delayed_work tty_work;
	struct delayed_work mipi_work;
	char of_name[32];
	int framerate;
	int enable_powerdown;
	int csi_id;
	int has_serial;
	int state;
	int firmware_loaded;
};

enum crosslink_regs {
	CROSSLINK_REG_ID = 0x1,         // RO: 8:  Firmware version
	CROSSLINK_REG_ENABLE = 0x2,     // RW: 8:  [b3]=CAM-POW-EN	[b2]=UART-EN	[b1]=LVDS-EN	[b0]=MIPI-EN
	CROSSLINK_REG_LVDS_INV = 0x3,	// RW: 8:  lvds hsync vsync invert. [1]=force-invert [0]=force-non-invert
	CROSSLINK_REG_LINE_COUNT = 0x4, // RO:16:  Y-count
	CROSSLINK_REG_COLM_COUNT = 0x6, // RO:16:  X-count
	CROSSLINK_REG_LVDS_STATUS = 0x8,// RO: 8:  embedded_hv_valid & hv_sync_inverted & is_8ch_not_4ch & pll_lock_int & gddr_rdy_int & bit_lock_int & word_lock_int & bw_rdy_int;
	CROSSLINK_REG_UART_STAT = 0x9,  // RO: 8:  board_detect2 & board_detect1 & s_busy_tx & s_busy_rx & s_data_fulltx & s_data_emptytx & s_data_fullrx & s_data_emptyrx;
	CROSSLINK_REG_UART_RX_CNT= 0xA, // RO: 8:  count of bytes in UART RX fifo
	CROSSLINK_REG_UART_RX_LAST= 0xB,// RO: 8:  last byte received. Can check the last byte without emptying the RX fifo.
	CROSSLINK_REG_UART_PRESCL= 0xC, // RW:16:  UART Prescaler from 24 MHz. default=2500 => 24M/2500=9600 baud.
	CROSSLINK_REG_FRAME_PERIOD= 0xE,// RO:16:  FRAME PERIOD	frame period register. micro-seconds per frame.
	CROSSLINK_REG_PX_MHZ = 0x10,    //RO: 8:  pixel-clk freq in Mhz
	CROSSLINK_REG_SERIAL = 0x80,    // RW:XX:  Any bytes read/written above 0x80 are read from or written to the UART RX/TX fifos. Fifos are 32 bytes deep.
};

enum crosslink_state {
	CRSLK_STATE_NONE = 0,
	CRSLK_STATE_PROBED,
	CRSLK_STATE_FW_LOADED,
	CRSLK_STATE_IDLE,
	CRSLK_STATE_STREAMING,
	CRSLK_STATE_POWERDOWN,
};

struct crosslink_ioctl_serial {
	u32 len;
	u8 data[64];
};

enum crosslink_ioctl_cmds {
	CROSSLINK_CMD_SERIAL_SEND_TX   	= 0x7601,
	CROSSLINK_CMD_SERIAL_RECV_RX	= 0x7602,
	CROSSLINK_CMD_SERIAL_RX_CNT		= 0x7603,
	CROSSLINK_CMD_SERIAL_BAUD 		= 0x7604,
	CROSSLINK_CMD_GET_FW_VERSION	= 0x7605,
	CROSSLINK_CMD_GET_LVDS_STATUS	= 0x7606,
	CROSSLINK_CMD_GET_UART_STATUS	= 0x7607,
	CROSSLINK_CMD_GET_FRAME_PERIOD	= 0x7608,
	CROSSLINK_CMD_GET_PIXEL_FREQ	= 0x7609,
	CROSSLINK_CMD_GET_LINE_COUNT	= 0x760A,
	CROSSLINK_CMD_GET_COLM_COUNT	= 0x760B,
	CROSSLINK_CMD_SET_POWERDOWN		= 0x760C,
	CROSSLINK_CMD_FORCE_HVSYNC_INV	= 0x760D,
	CROSSLINK_CMD_GET_REGS			= 0x760E,
	CROSSLINK_CMD_SET_REGS			= 0x760F,
	CROSSLINK_CMD_SERIAL_RX_LAST	= 0x7610,
};

/* function protoypes */
extern int crosslink_tty_probe(struct crosslink_dev *sensor);
extern int crosslink_fpga_ops_write_init(struct gpio_desc *reset, struct i2c_client *client);
extern int crosslink_fpga_ops_write(struct i2c_client *client, const char *buf, size_t count);
extern int crosslink_fpga_ops_write_complete(struct i2c_client *client);
extern u32 crosslink_fpga_reset(struct gpio_desc *reset, struct i2c_client *client);
extern void crosslink_tty_remove(struct crosslink_dev *sensor);
extern int crosslink_tty_init(void);
extern void crosslink_tty_exit(void);

#endif