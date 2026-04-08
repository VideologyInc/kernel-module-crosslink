// SPDX-License-Identifier: GPL-2.0
/*
 * Copyright (C) 2023 Videology Inc, Inc.
 */

#include <linux/clk.h>
#include <linux/ctype.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/i2c.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/regmap.h>
#include <linux/of_device.h>
#include <linux/of_gpio.h>
#include <linux/firmware.h>
#include <linux/pinctrl/consumer.h>
#include <linux/slab.h>
#include <linux/types.h>
#include <linux/kmod.h>
#include <linux/tty.h>
#include <media/v4l2-async.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-device.h>
#include <media/v4l2-event.h>
#include <media/v4l2-fwnode.h>
#include <media/v4l2-subdev.h>
#include <linux/version.h>

#include "crosslink.h"

static bool __read_mostly powerdown_enable = 0;
module_param(powerdown_enable, bool, 0644);

static int __read_mostly powerdown_timeout_ms=30000;
module_param(powerdown_timeout_ms, int, 0644);

static int __read_mostly powerup_wait_ms=2500;
module_param(powerup_wait_ms, int, 0644);


static inline struct crosslink_dev *to_crosslink_dev(struct v4l2_subdev *sd)
{
	return container_of(sd, struct crosslink_dev, sd);
}

// Corrects the given fps based on the given hf_cnt.
static int correct_period(struct v4l2_subdev *sub_dev, unsigned long *period, unsigned hf_cnt, unsigned long pixel_cnt)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sub_dev);

	if (sensor->video_format == FORMAT_PAL) {
		// PAL
		// Compare to known count ranges and determine pixel clock frequency.
		for (u8 i = 0; i < ARRAY_SIZE(camera_pixel_counts_pal); i++) {
			if(hf_cnt > camera_pixel_counts_pal_low[i] && hf_cnt < camera_pixel_counts_pal_high[i]) {
				// Calculate the period in nano seconds (from femto seconds period length).
				*period = (unsigned long)DIV_ROUND_CLOSEST_ULL((unsigned long long)pixel_cnt * camera_pixel_periods_pal[i], 1000000);
				return 0;
			}
		}
	}else if (sensor->video_format == FORMAT_NTSC) {
		// NTSC
		// Compare to known count ranges and determine pixel clock frequency.
		for (u8 i = 0; i < ARRAY_SIZE(camera_pixel_counts_ntsc); i++) {
			if(hf_cnt > camera_pixel_counts_ntsc_low[i] && hf_cnt < camera_pixel_counts_ntsc_high[i]) {
				// Calculate the period in nano seconds (from femto seconds period length).
				*period = (unsigned long)DIV_ROUND_CLOSEST_ULL((unsigned long long)pixel_cnt * camera_pixel_periods_ntsc[i], 1000000);
				return 0;
			}
		}
	}else {
		dev_err(sensor->dev, "Incorrect video_format value was set: %d\n", sensor->video_format);
		return -EINVAL;
	}

	*period = *period * 1000;
	dev_info(sensor->dev, "Measured pixel clock count does not align with any known value: %d\nUncorrected period was taken instead.\n", hf_cnt);
	return 0;
}

static int set_subdev_interval(struct v4l2_subdev *sub_dev, u32 *interval_numerator, u32 *interval_denominator, int *framerate) 
{
	struct crosslink_dev *sensor = to_crosslink_dev(sub_dev);

	int ret = 0;
	unsigned hf_cnt = 0;
	unsigned long pixel_cnt = 0;
	unsigned long period = 0;
	unsigned long frame_mult = 0;

	// Obtain counters that are required to adjust for the possible deviation of the internal clock inside the FPGA.
	// HF_CNT,	counter of the internal clock based on the pixel clock. Used to determine error of the internal clock.
	// PIX_CNT,	counter of the pixel clock per frame. Used to determine pixel clock frequency.
	// PERIOD,	estimated period measured inside the FPGA based on the internal clock.
	pm_runtime_get_sync(sensor->dev);
	ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_HF_CNT, &hf_cnt, 3);
	ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_PIX_CNT, &pixel_cnt, 3);
	ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_FPGA_PERIOD, &period, 2);
	pm_runtime_put_autosuspend(sensor->dev);
	if(ret || hf_cnt==0 || pixel_cnt==0)
		return ret;
	else {
		// Correct the period based on the obtained counters inside the FPGA.
		correct_period(sub_dev, &period, hf_cnt, pixel_cnt);
		dev_dbg(sub_dev->dev, "period: %lu\n", period);

		// Multiply the period by a multiplier to not lose precision (floats can not be used).
		frame_mult = (unsigned long)DIV_ROUND_CLOSEST_ULL((unsigned long long)1000000000 * PERIOD_MULTIPLIER, period);
		// Rounded framerate is required for the NTSC to obtain the exact ratio.
		*framerate = DIV_ROUND_CLOSEST(frame_mult, PERIOD_MULTIPLIER);

		if (sensor->video_format == FORMAT_PAL) {
			*interval_numerator = PERIOD_MULTIPLIER;
			*interval_denominator = frame_mult;
		} else if (sensor->video_format == FORMAT_NTSC) {
			*interval_numerator = FPS_NTSC_NUMERATOR;
			*interval_denominator = *framerate * PERIOD_MULTIPLIER;
		} else {
			dev_err(sensor->dev, "Incorrect video_format value was set: %d\n", sensor->video_format);
			return -EINVAL;
		}
		return 0;
	}
}

