// SPDX-License-Identifier: GPL-2.0
/*
 * FPGA firmware update for crosslink-plus.
 *
 *  Copyright (c) 2023 Videology Inc.
 *
 * This driver adds support to the FPGA manager for configuring the SRAM of
 * Lattice CrossLink FPGAs through I2C.
 */

#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of_gpio.h>
#include <linux/stringify.h>
#include <linux/delay.h>
#include <linux/string.h>
#include <linux/slab.h>
#include "crosslink.h"

u8 isc_enable[]          = {0xC6, 0x00, 0x00, 0x00};
u8 isc_erase[]           = {0x0E, 0x00, 0x00, 0x00};
u8 isc_disable[]         = {0x26, 0x00, 0x00, 0x00};

u8 idcode_pub[]          = {0xE0, 0x00, 0x00, 0x00};
u8 read_usercode[]       = {0xC0, 0x00, 0x00, 0x00};
u8 uidcode_pub[]         = {0x19, 0x00, 0x00, 0x00};

u8 lsc_init[]            = {0x46, 0x00, 0x00, 0x00};
u8 lsc_bitstream_burst[] = {0x7A, 0x00, 0x00, 0x00};
u8 lsc_read_status[]     = {0x3C, 0x00, 0x00, 0x00};
u8 lsc_refresh[]         = {0x79, 0x00, 0x00, 0x00};
u8 lsc_check_busy[]      = {0xF0, 0x00, 0x00, 0x00};

u8 activation_msg[] = {0xA4, 0xC6, 0xF4, 0x8A};

#define STATUS_DONE	BIT(8)
#define STATUS_BUSY	BIT(12)
#define STATUS_FAIL	BIT(13)

#define prog_addr 0x40

///	@brief Transfer data to the FPGA, with the I2C lock already in possesion.
///	@param		client		I2C bus object.
///	@param[in]	write_buf	Data to write.
///	@param[in]	write_len	Number of bytes to write.
///	@param[out]	read_buf	Buffer in which to receive the read data.
///	@param[in]	read_len	Size of the read buffer.
///	@returns Returns a negative value on error; success otherwise.
///	@pre The lock for the I2C bus, passed via 'client', has been taken by
///		the calling function.
static int __lsc_xfer(struct i2c_client *client, u8 *write_buf, size_t write_len, u8 *read_buf, size_t read_len) {
    struct i2c_msg msg[2];
    int ret, msg_count = 1;

	if (read_len > 0)
		msg_count = 2;

	memset(msg, 0, sizeof(msg));
    msg[0].addr = prog_addr;
    msg[0].buf = write_buf;
    msg[0].len = write_len;
    msg[1].addr = prog_addr;
    msg[1].flags = I2C_M_RD;
    msg[1].buf = read_buf;
    msg[1].len = read_len;

    ret = __i2c_transfer(client->adapter, msg, msg_count);
    return ret;
}

///	@brief Transfer data to the FPGA.
///	@param		client		I2C bus object.
///	@param[in]	write_buf	Data to write.
///	@param[in]	write_len	Number of bytes to write.
///	@param[out]	read_buf	Buffer in which to receive the read data.
///	@param[in]	read_len	Size of the read buffer.
///	@returns Returns a negative value on error; success otherwise.
///	@details This functions transfer data to the FPGA. The transfer is protected
///		by the I2C bus lock, but this lock can be taken in advance to lock out
///		other devices on the bus.
static int lsc_xfer(struct i2c_client *client, u8 *write_buf, size_t write_len, u8 *read_buf, size_t read_len) {
	int ret;
	int had_lsc_lock;
	
	///	@li Take the bus lock with a call to 'lsc_lock()'. Remember if the bus
	///		was already in possession.
	had_lsc_lock = crosslink_lsc_lock(client);
	
	///	@li Transfer the data with a call to '__lsc_xfer()'.
	ret = __lsc_xfer(client, write_buf, write_len, read_buf, read_len);

	///	@li Release the bus lock, but only when it was taken above.
	///		If we already had the lock when calling 'lsc_lock()', the lock is
	///		held a global level and we must \em not release it here.
	if( !had_lsc_lock ) {
		crosslink_lsc_unlock(client);
	}
	
	return ret;
}

static u32 lsc_status(struct i2c_client *client) {
	int ret=0;
	u32 status=0;
	ret = lsc_xfer(client, lsc_read_status, ARRAY_SIZE(lsc_read_status), (u8 *) &status, sizeof(status));
	if (ret < 0) {
		dev_err(&client->dev, "LSC_READ_STATUS command failed! (%d)\n", ret);
		return 0xffff;
	}
	status = __be32_to_cpu(status);

	dev_dbg(&client->dev, "STATUS: 0x%x\n (done: %s busy: %s, fail: %s)", status,
			status & STATUS_DONE ? "yes" : "no",
			status & STATUS_BUSY ? "yes" : "no",
			status & STATUS_FAIL ? "yes" : "no");

	if (status & STATUS_BUSY) {
		dev_dbg(&client->dev, "stat busy\n");
	}

	return status;
}

