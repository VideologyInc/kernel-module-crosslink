"""

Open Boson camera at /dev/video1 GRAY16 format and capture a frame.
Save the frame (16bit) image and its normalized outputs to 16bit and 8bit image files.
And calculate PNSR among them to detect which ones are closer and which ones are more different.

Copyright (C) 2026 Videology
Programmed by Jianping Ye <jye@videologyinc.com>

Mar 26, 2026. Added calculate stats and linear transfrom function to be called by go2rtc.
Mar 23, 2026. Added percentile estimates to avoid 0 and linear transform formula outputs for 8bit and 16bit so that nnstreamer can use them.
Feb 12, 2026. Added 16bit to 8bit to 16bit conversion and PSNR calculation for raw, scaled, and normalized images.

"""

import cv2
import numpy as np
from glob import glob
from PIL import Image
import argparse

import struct


def show_telemetry(tel_line):
    """
    Given input telemetry line in 640 x 514 (the extra 2 lines of data in the image buffer), return baseline temperature in Celsius.

    Arguments:
    tel_line  --  numpy array of uint8 containing telemetry data.

    Returns:

    """

    tel_line = tel_line.astype(
        np.uint8
    ).tobytes()  # telemetry line seems to be bytes packed into the 14-bit values...
    cam_temp = struct.unpack_from("<H", tel_line, 96)[0]
    cam_temp = (cam_temp / 10.0) - 273.15
    print(f"Cam temp: {cam_temp}")


def calculate_psnr(src, tgt):
    """
    Given two image buffer, calculate its differences in PSNR.

    Arguments:
    src  --  Source input buffer of numpy array.
    tgt  --  Target input buffer of numpy array.

    Returns:
    float --  PSNR of the two images.

    Notes:
    High PSNR values (>=30 dB) means two images are very close.
    Low PSNR values (<=20) means two images are significant different.
    We measure 14bit to 16bit data preserving this way.
    14bit raw => 8bit linear transform => simple x 255 to get 16bit data.
    14bit raw to 16bit linear transform.
    Calculate PSNR of above two 16bit images and / or view their histograms to see that 14bit => 16bit will preserve data accuracy.

    """

    return cv2.PSNR(src, tgt)


# Calculate stats of the image and return tuple of (vmin, p025, p99, vmax)
def calculate_stats(img):
    """
    Given an input image, calculate its histogram percentile stats and return tuple of 4 values.

    Arguments:
    img  --  Input image buffer numpy array.

    Returns:
    (float,float,float,float) --  Tuple of percentiles = (minimum, percentile 0.2%, percentile 99%, maximum).

    Notes:
    The two percentile values are to avoid too many pixels at minimum (==0) and maximum (==255), which will affect contrast of other pixels with linear transform.

    """

    height = img.shape[0]
    img2 = img[:-2, :] if height == 514 else img

    percent_low = 0.2
    percent_high = 100
    img3 = img2[img2 != 0]
    vmin = np.amin(img3)
    vmax = max(np.amax(img3), 255.0)
    per_low, per_high = np.percentile(img3, [percent_low, percent_high])

    print(
        f"min = {vmin}, percent 0.2% = {per_low}, percent 99% = {per_high}, max = {vmax}"
    )
    return vmin, per_low, per_high, vmax


# Given 4 stat values, calculate linear transform alpha and beta of 8bits and 16bits, return tuple of (beta, alpha16, alpha8).
def calculate_linear_transform(vmin, per_low, per_high, vmax):
    """
    Given 4 stat values, calculate linear transform alpha and beta of 8bits and 16bits, return tuple of (beta, alpha16, alpha8).

    Arguments:
    vmin  --  Input minimum pixel float value of the image.
    per_low  --  Input low percentile float value of the image.
    per_high  --  Input high percentile float value of the image.
    vmax  --  Input maximum pixel float value of the image.

    Returns:
    (float,float,float) --  Tuple of (beta, alpha16, alpha8) to linear transform image data to 16bit and 8bit.

    Notes:
    Transform fomulae are as follows.

    out16 = (in14 - beta) * alpha16
    out8 = (in14 - beta) *alpha8

    """

    alpha16 = 65535.0 / max(vmax - per_low, 1.0)
    alpha8 = 255.0 / max(vmax - per_low, 1.0)
    print(f"Linear transform 14bit=>16bit: out = (in - {per_low}) * {alpha16}")
    print(f"Linear transform 14bit=>8bit:  out = (in - {per_low}) * {alpha8}")

    return per_low, alpha16, alpha8