/* --------------- Subdev Operations --------------- */

static int crosslink_s_power(struct v4l2_subdev *sd, int on)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sd);
	int ret;
	dev_dbg(sensor->dev, "powering LVDS and UART %s\n", on ? "on" : "off");
	if (on)
		pm_runtime_get_sync(sensor->dev);
	ret = regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, on ? 0xFE : 0xFE);
	msleep(5);
	// regcache_mark_dirty(sensor->regmap);
	dev_dbg(sensor->dev, "powering finished %s\n", on ? "on" : "off");
	if (!on)
		pm_runtime_put_autosuspend(sensor->dev);
	pm_runtime_mark_last_busy(sensor->dev);
	return ret;
}

static long crosslink_ioctl(struct v4l2_subdev *sd, unsigned int cmd, void *arg)
{
	long ret = 0;
	unsigned int baud;
	u8 address = 0;
  u32 status;
  u32 temp_serial_len;
	struct crosslink_dev *sensor = to_crosslink_dev(sd);
	struct crosslink_ioctl_serial *serial;

	if (sensor->firmware_loaded == 0)
		return -ENODEV;

	pm_runtime_get_sync(sensor->dev);
	switch (cmd) {
		case CROSSLINK_CMD_SERIAL_SEND_TX:
      // Send reset to UART system to clear any remaining data.
      ret  = regmap_read(sensor->regmap, CROSSLINK_REG_ENABLE, &status);
		  ret |= regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, status &~ ENABLE_UART_MASK);
      ret |= regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, status | ENABLE_UART_MASK);

			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SERIAL_TX\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_bulk_write(sensor->regmap, CROSSLINK_REG_SERIAL, serial->data, serial->len);
			break;
		case CROSSLINK_CMD_SERIAL_RECV_RX:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SERIAL_RX\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			if (serial->len == 0)
				ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_RX_CNT, &serial->len);
			ret = regmap_bulk_read(sensor->regmap, CROSSLINK_REG_SERIAL, serial->data, serial->len);
			// Check if buffer overflow occured.
      temp_serial_len = serial->len;
      ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_FULL, &serial->len);
      if ((serial->len & 1) == 1) {
				dev_warn(sd->dev, "WARNING FPGA TX buffer has overflown!");
      } 
			if ((serial->len & 2) == 2) {
				dev_warn(sd->dev, "WARNING FPGA RX buffer has overflown!");
			}
			serial->len = temp_serial_len;
			
			break;
		case CROSSLINK_CMD_SERIAL_RX_CNT:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SERIAL_RX_WAITING\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_RX_CNT, &serial->len);
			break;
		case CROSSLINK_CMD_SERIAL_BAUD:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SERIAL_BAUD\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			if(serial->len) {
				baud = DIV_ROUND_CLOSEST(24000000, serial->len);
				regmap_raw_write(sensor->regmap, CROSSLINK_REG_UART_PRESCL, &baud, 2);
			} else {
				regmap_raw_read(sensor->regmap, CROSSLINK_REG_UART_PRESCL, &baud, 2);
				serial->len = DIV_ROUND_CLOSEST(24000000, baud);
			}
			break;
		case CROSSLINK_CMD_GET_FW_VERSION:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_FW_VERSION\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_ID, &serial->len);
			break;
		case CROSSLINK_CMD_GET_LVDS_STATUS:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_LVDS_STATUS\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_LVDS_STATUS, &serial->len);
			break;
		case CROSSLINK_CMD_GET_UART_STATUS:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_UART_STATUS\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_STAT, &serial->len);
			break;
		case CROSSLINK_CMD_GET_FPGA_PERIOD:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_FPGA_PERIOD\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_FPGA_PERIOD, &serial->len, 2);
			break;
		case CROSSLINK_CMD_GET_PIXEL_FREQ:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_PIXEL_FREQ\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_PX_MHZ, &serial->len);
			break;
		case CROSSLINK_CMD_GET_LINE_COUNT:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_LINE_COUNT\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_LINE_COUNT, &serial->len, 2);
			break;
		case CROSSLINK_CMD_GET_COLM_COUNT:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_COLM_COUNT\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_COLM_COUNT, &serial->len, 2);
			break;
		case CROSSLINK_CMD_SET_POWERDOWN:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SET_POWERDOWN\n", __func__);
			sensor->enable_powerdown = 1;
			break;
		case CROSSLINK_CMD_SET_FORMAT_PAL:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SET_FORMAT_PAL\n", __func__);
			sensor->video_format = FORMAT_PAL;
			break;
		case CROSSLINK_CMD_SET_FORMAT_NTSC:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SET_FORMAT_NTSC\n", __func__);
			sensor->video_format = FORMAT_NTSC;
			break;
		case CROSSLINK_CMD_GET_VIDEOFORMAT:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_VIDEOFORMAT\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			serial->len = sensor->video_format;
			break;
		case CROSSLINK_CMD_FORCE_HVSYNC_INV:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_FORCE_HVSYNC_INV\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_write(sensor->regmap, CROSSLINK_REG_LVDS_INV, serial->len);
			break;
		case CROSSLINK_CMD_GET_REGS:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_REGS\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			address = serial->data[0];
			ret = regmap_bulk_read(sensor->regmap, address, serial->data, serial->len);
			break;
		case CROSSLINK_CMD_SET_REGS:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SET_REGS\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			address = serial->data[0];
			ret = regmap_bulk_write(sensor->regmap, address, serial->data, serial->len);
			break;
		case CROSSLINK_CMD_SERIAL_RX_LAST:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_SERIAL_RX_LAST\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_RX_LAST, &serial->len);
			break;
    case CROSSLINK_CMD_GET_UART_RX_FILLRATE:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_UART_RX_FILLRATE\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_RX_FILLRATE, &serial->len);
			break;
    case CROSSLINK_CMD_GET_UART_FULL:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_UART_FULL\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_FULL, &serial->len);
		case CROSSLINK_CMD_GET_FRAME_PERIOD:
			dev_dbg_ratelimited(sensor->dev, "%s: CROSSLINK_CMD_GET_FRAME_PERIOD\n", __func__);
			serial = (struct crosslink_ioctl_serial *)arg;
			unsigned hf_cnt = 0;
			unsigned long pixel_cnt = 0;
			unsigned long period = 0;
			ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_HF_CNT, &hf_cnt, 3);
			ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_PIX_CNT, &pixel_cnt, 3);
			ret = regmap_raw_read(sensor->regmap, CROSSLINK_REG_FPGA_PERIOD, &period, 2);
			if(ret || hf_cnt==0 || pixel_cnt==0)
				return ret;
			correct_period(sd, &period, hf_cnt, pixel_cnt);
			serial->len = period;
			break;
		default:
			ret = -EINVAL;
	}
	pm_runtime_put_autosuspend(sensor->dev);

	return 0;
}

