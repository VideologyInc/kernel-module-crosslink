#! /usr/bin/env python3
# this was a test to try to burn a lattice bitfile to a crosslink device based on the instruction pseudocode in
# the appendix of the [Crosslink programming manual](https://www.latticesemi.com/-/media/LatticeSemi/Documents/ApplicationNotes/AD2/FPGA-TN-02014-1-6-CrossLink-Programming-Config-User-Guide.ashx?document_id=51655)
# the status read and similar commands seem to work, but the bitfile-sending does not. Here I am splitting it into
# 8K chunks as the spi-dev driver has a 16bit buffer-len field. I added _I2C_NOSTART flag, but that didnt help.
# Ideally we would also be able to use the flash programming commands, but I'm not sure how that would work. I'm assuming
# that programming commands other than write_burst send chunks instead of the whole thing, probably with an address.
# next effort would then be to use the sysconfig slave-i2c code provided with Diamond programming tools, but that doesn't include a i2c-dev example.

from periphery import I2C, GPIO
from time import sleep, process_time
import sys

SYSCONFIG_STATUS_DONE	= 1<<8
SYSCONFIG_STATUS_BUSY	= 1<<12
SYSCONFIG_STATUS_FAIL	= 1<<13
SYSCONFIG_STATUS_ERR	= (1<<25 | 1<<23)

CROSSLINKPLUS_IDCODE = 0x43002F01
CROSSLINK_IDCODE     = 0x43002C01

# get creset GPIO:
creset = GPIO("/dev/gpiochip5", 1, "out")
# get I2C bus
i2c = I2C("/dev/i2c-1")

def lsc_get_status(i2c: I2C, addr: int):
    lsc_status_msgs = [I2C.Message([0x3C,0x00,0x00,0x00]),I2C.Message([0x00,0x00,0x00,0x00], read=True)]
    i2c.transfer(addr, lsc_status_msgs)
    return int.from_bytes(lsc_status_msgs[1].data, byteorder='big', signed=False)

def lsc_send_opcode(i2c: I2C, addr: int, code):
    lsc_opcode_msgs = [I2C.Message([code,0x00,0x00,0x00])]
    i2c.transfer(addr, lsc_opcode_msgs)

# open bitfile:
def open_bitfile(filename):
    bitfile_msgs = []
    with open(filename, 'rb') as f:
        b = f.read()
        bitfile = b"\x7A\x00\x00\x00" + b
        # Limit for I2C WR_IOCTL is 43 msgs of max 8K each = 344K. We need to send 164k,  so 8k is the only sizxe that works.
        n = 8192
        chunks = [bitfile[i:i+n] for i in range(0, len(bitfile), n)]
        bitfile_msgs = [I2C.Message(chunks[0])] + [I2C.Message(c, flags=I2C._I2C_M_NOSTART) for c in chunks[1:]]

    # return if we dont have data.
    if len(bitfile_msgs) < 2:
        print("bitfile is empty")
        exit(1)
    return bitfile_msgs

