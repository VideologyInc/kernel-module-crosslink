import argparse
from time import sleep
from vdlg_lvds.ioctl import *
import fcntl
import glob

# Fixed measurement values set within the LVDS-MIPI Crosslink FPGA
PIXEL_CNT_MAX = 65536
PIXEL_CNT_AMOUNT = 10
PIXEL_CNT_FPGA_CLK_FREQ = 24

def pixel_cnt(freq_mhz: float) -> int:
    return int(round((PIXEL_CNT_MAX * PIXEL_CNT_AMOUNT * PIXEL_CNT_FPGA_CLK_FREQ) / freq_mhz))

# Camera pixel frequencies supported [MHz]
PAL_FREQS_MHZ = (
    148.5,
    74.25,
    37.125,
    20.576,
)

NTSC_FREQS_MHZ = tuple(f / 1.001 for f in (
    148.5,
    74.25,
    37.125,
))

# Pixel clock periods (microseconds)
camera_pixel_periods_pal = tuple(1 / f for f in PAL_FREQS_MHZ)
camera_pixel_periods_ntsc = tuple(1 / f for f in NTSC_FREQS_MHZ)

# Expected pixel clock counts per frequency
camera_pixel_counts_pal = tuple(pixel_cnt(f) for f in PAL_FREQS_MHZ)
camera_pixel_counts_ntsc = tuple(pixel_cnt(f) for f in NTSC_FREQS_MHZ)

# High (+10%)
camera_pixel_counts_pal_high = tuple(x * 1.1 for x in camera_pixel_counts_pal)
camera_pixel_counts_ntsc_high = tuple(x * 1.1 for x in camera_pixel_counts_ntsc)

# Low (-10%)
camera_pixel_counts_pal_low = tuple(x * 0.9 for x in camera_pixel_counts_pal)
camera_pixel_counts_ntsc_low = tuple(x * 0.9 for x in camera_pixel_counts_ntsc)

def get_resolution(dev):
    ioctl_serial = LvdsIoctlSerial()
    with open(dev) as f:
        fcntl.ioctl(f, LVDS_CMD_GET_LINE_COUNT, ioctl_serial)
        vres = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_COLM_COUNT, ioctl_serial)
        hres = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_FRAME_PERIOD, ioctl_serial)
        period_estimation = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_HF_CNT, ioctl_serial)
        hf_cnt = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_PIX_CNT, ioctl_serial)
        pix_cnt = ioctl_serial.len
        fcntl.ioctl(f, LVDS_CMD_GET_VIDEOFORMAT, ioctl_serial)
        video_format = ioctl_serial.len

        # PAL
        if (video_format == 0):
            for i, pixel_period in enumerate(camera_pixel_periods_pal):
                if camera_pixel_counts_pal_low[i] < hf_cnt < camera_pixel_counts_pal_high[i]:
                    frame_rate = 1_000_000.0 / (pix_cnt * pixel_period)
                    print(f"{hres} x {vres} @ {frame_rate:.1f}")
                    return
        # NTSC
        if (video_format == 1):
            for i, pixel_period in enumerate(camera_pixel_periods_ntsc):
                if camera_pixel_counts_ntsc_low[i] < hf_cnt < camera_pixel_counts_ntsc_high[i]:
                    frame_rate = 1_000_000.0 / (pix_cnt * pixel_period)
                    print(f"{hres} x {vres} @ {frame_rate:.2f}")
                    return
        
        # If no supported pixel frequency was detected, return frequency estimation from Crosslink
        frame_rate = 1_000_000.0 / period_estimation
        print(f"{hres} x {vres} @ {frame_rate:.1f}")

def main():
    parser = argparse.ArgumentParser(description="Get current LVDS camera resolution")
    lvds_devs = glob.glob("/dev/links/lvds*")
    default_lvds = lvds_devs[0] if lvds_devs else "/dev/v4l-subdev1"
    parser.add_argument("-d", "--dev", type=str, default=default_lvds, help="Device path")
    args = parser.parse_args()
    get_resolution(args.dev)

if __name__ == "__main__":
    main()