static int crosslink_ops_get_fmt(struct v4l2_subdev *sub_dev, struct v4l2_subdev_state *sd_state, struct v4l2_subdev_format *format)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sub_dev);
	struct v4l2_mbus_framefmt *fmt;
	u32 status;
	int ret;

	if (format->pad >= NUM_PADS)
		return -EINVAL;

	if (format->which == V4L2_SUBDEV_FORMAT_TRY) {
		dev_dbg(sub_dev->dev, "%s: TRY \n", __func__);
		fmt = v4l2_subdev_get_try_format(&sensor->sd, sd_state, format->pad);
		format->format = *fmt;
	} else {
		dev_dbg(sub_dev->dev, "%s: ACTIVE \n", __func__);
		format->format = sensor->fmt;


		// format->format.width = sensor->current_res_fr.width;
		// format->format.height = sensor->current_res_fr.height;


		// get frame height/width
		pm_runtime_get_sync(sensor->dev);
		ret  = regmap_raw_read(sensor->regmap, CROSSLINK_REG_COLM_COUNT, &format->format.width, 2);
		ret |= regmap_raw_read(sensor->regmap, CROSSLINK_REG_LINE_COUNT, &format->format.height, 2);
		ret |= regmap_read(sensor->regmap, CROSSLINK_REG_LVDS_STATUS, &status);
		pm_runtime_put_autosuspend(sensor->dev);

		if(ret || format->format.width == 0 || format->format.height == 0)
			return ret;
		else{
			pr_debug("%s: get_fmt->height =%d\n", __func__, format->format.height);
			pr_debug("%s: get_fmt->width  =%d\n", __func__, format->format.width);
			pr_debug("%s: get_status  =%x\n", __func__, status);
			sensor->current_res_fr.width = format->format.width;
			sensor->current_res_fr.height = format->format.height;
		}
	}
	return 0;
}