def main():
    #Steps
    ##### set CRESET high
    creset.write(bool(1))
    print("reset high")

    ##### Wait 1s
    sleep(0.01)
    print("sleep 10ms")

    # set CRESET low
    creset.write(bool(0))
    print("reset low")
    # Wait 1s
    # sleep(1.0)
    sleep(0.1)
    print("sleep 100ms")
    # Shift in Activation Key
    initialise_msgs = [I2C.Message([0xA4,0xC6,0xF4,0x8A])]
    i2c.transfer(0x40, initialise_msgs)
    print("xfer activation msg")
    # set CRESET high
    creset.write(bool(1))
    print("rest high")

    # Wait 10 ms
    sleep(0.001)
    print("sleep 1ms")

    # Shift in IDCODE (0xE0) opcode and shift out DEVICE_ID
    idcode_msgs = [I2C.Message([0xE0,0x00,0x00,0x00]),I2C.Message([0x00,0x00,0x00,0x00], read=True)]
    i2c.transfer(0x40, idcode_msgs)
    print("get ID code")
    # get u32 from bytes returned
    id = int.from_bytes(idcode_msgs[1].data, byteorder='little', signed=False)
    print(f"device id received: {hex(id)}. Expecting {hex(CROSSLINKPLUS_IDCODE)} or {hex(CROSSLINK_IDCODE)}")

    # Shift in ENABLE (0xC6) instruction
    lsc_send_opcode(i2c, 0x40, 0xC6)                    ##################
    print("send ENABLE C6")
    # Wait 1 ms
    sleep(0.001)
    print("sleep 1ms")

    # Shift in ERASE (0x0E) instruction
    lsc_send_opcode(i2c, 0x40, 0x0E)                    ##################
    print("send ERASE")
    # idcode_msgs = [I2C.Message([0xE0,0x00,0x00,0x00]),I2C.Message([0x00,0x00,0x00,0x00], read=True)]
    # i2c.transfer(0x40, idcode_msgs)

    # # Wait 50 ms
    sleep (0.01)
    print("sleep 10ms")
    # # Wait 5000 ms
    # sleep (5.0)

    start_time = process_time()
    while True:
        print("waiting for erase")
        sleep(0.2)
        stat = lsc_get_status(i2c, 0x40)
        print(f"stat received: {hex(stat)}. Expecting 0x0000 with mask 0x3000 = {hex(stat&0x3000)}")
        if (stat & SYSCONFIG_STATUS_BUSY) == SYSCONFIG_STATUS_BUSY:
            ellapsed = process_time() - start_time
            print(f"busy. been waiting for {ellapsed:.2f}s")
            if ellapsed > 10.0:
                print("been waiting too long. Exiting")
                exit
        else:
            break

    # Shift in LSC_READ_STATUS (0x3C) instruction
    # "Expected Value: 0x00000000
    stat = lsc_get_status(i2c, 0x40)
    print(f"stat received: {hex(stat)}. Expecting 0x0000 with mask 0x3000 = {hex(stat&0x3000)}")
    if stat & 0x3000 != 0x0:
        print(f"stat wrong. {stat}")
        exit(1)

    # Shift in LSC_INIT_ADDRESS (0x46) instruction
    print(f"sending init address")
    lsc_send_opcode(i2c, 0x40, 0x46)


    # Shift in LSC_BITSTREAM_BURST (0x7A) instruction
    # lsc_send_opcode(i2c, 0x40, 0x7A)

    # Shift in bitstream (.bit) generated by Diamond Software
    if id == CROSSLINKPLUS_IDCODE:
        bitfile_msgs = open_bitfile('/lib/firmware/LVDS_MIPI_bridge_MDF6000_b4.bit')
    elif id == CROSSLINK_IDCODE:
        bitfile_msgs = open_bitfile('/lib/firmware/LVDS_MIPI_bridge_MD6000_b4.bit')
    else:
        print("ID code not known. Exiting")
        exit(1)
    print(f"transfering bitfile: {len(bitfile_msgs)} messages")
    i2c.transfer(0x40, bitfile_msgs)
    print(f"bitfile sent")

    # Wait 10 ms
    sleep(0.01)

    # Shift in USERCODE (0xC0) instruction
    # usercode_msgs = [I2C.Message([0xC0,0x00,0x00,0x00]),I2C.Message([0x00,0x00,0x00,0x00], read=True)]
    # i2c.transfer(0x40, usercode_msgs)
    # usercode = int.from_bytes(usercode_msgs[1].data, byteorder='big', signed=False)
    # print(f"usercode: {hex(usercode)}")

    # Shift in LSC_READ_STATUS (0x3C) instruction
    stat = lsc_get_status(i2c, 0x40)
    print(f"stat received after prog: {hex(stat)}. Expecting 0x0100 with mask 0x3100 = {hex(stat&0x3100)}")
    # "Expected Value from 0x0100 with the Mask: 0x3100
    if stat & 0x3100 != 0x0100:
        print(f"stat wrong. {hex(stat)}")
        # exit(1)

    # Shift in DISABLE (0x26) instruction
    print(f"send disable")
    lsc_send_opcode(i2c, 0x40, 0x26)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if "s" in sys.argv[1]:
            stat = lsc_get_status(i2c, 0x40)
            print(f"stat received: {hex(stat)}.")
        elif "r" in sys.argv[1]:
            val = creset.read()
            creset.write(bool(not val))
        elif "i" in sys.argv[1]:
            idcode_msgs = [I2C.Message([0xE0,0x00,0x00,0x00]),I2C.Message([0x00,0x00,0x00,0x00], read=True)]
            i2c.transfer(0x40, idcode_msgs)
            # get u32 from bytes returned
            id = int.from_bytes(idcode_msgs[1].data, byteorder='little', signed=False)
            print(f"device id: {hex(id)}")
        elif "x" in sys.argv[1]:
            initialise_msgs = [I2C.Message([0xA4,0xC6,0xF4,0x8A])]
            i2c.transfer(0x40, initialise_msgs)
        else:
            code = int(sys.argv[1], 16)
            lsc_send_opcode(i2c, 0x40, code)
    else:
        main()