u32 crosslink_fpga_reset(struct gpio_desc *reset, struct i2c_client *client)
{
	u32 idcode=0;
	int ret;
	dev_dbg(&client->dev, "START RESET\n");

	gpiod_set_value_cansleep(reset, 0);
	mdelay(2);
	dev_dbg(&client->dev, "DELAY 10\n");
	gpiod_set_value_cansleep(reset, 1);
	mdelay(5);
	dev_dbg(&client->dev, "RESET, DELAY 1000\n");

	ret = lsc_xfer(client, activation_msg, ARRAY_SIZE(activation_msg), NULL, 0);
	if (ret < 0) {
		dev_err(&client->dev, "Writing activation code failed! (%d)\n", ret);
		return (u32)ret;
	}

	gpiod_set_value_cansleep(reset, 0);

	mdelay(1);

	ret = lsc_xfer(client, idcode_pub, ARRAY_SIZE(idcode_pub), (u8 *) &idcode, sizeof(idcode));
	dev_dbg(&client->dev, "READ ID CODE\n");
	if (ret < 0) {
		dev_err(&client->dev, "IDCODE command failed! (%d)\n", ret);
		return (u32)ret;
	}

	dev_dbg(&client->dev, "IDCODE: 0x%x\n", idcode);

	return idcode;
}

int crosslink_fpga_ops_write_init(struct gpio_desc *reset, struct i2c_client *client)
{
	int ret;
	u32 stat;

	dev_dbg(&client->dev, "ISC ENABLE\n");
	ret = lsc_xfer(client, isc_enable, ARRAY_SIZE(isc_enable), NULL, 0);
	if (ret < 0) {
		dev_err(&client->dev, "ISC_ENABLE command failed! (%d)\n", ret);
		return ret;
	}

	mdelay(1);

	dev_dbg(&client->dev, "ERASE\n");
	ret = lsc_xfer(client, isc_erase, ARRAY_SIZE(isc_erase), NULL, 0);
	if (ret < 0) {
		dev_err(&client->dev, "ISC_ERASE command failed! (%d)\n", ret);
		return ret;
	}

	mdelay(25);
	stat = lsc_status(client);
	if ((stat & 0x3000) != 0){
		dev_err(&client->dev, "status after erase is invalid: (%x)\n", stat);
		return -EINVAL;
	}

	return 0;
}

int crosslink_fpga_ops_write(struct i2c_client *client, const char *buf, size_t count)
{
	u8* msgbuf = kzalloc(count + 4, GFP_KERNEL);
	int msglen = count + 4;
	int maxlen = 8192;
	int msgnum = DIV_ROUND_UP(msglen,maxlen);
	struct i2c_msg *bitstream_msg;
	u32 status;
	int ret, i;

	if (!msgbuf)
		return -ENOMEM;

	bitstream_msg = kzalloc(sizeof(struct i2c_msg) * msgnum, GFP_KERNEL);
	if (!bitstream_msg)
		return -ENOMEM;

	dev_dbg(&client->dev, "LSC-INIT\n");
	ret = lsc_xfer(client, lsc_init, ARRAY_SIZE(lsc_init), NULL, 0);
	if (ret < 0) {
		dev_err(&client->dev, "LSC_INIT command failed! (%d)\n", ret);
		return ret;
	}

	memcpy(msgbuf, lsc_bitstream_burst, 4);
	memcpy(msgbuf + 4, buf, count);

	for(i = 0; i < msgnum; i++) {
		bitstream_msg[i].addr = prog_addr;
		bitstream_msg[i].buf  = msgbuf + (i * maxlen);
		bitstream_msg[i].len  = msglen > maxlen ? maxlen : msglen;
		if (i > 0)
			bitstream_msg[i].flags |= I2C_M_NOSTART;

		msglen -= maxlen;
	}
	dev_dbg(&client->dev, "SENDING %d PACKETS\n", msgnum);
	ret = __i2c_transfer(client->adapter, bitstream_msg, msgnum);
	if (ret < 0) {
		dev_err(&client->dev, "BITSTREAM_BURST command failed! (%d).\n", ret);
		return ret;
	}

	kfree(msgbuf);
	kfree(bitstream_msg);

	mdelay(5);
	status = lsc_status(client);
	if ((status & 0x3100) != 0x100) {
		dev_err(&client->dev, "Status following Bitstream-prog is invalid: 0x%x\n", status);
	 	return -EIO;
	}

	return 0;
}

int crosslink_fpga_ops_write_complete(struct i2c_client *client)
{
	int ret;

	ret = lsc_xfer(client, isc_disable, ARRAY_SIZE(isc_disable), NULL, 0);
	if (ret < 0) {
		dev_err(&client->dev, "ISC_DISABLE command failed! (%d)\n", ret);
		return ret;
	}

	dev_info(&client->dev, "Crosslink loading successful!\n");
	return 0;
}

///	@brief Take the I2C lock when accessing the FPGA.
///	@param		client		I2C bus object.
///	@returns Returns a boolean that indicates that the lock was already in
///		possession.
int crosslink_lsc_lock(struct i2c_client *client) {
	struct crosslink_dev *sensor = crosslink_dev_from_i2c_client(client);
	int had_i2c_lock = sensor->has_i2c_lock;
	
	if( !had_i2c_lock ) {
		mutex_lock(&sensor->i2c_lock);
		i2c_lock_bus(client->adapter, I2C_LOCK_SEGMENT);
		sensor->has_i2c_lock = 1;
		mutex_unlock(&sensor->i2c_lock);
	}
	
	return had_i2c_lock;
}

///	@brief Release the I2C lock.
///	@param		client		I2C bus object.
///	@returns Always returns '0' for success.
int crosslink_lsc_unlock(struct i2c_client *client) {
	struct crosslink_dev *sensor = crosslink_dev_from_i2c_client(client);
	
	mutex_lock(&sensor->i2c_lock);
	i2c_unlock_bus(client->adapter, I2C_LOCK_SEGMENT);
	sensor->has_i2c_lock = 0;
	mutex_unlock(&sensor->i2c_lock);
	
	return 0;
}