static int crosslink_set_fmt(struct v4l2_subdev *sd, struct v4l2_subdev_state *sd_state, struct v4l2_subdev_format *format)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sd);
	u32 status;
	int ret=0;

	dev_dbg(sd->dev, "%s: \n", __func__);

	if (format->pad >= NUM_PADS)
		return -EINVAL;

	format->format.code = sensor->fmt.code;

	pr_debug("%s: requested:height =%d\n", __func__, format->format.height);
	pr_debug("%s: requested:width  =%d\n", __func__, format->format.width);
	pm_runtime_get_sync(sensor->dev);
	// check if the resolution matches the current value
	ret  = regmap_raw_read(sensor->regmap, CROSSLINK_REG_COLM_COUNT, &sensor->current_res_fr.width, 2);
	ret |= regmap_raw_read(sensor->regmap, CROSSLINK_REG_LINE_COUNT, &sensor->current_res_fr.height, 2);
	ret |= regmap_read(sensor->regmap, CROSSLINK_REG_LVDS_STATUS, &status);
	pm_runtime_put_autosuspend(sensor->dev);

	if (format->format.width == sensor->current_res_fr.width && format->format.height == sensor->current_res_fr.height) {
		dev_dbg(sd->dev, "requested resolution matches current.\n");
	} else {
		dev_warn(sd->dev, "requested resolution (%dx%d) does NOT match current (%dx%d).\n",format->format.width, format->format.height, sensor->current_res_fr.width, sensor->current_res_fr.height );
		format->format.width = sensor->current_res_fr.width;
		format->format.height = sensor->current_res_fr.height;
	}

	pr_debug("%s: sensor->fmt->height =%d\n", __func__, format->format.height);
	pr_debug("%s: sensor->fmt->width  =%d\n", __func__, format->format.width);
	pr_debug("%s: get_status  =%x\n", __func__, status);
	pr_debug("%s: end \n", __func__);
	return ret;
}

static int ops_enum_frame_size(struct v4l2_subdev *sub_dev, struct v4l2_subdev_state *sd_state, struct v4l2_subdev_frame_size_enum *fse)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sub_dev);
	struct resolution res = {.width=U16_MAX, .height=U16_MAX};
	int ret=-EINVAL;

	dev_dbg(sub_dev->dev, "%s: \n", __func__);

	if (fse->pad >= NUM_PADS)
		return -EINVAL;
	if (fse->code != sensor->fmt.code) {
		dev_dbg_ratelimited(sub_dev->dev, "%s unsupported fmt.code: 0x%04x.\n", __func__, fse->code);
		return -EINVAL;
	}

	if (fse->index == 0) {
		pm_runtime_get_sync(sensor->dev);
		ret  = regmap_raw_read(sensor->regmap, CROSSLINK_REG_COLM_COUNT, &res.width, 2);
		ret |= regmap_raw_read(sensor->regmap, CROSSLINK_REG_LINE_COUNT, &res.height, 2);
		pm_runtime_put_autosuspend(sensor->dev);
		if(ret == 0 && res.width != 0 && res.height != 0) {
			pr_debug("%s: offer height =%d\n", __func__, res.height);
			pr_debug("%s: offer width  =%d\n", __func__, res.width);
			sensor->current_res_fr.width = res.width;
			sensor->current_res_fr.height = res.height;
			fse->min_width  = fse->max_width  = res.width;
			fse->min_height = fse->max_height = res.height;
			ret = 0;
		}
	} else {
		ret = -EINVAL;
	}
	return ret;
}