# Save 16bit image to different output files.
def save_images(img, prefix, show_psnr=False):
    """
    Given input camera buffer, user specified prefix to save image, and flag to calculate PSNR, calculate image stats, do various linear transforms and optionally save images.

    Arguments:
    img  --  Input camera image buffer of numpy array.
    prefix -- Input file name prefix to save processed images. Default = "" will not save.
    show_psnr --    Bool flag to calculate PSNR between processed images.

    Returns:
    (float,float,float,float) --  Tuple of percentiles = (minimum, percentile 0.2%, percentile 99%, maximum).

    """

    height = img.shape[0]
    img2 = img[:-2, :] if height == 514 else img

    percent_low = 0.2
    percent_high = 100
    img3 = img2[img2 != 0]
    vmin = np.amin(img3)
    vmax = max(np.amax(img3), 255.0)
    per_low, per_high = np.percentile(img3, [percent_low, percent_high])
    print("min, max pixel value = ", vmin, ",", vmax)
    print(f"{percent_low}%, {percent_high}% pixel value  = ", per_low, ",", per_high)

    # Save 16bit img raw
    cv2.imwrite(prefix + "_16bit.png", img2)

    # Call cv2.normalize() and save.
    image_16bit_normalized = cv2.normalize(
        img2, None, 0, 65535, cv2.NORM_MINMAX
    ).astype(np.uint16)
    cv2.imwrite(prefix + "_normalize_16bit.tif", image_16bit_normalized)

    # Save image after simple scale
    # Should NOT call cv2.convertScaleAbs() here, because it outputs 8bit data.
    alpha = 65535.0 / vmax
    image_16bit_scaled = np.clip(img2 * alpha, 0, 65535).astype(np.uint16)

    cv2.imwrite(prefix + "_scale16_16bit.tif", image_16bit_scaled)

    # Standard linear transform = cv2.normalize()
    # out = (in - per_low) */ (vmax - per_low) * 65535
    alpha16 = 65535.0 / max(vmax - per_low, 1.0)
    alpha8 = 255.0 / max(vmax - per_low, 1.0)
    # print(f"Linear transform 14bit=>16bit: out = (in - {per_low}) * {alpha16}")
    # print(f"Linear transform 14bit=>8bit:  out = (in - {per_low}) * {alpha8}")
    image_16bit_linear = np.clip((img2 - per_low) * alpha16, 0, 65535).astype(np.uint16)

    cv2.imwrite(prefix + "_linear_16bit.tif", image_16bit_linear)

    # Normalize to 8bit and save.
    image_8bit = cv2.normalize(img2, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    cv2.imwrite(prefix + "_normalize_8bit.png", image_8bit)

    # Scale to 8bit and save.
    scale8 = 255.0 / vmax
    image_scale = cv2.convertScaleAbs(img2, alpha=scale8).astype(np.uint8)
    cv2.imwrite(prefix + "_scale8_8bit.png", image_scale)

    # Show and compare PSNR
    if not show_psnr:
        return vmin, per_low, per_high, vmax

    # 16bit psnr
    print(
        "PSNR 16bit raw to normalized    = ",
        calculate_psnr(image_16bit_normalized, img2),
    )
    print(
        "PSNR 16bit raw to scaled        = ", calculate_psnr(image_16bit_scaled, img2)
    )
    print(
        "PSNR 16bit scaled to normalized = ",
        calculate_psnr(image_16bit_normalized, image_16bit_scaled),
    )
    # 8bit psnr
    print("PSNR 8bit scaled to normalized  = ", calculate_psnr(image_scale, image_8bit))

    # Scale to scale
    print(
        "PSNR 8bit to 16bit scaled        = ",
        calculate_psnr(image_scale_16bit, image_16bit_scaled),
    )
    # Normalize to nomalize
    print(
        "PSNR 8bit to 16bit normalized    = ",
        calculate_psnr(image_16bit_normalized, image_norm_scale_16bit),
    )
    return vmin, per_low, per_high, vmax


# Open a Boson camera at 640 x 514 to get telemetry info from the extra 2 lines ;-)
# Calculate stats, optinally save images, and return linear transform beta, alpha16, alpha8.
# out16 = (in - beta) * alpha16
# out8 = (in - beta) * alpha8
def boson_show_telemetry(
    camera_number=0, width=640, height=514, prefix="", save_image=False
):
    """
    Given camera device number, desired width and height, prefix to save files, and flag to save image, open the camera with desired format, grab a buffer, calculate stats, and optionally show telemetry and save processed images.

    Arguments:
    camera_number  --  Camera number for OpenCV to open. On Linux 0 = /dev/video0, etc.
    width   --  Frame width.
    height  --  Frame height.
    prefix  --  Input file name prefix to save processed images. Default = "" will not save.
    save_image  --  Bool flag to save images. Default = False will only calculate stats.

    Returns:
    (float,float,float) --  Tuple of (beta, alpha16, alpha8) to linear transform image data to 16bit and 8bit, which are used by go2rtc.service live streaming. Or default values if camera can open but with frame error. Or raise an exception if camera cannot be opened.

    """

    # Default values of beta, alpha16 and alpha8, assuming input is 14bits (0, 16383)
    beta = 0.0
    alpha16 = 4.0  # 65535/16383
    alpha8 = 0.0155649  # 255 / 16363

    cap = cv2.VideoCapture(camera_number, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise SystemExit("Failed to open camera")

    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(
            cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"Y16 ")
        )  # can get this in gstreamer with "formatGRAY16_LE
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fcc = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        print(f"fcc: {fcc}")

        ret, img = cap.read()
        if img is None:
            print("something went wrong")
        else:
            # display(Image.fromarray(img))
            # display(Image.fromarray(cv2.normalize(img[:-2,:], None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)))
            # normalise so we can actually see something
            if height == 514:
                tel_line = img[-2, :]
                show_telemetry(tel_line)
            if prefix and save_image:
                print(img.shape, img.dtype)
                vmin, per_low, per_high, vmax = save_images(img, prefix)
            else:
                vmin, per_low, per_high, vmax = calculate_stats(img)
            beta, alpha16, alpha8 = calculate_linear_transform(
                vmin, per_low, per_high, vmax
            )

    finally:
        cap.release()

    return beta, alpha16, alpha8


# main function with boson at /dev/video1
# boson_show_telemetry(1, 514, "boson_640x514")

# Example Usage
if __name__ == "__main__":
    """
    boson_stats.py main() function.

    With user input arguments, the program opens Boson camera, grabs a frame, calculate and show stats, and optionally show telemetry data and save processed images.

    """

    parser = argparse.ArgumentParser(
        description="Calculate Boson Camera Stats",
        prog="boson_stats",
    )
    parser.add_argument(
        "-d", "--device", type=str, default="/dev/video0", help="camera device path"
    )
    parser.add_argument(
        "-s",
        "--save",
        type=int,
        default=0,
        help="1 = Save image files. Or default 0 = Calculate stats only.",
    )

    args = parser.parse_args()
    device_str = args.device
    dev_len = len("/dev/video")
    camera_id = int(device_str[dev_len:]) if len(device_str) > dev_len else 0

    boson_show_telemetry(camera_id, 320, 256, "images/boson_320x256", args.save)