static int ops_enum_frame_interval(struct v4l2_subdev *sub_dev, struct v4l2_subdev_state *sd_state, struct v4l2_subdev_frame_interval_enum *fie)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sub_dev);
	int ret = -EINVAL;
	int framerate;

	dev_dbg(sub_dev->dev, "%s: \n", __func__);

	if (fie->pad >= NUM_PADS)
		return -EINVAL;
	// only suports MEDIA_BUS_FMT_YUYV8_1X16
	if (fie->code != sensor->fmt.code) {
		dev_dbg_ratelimited(sub_dev->dev, "%s unsupported fmt.code: 0x%04x.\n", __func__, fie->code);
		return -EINVAL;
	}

	if (fie->index == 0) {
		ret =  set_subdev_interval(sub_dev, &fie->interval.numerator, &fie->interval.denominator, &framerate);
		return ret;
	}
	return -EINVAL;
}

static int ops_get_frame_interval(struct v4l2_subdev *sub_dev, struct v4l2_subdev_frame_interval *fi)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sub_dev);
	int ret = 0;
	int framerate;
	dev_dbg(sub_dev->dev, "%s: \n", __func__);

	if (fi->pad >= NUM_PADS)
		return -EINVAL;
	
	ret =  set_subdev_interval(sub_dev, &fi->interval.numerator, &fi->interval.denominator, &framerate);
	sensor->current_res_fr.framerate = framerate;
	dev_dbg(sub_dev->dev, "%s, framerate: %d\n", __func__, framerate);
	return ret;
}

static int crosslink_enum_mbus_code(struct v4l2_subdev *sub_dev, struct v4l2_subdev_state *sd_state, struct v4l2_subdev_mbus_code_enum *code)
{
	if ((code->pad >= NUM_PADS) || (code->index >= 1))
		return -EINVAL;

	dev_dbg_ratelimited(sub_dev->dev, "%s: \n", __func__);
	code->code = MEDIA_BUS_FMT_YUYV8_1X16;
	return 0;
}

static void crosslink_mipi_handler(struct work_struct *work) {
	struct crosslink_dev *sensor = container_of(to_delayed_work(work), struct crosslink_dev, mipi_work);
	regmap_write(sensor->regmap, 0x2, (sensor->state == CRSLK_STATE_STREAMING) ? 0xFF : 0xFE);
	dev_dbg(sensor->dev, "%s: %s\n", __func__, (sensor->state == CRSLK_STATE_STREAMING) ? "re-enable mipi" : "disable mipi");
}

static int crosslink_s_stream(struct v4l2_subdev *sd, int enable)
{
	struct crosslink_dev *sensor = to_crosslink_dev(sd);
	int ret = 0;

	if (sensor->ep.bus_type != V4L2_MBUS_CSI2_DPHY){
		dev_err(sensor->dev, "endpoint bus_type not supported: %d\n", sensor->ep.bus_type);
		return -EINVAL;
	}
	if (enable) {
		pm_runtime_get_sync(sensor->dev);
		sensor->state = CRSLK_STATE_STREAMING;
		ret |= regmap_write(sensor->regmap, 0x2, 0xFE);
		INIT_DELAYED_WORK(&sensor->mipi_work, crosslink_mipi_handler);
		schedule_delayed_work(&sensor->mipi_work, HZ/15);  // at least one frame delay. lowest framerate is 25 Hz
		pr_debug("%s: Starting stream\n", __func__);
	} else {
		ret |= regmap_write(sensor->regmap, 0x2, 0xFE);
		sensor->state = CRSLK_STATE_IDLE;
		pm_runtime_mark_last_busy(sensor->dev);
		pm_runtime_put_autosuspend(sensor->dev);
		pr_debug("%s: Stopping stream \n", __func__);
	}

	return ret;
}

static void crosslink_remove(struct i2c_client *client);

static void crosslink_fw_handler(const struct firmware *fw, void *context)
{
	int ret, uart_stat;
	struct crosslink_dev *sensor = (struct crosslink_dev *)context;

	if (!fw)
		return;

	mutex_lock(&sensor->lock);
	ret = crosslink_fpga_ops_write_init(sensor->reset_gpio, sensor->i2c_client);
	if (ret < 0)
		goto exit;
	ret = crosslink_fpga_ops_write(sensor->i2c_client, fw->data, fw->size);
	if (ret < 0)
		goto exit;
	ret = crosslink_fpga_ops_write_complete(sensor->i2c_client);
	if (ret < 0)
		goto exit;

	sensor->firmware_loaded = 1;
	sensor->state = CRSLK_STATE_FW_LOADED;
exit:
	release_firmware(fw);
	mutex_unlock(&sensor->lock);
	regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, 0xFE);
	if (ret < 0) {
		dev_err(sensor->dev, "Failed to load firmware: %d\n", ret);
		crosslink_remove(sensor->i2c_client);
	} else {
		msleep(2);
		ret = regmap_read(sensor->regmap, CROSSLINK_REG_UART_STAT, &uart_stat);
		if (ret == 0)
			sensor->has_serial = uart_stat & 0b11000000;
		if (sensor->has_serial)
			crosslink_tty_probe(sensor);
	}
}

static const struct v4l2_subdev_core_ops crosslink_core_ops = {
	.s_power = crosslink_s_power,
	.log_status = v4l2_ctrl_subdev_log_status,
	.subscribe_event = v4l2_ctrl_subdev_subscribe_event,
	.unsubscribe_event = v4l2_event_subdev_unsubscribe,
	.ioctl = crosslink_ioctl,
};

static const struct v4l2_subdev_video_ops crosslink_video_ops = {
	.g_frame_interval = ops_get_frame_interval,
	.s_stream = crosslink_s_stream,
};

static const struct v4l2_subdev_pad_ops crosslink_pad_ops = {
	.enum_mbus_code = crosslink_enum_mbus_code,
	.get_fmt = crosslink_ops_get_fmt,
	.set_fmt = crosslink_set_fmt,
	.enum_frame_size = ops_enum_frame_size,
	.enum_frame_interval = ops_enum_frame_interval,
};

static const struct v4l2_subdev_ops crosslink_subdev_ops = {
	.core = &crosslink_core_ops,
	.video = &crosslink_video_ops,
	.pad = &crosslink_pad_ops,
};

static int crosslink_link_setup(struct media_entity *entity, const struct media_pad *local, const struct media_pad *remote, u32 flags)
{
	return 0;
}

static const struct media_entity_operations crosslink_sd_media_ops = {
	.link_setup = crosslink_link_setup,
};

static int __maybe_unused crosslink_suspend(struct device *dev)
{
	int ret = 0;
	struct i2c_client *client = to_i2c_client(dev);
	struct v4l2_subdev *sd = i2c_get_clientdata(client);
	struct crosslink_dev *sensor = to_crosslink_dev(sd);
	dev_dbg(dev, "%s: \n", __func__);

	if (sensor->enable_powerdown)
		ret = regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, 0x07);
	else
		ret = regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, 0xFE);
	regcache_mark_dirty(sensor->regmap);
	sensor->state = CRSLK_STATE_POWERDOWN;
	return 0;
}

static int __maybe_unused crosslink_resume(struct device *dev)
{
	int ret = 0;
	u32 status;
	struct i2c_client *client = to_i2c_client(dev);
	struct v4l2_subdev *sd = i2c_get_clientdata(client);
	struct crosslink_dev *sensor = to_crosslink_dev(sd);
	dev_dbg(dev, "%s: \n", __func__);

	if (sensor->firmware_loaded) {
		ret  = regmap_read(sensor->regmap, CROSSLINK_REG_ENABLE, &status);
		ret |= regmap_write(sensor->regmap, CROSSLINK_REG_ENABLE, 0xFE);
		if (ret == 0) {
			if ((status & 0x08) == 0){
				dev_info(sensor->dev, "powering up camera...\n");
				msleep(powerup_wait_ms);
			}
			msleep(10);
			ret |= regmap_read_poll_timeout(sensor->regmap, CROSSLINK_REG_LVDS_STATUS, status, ((status & 0x01) == 0x01), 5000, 2000000); // wait for LVDS pll-locked
			if (ret)
				dev_info(sensor->dev, "timeout waiting for LVDS PLL lock: %d\n", status);
			sensor->state = CRSLK_STATE_IDLE;
		} else {
			dev_err(sensor->dev, "failed to power on %d\n", ret);
		}
	}
	return 0;
}

static void crosslink_lock_mutex(void *p) {
	mutex_lock(&((struct crosslink_dev *)p)->lock);
}
static void crosslink_unlock_mutex(void *p) {
	mutex_unlock(&((struct crosslink_dev *)p)->lock);
}

static struct regmap_config sensor_regmap_config = {
	.reg_bits = 8,
	.val_bits = 8,
	.reg_format_endian = REGMAP_ENDIAN_LITTLE,
	.val_format_endian = REGMAP_ENDIAN_LITTLE,
	.cache_type = REGCACHE_NONE,
	.lock = crosslink_lock_mutex,
	.unlock = crosslink_unlock_mutex,
};

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 3, 0)
static int crosslink_probe(struct i2c_client *client)
#else
static int crosslink_probe(struct i2c_client *client, const struct i2c_device_id *id)
#endif
{
	struct device *dev = &client->dev;
	struct fwnode_handle *endpoint;
	struct crosslink_dev *sensor;
	struct v4l2_mbus_framefmt *fmt;
	int ret;
	u32 idcode = 0;

	pr_debug("-->%s crosslink Probe start\n",__func__);

	sensor = devm_kzalloc(dev, sizeof(*sensor), GFP_KERNEL);
	if (!sensor)
		return -ENOMEM;

	sensor->dev = dev;
	sensor->i2c_client = client;
	sensor->current_res_fr.height = 0;
	sensor->current_res_fr.width = 0;
	sensor->video_format = FORMAT_PAL;
	sensor->enable_powerdown = (int)powerdown_enable;

	// default init sequence initialize sensor to 1080p30 YUV422 UYVY
	fmt = &sensor->fmt;
	fmt->code = MEDIA_BUS_FMT_YUYV8_1X16;
	fmt->colorspace = V4L2_COLORSPACE_SRGB;
	fmt->ycbcr_enc = V4L2_MAP_YCBCR_ENC_DEFAULT(fmt->colorspace);
	fmt->quantization = V4L2_QUANTIZATION_FULL_RANGE;
	fmt->xfer_func = V4L2_MAP_XFER_FUNC_DEFAULT(fmt->colorspace);
	fmt->width = 1920;
	fmt->height = 1080;
	fmt->field = V4L2_FIELD_NONE;
	sensor->framerate = 30;

	/* request reset pin */
	sensor->reset_gpio = devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_LOW);
	if (IS_ERR(sensor->reset_gpio)) {
		ret = PTR_ERR(sensor->reset_gpio);
		if (ret != -EPROBE_DEFER)
			dev_warn(dev, "Cannot get reset GPIO (%d)", ret);
		// return ret;
	}

	of_property_read_u32(dev->of_node, "csi_id", &sensor->csi_id);

	// get name
	snprintf(sensor->of_name, 31, "VD_%s_%d", client->name, client->addr);
	sensor->of_name[31] = 0;

	endpoint = fwnode_graph_get_next_endpoint(dev_fwnode(&client->dev), NULL);
	if (!endpoint) {
		dev_err(dev, "endpoint node not found\n");
		return -EINVAL;
	}

	ret = v4l2_fwnode_endpoint_parse(endpoint, &sensor->ep);
	fwnode_handle_put(endpoint);
	if (ret) {
		dev_err(dev, "Could not parse endpoint\n");
		return ret;
	}

	pr_debug("%s: sensor->ep.bus_type=%d\n", __func__, sensor->ep.bus_type);

	if (sensor->ep.bus_type != V4L2_MBUS_CSI2_DPHY) {
		dev_err(dev, "Unsupported bus type %d\n", sensor->ep.bus_type);
		return -EINVAL;
	}

	mutex_init(&sensor->lock);
	sensor_regmap_config.lock_arg = sensor;
	sensor->regmap = devm_regmap_init_i2c(client, &sensor_regmap_config);
	if (IS_ERR(sensor->regmap)) {
		dev_err(dev, "regmap init failed\n");
		return PTR_ERR(sensor->regmap);
	}

	mutex_lock(&sensor->lock);
	idcode = crosslink_fpga_reset(sensor->reset_gpio, sensor->i2c_client);
	if (idcode == CROSSLINK_IDCODE) {
		ret = request_firmware_nowait(THIS_MODULE, FW_ACTION_UEVENT, FIRWARE_NAME_MD6000,  dev, GFP_KERNEL, sensor, crosslink_fw_handler);
		dev_dbg(dev, "requesting firmware %s", FIRWARE_NAME_MD6000);
	} else if (idcode == CROSSLINKPLUS_IDCODE) {
		ret = request_firmware_nowait(THIS_MODULE, FW_ACTION_UEVENT, FIRWARE_NAME_MDF6000, dev, GFP_KERNEL, sensor, crosslink_fw_handler);
		dev_dbg(dev, "requesting firmware %s", FIRWARE_NAME_MDF6000);
	} else {
		dev_err(dev, "unexpected IDCODE value: 0x%x\n", idcode);
		return -EINVAL;
	}

	dev_info(dev, "Loading Firmware: %02x\n", FIRMWARE_VERSION);
	if (ret) {
		dev_err(dev, "Failed request_firmware_nowait err %d\n", ret);
		goto entity_cleanup;
	}

	v4l2_i2c_subdev_init(&sensor->sd, client, &crosslink_subdev_ops);

	sensor->sd.flags |= V4L2_SUBDEV_FL_HAS_EVENTS | V4L2_SUBDEV_FL_HAS_DEVNODE;
	sensor->sd.dev = &client->dev;
	// sensor->sd.internal_ops = &crosslink_internal_ops;
	sensor->pad.flags = MEDIA_PAD_FL_SOURCE;
	sensor->sd.entity.ops = &crosslink_sd_media_ops;
	sensor->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;
	ret = media_entity_pads_init(&sensor->sd.entity, 1, &sensor->pad);
	if (ret)
		goto entity_cleanup;

/*
	 * We need the driver to work in the event that pm runtime is disable in
	 * the kernel, so power up and verify the chip now. In the event that
	 * runtime pm is disabled this will leave the chip on, so that streaming
	 * will work.
	 */

	ret = crosslink_resume(&client->dev);
	if (ret)
		goto entity_cleanup;

	pm_runtime_set_active(&client->dev);
	pm_runtime_get_noresume(&client->dev);
	pm_runtime_enable(&client->dev);

	ret = v4l2_async_register_subdev_sensor(&sensor->sd);
	if (ret) {
		dev_err(&client->dev, "failed to register V4L2 subdev: %d",
			ret);
		goto err_pm_runtime;
	}

	pm_runtime_set_autosuspend_delay(&client->dev, powerdown_timeout_ms);
	pm_runtime_use_autosuspend(&client->dev);
	pm_runtime_put_autosuspend(&client->dev);

	// ret = crosslink_tty_probe(sensor);
	mutex_unlock(&sensor->lock);
	pr_debug("<--%s crosslink Probe end successful, return\n",__func__);
	sensor->state = CRSLK_STATE_PROBED;
	return 0;

err_pm_runtime:
	pm_runtime_disable(&client->dev);
	pm_runtime_put_noidle(&client->dev);

entity_cleanup:
	pr_debug("---%s crosslink ERR entity_cleanup\n",__func__);
	mutex_unlock(&sensor->lock);
	media_entity_cleanup(&sensor->sd.entity);
	mutex_destroy(&sensor->lock);
	return ret;
}

#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 0, 0)
static int crosslink_remove(struct i2c_client *client)
#else
static void crosslink_remove(struct i2c_client *client)
#endif
{
	struct v4l2_subdev *sd = i2c_get_clientdata(client);
	struct crosslink_dev *sensor = to_crosslink_dev(sd);

	// wait in case Firmware is busy
	if (!mutex_trylock(&sensor->lock)){
		mutex_lock(&sensor->lock);
		msleep(100);
	}
	mutex_unlock(&sensor->lock);

	crosslink_tty_remove(sensor);

	/* Barrier after the sysfs remove */
	pm_runtime_barrier(&client->dev);
	if (!pm_runtime_suspended(&client->dev))
		pr_debug("%s: runtime not suspended\n", __func__);

	pm_runtime_disable(&client->dev);
	pm_runtime_set_suspended(&client->dev);

	v4l2_async_unregister_subdev(&sensor->sd);
	media_entity_cleanup(&sensor->sd.entity);

	mutex_destroy(&sensor->lock);
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 0, 0)
	return 0;
#endif
}

static const struct dev_pm_ops crosslink_pm_ops = {
	SET_RUNTIME_PM_OPS(crosslink_suspend, crosslink_resume, NULL)
};

static const struct i2c_device_id crosslink_id[] = {
	{"crosslink", 0},
	{},
};
MODULE_DEVICE_TABLE(i2c, crosslink_id);

static const struct of_device_id crosslink_dt_ids[] = {
	{ .compatible = "scailx,lvds2mipi" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, crosslink_dt_ids);

static struct i2c_driver crosslink_i2c_driver = {
	.driver = {
		.name  = "crosslink",
		.of_match_table	= crosslink_dt_ids,
		.pm = &crosslink_pm_ops,
	},
	.id_table = crosslink_id,
	.probe = crosslink_probe,
	.remove   = crosslink_remove,
};

static int __init crosslink_init(void)
{
	crosslink_tty_init();
	return i2c_add_driver(&crosslink_i2c_driver);
}

static void __exit crosslink_exit(void)
{
	i2c_del_driver(&crosslink_i2c_driver);
	crosslink_tty_exit();
}

module_init(crosslink_init);
module_exit(crosslink_exit);

MODULE_DESCRIPTION("crosslink MIPI Camera Subdev Driver");
MODULE_LICENSE("GPL");
MODULE_AUTHOR("VideologyInc, 2023");
MODULE_VERSION("1.0");
MODULE_ALIAS("crosslink_lvds2mipi");
