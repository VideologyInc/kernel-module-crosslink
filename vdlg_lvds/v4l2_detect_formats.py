#!/usr/bin/env python3

"""

File:   v4l2_detect_formats.py

2026.0326.  Added adaptive gray16 linear transform parameter calculation from boson_stats.py and fixtures of a few formats.
2026.0324.  Added Boson gray16 nnstreamer pipelines and object detection pipilines.
2026.0302.  Added Zoom Block camera format full list (resolution, fps, formats) from Visca commands.
2026.0227.  Detect formats by parsing from v4l2 command v4l2-ctl -d /dev/video0 --list-formats-ext outputs.

2026.0428.  Added functions to generate camera settings list compatible with Portal exclude all nnstreamer strings.

By:			jye@videologyinc.com

"""

import argparse
import subprocess
import re
import copy
import math
import json

from vdlg_lvds.detect_cameras_live import detect_camera_type, camera_dict
from vdlg_lvds.boson_stats import boson_show_telemetry as boson_calculate_linear

# Maximum resolution Scailx decoder h264 supports.
MAX_WIDTH = 1920
MAX_HEIGHT = 1080


Formats_Exclude_AR0234 = ["BGRA", "BGRx", "RGB"]
"""Global shutter camera: remove unwanted formats"""

Format_Exclude_List = ["NM12", "YUV4", "YM24"]
""" Camera formats to exclude from go2rtc stream list. """

Desc_Exclude_List = ["Bayer", "JPEG", "10-bit", "12-bit", "5-6-5"]
""" Camera description from v4l2-ctl --list-formats-ext command to exclude from go2rtc stream list. """

# Added a few Bayer formats, etc.
Fourcc_Dict = {
    "YUYV": "YUY2",
    "NV12": "NV12",
    "GREY": "GRAY8",
    "Y16 ": "GRAY16_LE",
    "RGB3": "RGB",
    "BGR3": "BGR",
    "XR24": "BGRx",
    "AR24": "BGRA",
    "NV12Gray8": "NV12GRAY8",
    "BA81": "rggb",
    "RGGB": "rggb",
    "GBRG": "gbrg",
    "GRBG": "grbg",
}
""" dict of v4l2 FOURCC to gstreamer pixel format string conversion. """

# Input framrrate is not important here because we'll videorate it to 10/1 ;-)
Object_Detection_List = [
    (320, 256, "GRAY8"),
    (320, 256, "GRAY16_LE"),
    (320, 256, "NV12"),
    (640, 512, "NV12"),
    (640, 512, "NV12GRAY8"),
]
""" List of resolution and format to add thermal and object detection pipelines. """


# Calculate stepwise closest value <=max if input > max.
def closest_value(val, istep, max_val):
    if val <= max_val:
        return val

    istep = max(istep, 1)
    # val > max_val => diff = val - max; ns = diff//istep; ret = val - ns*step
    ret = val - (val - max_val) // istep * istep

    return ret if ret <= max_val else ret - istep


def parse_v4l2_formats(device="/dev/video0"):
    """
    Given camera device path, run v4l2-crl --list-formats-ext command and parse camera's format information as output.

    Arguments:
    device  --  Input camera device path.

    Returns:
    list[dict] --  Parsed list of dict each containing camera's pixelformat, description and sizes information.

    """

    # Run the command
    cmd = f"v4l2-ctl -d {device} --list-formats-ext"
    try:
        output = subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        print("Device not found or error running v4l2-ctl")
        return []

    formats = []
    current_format = None

    # Regex patterns
    fmt_pattern = re.compile(r"\[\d+\]:\s+'(.+?)'\s+\((.+)\)")
    size_pattern = re.compile(r"Size:\s+Discrete\s+(\d+)x(\d+)")
    fps_pattern = re.compile(r"Interval:\s+Discrete\s+.*?\s+\(([\d\.]+)\s+fps\)")

    # For global shutter cameras etc.
    stepwise_pattern = re.compile(
        r"Size: Stepwise (\d+)x(\d+) - (\d+)x(\d+) with step (\d+)/(\d+)"
    )

    for line in output.splitlines():
        line = line.strip()

        # Match Format line
        fmt_match = fmt_pattern.search(line)
        if fmt_match:
            current_format = {
                "pixelformat": fmt_match.group(1),
                "description": fmt_match.group(2),
                "sizes": [],
            }
            formats.append(current_format)
            continue

        # Match Size line
        size_match = size_pattern.search(line)
        if size_match and current_format is not None:
            current_size = {
                "width": int(size_match.group(1)),
                "height": int(size_match.group(2)),
                "fps": [],
            }
            current_format["sizes"].append(current_size)
            continue

        # Parse Stepwise Sizes (minx, miny, maxx, maxy, stepx, stepy)
        if "Size: Stepwise" in line and current_format is not None:
            stepwise_match = stepwise_pattern.search(line)
            if stepwise_match:
                # res = f"Stepwise: {match.group(1)}x{match.group(2)} to {match.group(3)}x{match.group(4)}, Step: {match.group(5)}x{match.group(6)}"
                # Only use maximum resolution for now.
                w = closest_value(
                    int(stepwise_match.group(3)),
                    int(stepwise_match.group(5)),
                    MAX_WIDTH,
                )
                h = closest_value(
                    int(stepwise_match.group(4)),
                    int(stepwise_match.group(6)),
                    MAX_HEIGHT,
                )
                current_size = {
                    "width": w,
                    "height": h,
                    "fps": [],
                }
                current_format["sizes"].append(current_size)

        # Match FPS line
        fps_match = fps_pattern.search(line)
        if fps_match and current_format is not None:
            current_format["sizes"][-1]["fps"].append(float(fps_match.group(1)))

    return formats


# Given format list from above, filter out 3 big conditions:
# empty sizes, some special formats, and description containing Bayer, JPEG, 10-bit or 12-bit.
def formats_filter_out_unwanted(format_list):
    """
    Given input camera's format list from function parse_v4l2_formats(), remove some from exclude list.

    Arguments:
    format_list  --  Input camera format list from function parse_v4l2_formats().

    Returns:
    list[dict] --  Output format list to be further processed.

    """

    format_list_filtered = []
    for fdict in format_list:
        if fdict["pixelformat"] in Format_Exclude_List:
            continue
        if len(fdict["sizes"]) == 0:
            continue
        if any(sub in fdict["description"] for sub in Desc_Exclude_List):
            continue
        format_list_filtered.append(fdict)

    return format_list_filtered


# For Boson camera, add some formats.
def add_formats_boson(format_list):
    """
    Given input camera's format list from other functions, add a few special one to replace problematic 640 x 512 gray.

    Arguments:
    format_list  --  Input camera format list from other functions.

    Returns:
    list[dict] --  Output format list to be further processed.

    """

    for f in format_list:
        if f["pixelformat"] == "NV12":
            for sz in f["sizes"]:
                if sz["width"] == 640 and sz["height"] == 512:
                    # Add an extra NV12 to Gray8 format to the list
                    one = copy.deepcopy(f)
                    one["pixelformat"] = "NV12Gray8"
                    one["description"] = "NV12 to Gray8"
                    one["sizes"] = [sz]
                    format_list.append(one)
    # print(format_list)

    return format_list


# For Zoom Block cameras connecte to LVDS port, add fps = 25,30,50,60 and 1920 x 1080, plus 1280 x 720 to the list.
def add_formats_lvds(format_list):
    """
    Given input camera's format list from other functions, add a few for ZoomBlock cameras connected through LVDS .

    Arguments:
    format_list  --  Input camera format list from other functions.

    Returns:
    list[dict] --  Output format list to be further processed.

    """

    formats = {"YUYV": "YUYV 4:2:2", "NV12": "Y/UV 4:2:0"}
    resolution_list = [(1920, 1080), (1280, 720)]
    fps_list = [25.0, 30.0, 50.0, 60.0]
    # Add all combinations 2 x 2 x 4 = 16 total possible formats
    sample = {
        "pixelformat": "YUYV",
        "description": "YUYV 4:2:2",
        "sizes": [{"width": 1920, "height": 1080, "fps": [25.0]}],
    }

    format_list = []
    for f in formats.keys():
        for w, h in resolution_list:
            for fps in fps_list:

                print(f, w, h, fps)
                one = copy.deepcopy(sample)
                one["pixelformat"] = f
                one["description"] = formats[f]
                one["sizes"][0]["width"] = w
                one["sizes"][0]["height"] = h
                one["sizes"][0]["fps"][0] = fps
                format_list.append(one)

    return format_list


def fourcc_to_gst(fourcc_str):
    """
    Given input v4l2 FOURCC pixel format string, return its matching gstreamer string.

    Arguments:
    fourcc_str  --  Input FOURCC string from v4l2-ctl commands.

    Returns:
    str --  Output corresponding gstreamer format string.

    """

    if fourcc_str in Fourcc_Dict:
        return Fourcc_Dict[fourcc_str]
    else:
        return Fourcc_Dict["NV12"]


def v4l2_format_mapto_gst(format_list):
    """
    Given input camera format list from other functions, print their gstreamer format strings.

    Arguments:
    format_list  --  Input camera format list from other functions.

    Returns:

    """

    for fdict in format_list:
        print(fdict["pixelformat"], "=>", fourcc_to_gst(fdict["pixelformat"]))


# For Boson camera, given width, height, framerate, and format=GRAY16_LE, return nnstreamer pipeline str.
def boson_gray16_nnstreamer(w, h, fps, f_gst, out16=True, gray16_para=(0, 0, 0)):
    """
    Given input Boson camera gray16 format features and calculated stats from boson_stats.py, output its gstreamer + nnstreamer pipeline string.

    Arguments:
    w  --  Input frame width int.
    h  --  Input frame height int.
    fps  --  Input frame rate int.
    f_gst   --  Input format gstreamer string.
    out16   --  Bool flag = True to generate true gray16 format string. Or = False to generate gray8 string instead.
    gray16_para --  Tuple (beta, alpha16, alpha8) from function boson_stats.boson_show_telemetry().

    Returns:
    str --  Output gstreamer string using nnstreamer pipeline.

    """

    # Always need this to avoid gst crash if using same width and height as input.
    ww = 320
    hh = 320
    # These 2 values are calculated based on boson_stats.py output.
    # out = (in - vmin) / (vmax - vmin) * 65535; (or *255 for 8bits)
    # beta = -5474.0
    # alpha = 112.77 if out16 else 0.43878
    # This gray16_para is calculated by calling boson_stats functions from a gray16 Boson camera frame.
    beta, alpha16, alpha8 = gray16_para

    # out16 = (in - beta) * alpha16
    # out8 = (in - beta) * alpha8
    alpha = alpha16 if out16 else alpha8
    beta = -beta

    cmax = 65535.0 if out16 else 255.0
    outype = "uint16" if out16 else "uint8"
    outformat = "GRAY16_LE" if out16 else "GRAY8"

    s = (
        rf"video/x-raw,width={w},height={h},framerate={fps}/1,format={f_gst} ! "
        r"videorate max-rate=10 ! video/x-raw,framerate=10/1 ! "
        r"queue leaky=2 max-size-buffers=10 ! "
        rf"videoscale ! video/x-raw, width={ww}, height={hh} ! "
        r"tensor_converter ! "
        rf"tensor_transform mode=arithmetic option=typecast:float32,add:{beta},mul:{alpha} ! "
        r"queue leaky=2 max-size-buffers=10 ! "
        rf"tensor_transform mode=clamp option=0.0:{cmax} ! "
        rf"tensor_transform mode=typecast option={outype} ! "
        r"queue leaky=2 max-size-buffers=10 ! "
        rf"tensor_decoder mode=direct_video option1={outformat} ! "
    )

    return s


# Given tflite model name and label txt file name, return nnstreamer str before compositing.
# Two options inside:
# Do videoconvert and no videoscale
# OR do videoscale and scale back and no videoconvert.
def object_detection_nnstreamer(
    w=320, h=256, use_scale=False, use_npu=False, use_float=True
):
    """
    Given input camera features and a few option flags, generate object detection gstreamer string as output.

    Arguments:
    w  --  Input frame width int.
    h  --  Input frame height int.
    use_scale   --  Bool flag = True to use tensor_decoder option4 to match input frame resolution. = False to use tensor default resolution instead.
    use_npu     --  Bool flag = True to use NPU in tensor_filter or = False to use CPU only.
    use_float   --  Bool flag = True to use float AI model for object detection. Or = False to use int model for thermal detection.

    Returns:
    str --  Output gstreamer string using nnstreamer pipeline to do object or thermal detection with optional NPU speed-up.

    """

    if use_float:
        model_name = "/opt/imx8-isp/boson/yolov8n_float16.tflite"
        label_name = "/opt/imx8-isp/boson/coco.txt"
    else:
        model_name = "/opt/imx8-isp/boson/thermal_yolov8n_320.tflite"
        label_name = "/opt/imx8-isp/boson/thermal.txt"

    # Handle convert or scale differently to maintain speed for 320 and display quality for 640 ;-)
    spre = (
        "videoscale method=0 ! video/x-raw,width=320,height=320"
        if use_scale
        else "videoconvert ! video/x-raw,format=RGB"
    )
    # spost = f"queue leaky=2 max-size-buffers=10 ! videoscale method=0 ! video/x-raw,width={w},height={h} !" if use_scale else ""
    npu_str = (
        "custom=Delegate:External,ExtDelegateLib:libvx_delegate.so accelerator=true:npu"
        if use_npu
        else ""
    )

    # Use tensor decoder option4 to scale bounding boxes back to original dim if pre-scaled.
    stdecoder = (
        f"tensor_decoder mode=bounding_boxes option1=yolov8 option2={label_name} option4={w}:{h} option5=320:320 ! "
        if use_scale
        else f"tensor_decoder mode=bounding_boxes option1=yolov8 option2={label_name} option4=320:320 option5=320:320 ! "
    )

    sfloat = (
        "tensor_transform mode=arithmetic option=typecast:float32,add:0.0,div:255.0 ! "
        "queue leaky=2 max-size-buffers=10 ! "
        f"tensor_filter latency=1 framework=tensorflow2-lite model={model_name} "
        f"{npu_str}"
        " ! tensor_transform mode=transpose option=1:0:2:3 ! "
        "queue leaky=2 max-size-buffers=10 ! "
        f"{stdecoder}"
    )

    sint = (
        "queue leaky=2 max-size-buffers=10 ! "
        f"tensor_filter latency=1 framework=tensorflow2-lite model={model_name} "
        f"{npu_str}"
        " ! tensor_transform mode=transpose option=1:0:2:3 ! "
        "queue leaky=2 max-size-buffers=10 ! "
        "tensor_transform mode=arithmetic option=typecast:float32,add:-17.0,mul:0.0063448 ! "
        f"{stdecoder}"
    )
    stensor = sfloat if use_float else sint

    s = (
        "tee name=t "
        "t. ! queue leaky=2 max-size-buffers=10 ! "
        f"{spre} ! "
        "tensor_converter ! "
        f"{stensor}"
        f"videoconvert ! mix.sink_0 "
        "t. ! queue leaky=2 max-size-buffers=10 ! videoconvert ! mix.sink_1 "
        "compositor name=mix sink_0::zorder=2 sink_1::zorder=1 ! videoconvert"
    )
    return s


# Match w x h x fps x format to list to add object detection
def object_detection_gst(
    w, h, fps, f_gst, use_npu=False, use_float=True, gray16_para=(0, 0, 0)
):
    """
    Given input camera features, gray16 linear transform stats and a few option flags, generate object detection gstreamer string as output.

    Arguments:
    w  --  Input frame width int.
    h  --  Input frame height int.
    fps  --  Input frame rate int.
    f_gst   --  Input format gstreamer string.
    use_npu     --  Bool flag = True to use NPU in tensor_filter or = False to use CPU only.
    use_float   --  Bool flag = True to use float AI model for object detection. Or = False to use int model for thermal detection.
    gray16_para --  Tuple (beta, alpha16, alpha8) from function boson_stats.boson_show_telemetry().

    Returns:
    str --  For one of available combinations (gray16 vs regular, 320 vs 640, float model vs int model, etc.), the valid gstreamer string.

    """

    if (w, h, f_gst) not in Object_Detection_List:
        return

    if w == 320:
        # width is close to tensor 320 x 320, do scale pre-process and convert to RGB internally.
        if f_gst == "GRAY16_LE":
            return boson_gray16_nnstreamer(
                w, h, fps, f_gst, False, gray16_para
            ) + object_detection_nnstreamer(w, h, False, use_npu, use_float)
        else:
            # Scale to match tensor 320 x 320.
            s_scale = (
                f"video/x-raw,format={f_gst},width={w},height={h},framerate={fps}/1 ! "
                "videorate max-rate=10 ! video/x-raw,framerate=10/1 ! "
                "queue leaky=2 max-size-buffers=10 ! videoscale method=0 ! video/x-raw,width=320,height=320 ! "
            )
            return s_scale + object_detection_nnstreamer(
                w, h, False, use_npu, use_float
            )
    else:
        # width is far different from 320 x 320, do convert outside and scale / rescale inside before and after tensor.
        if f_gst == "GRAY16_LE":
            return boson_gray16_nnstreamer(
                w, h, fps, f_gst, False, gray16_para
            ) + object_detection_nnstreamer(w, h, True, use_npu, use_float)
        else:
            # Convert to RGB
            if f_gst == "NV12GRAY8":  # f_gst=="NV12GRAY8"
                # Special case: convert NV12 to GRAY8 before nnstreamer pipeline.
                s_convert = (
                    f"video/x-raw,format=NV12,width={w},height={h},framerate={fps}/1 ! "
                    "videorate max-rate=10 ! video/x-raw,framerate=10/1 ! "
                    "queue leaky=2 max-size-buffers=10 ! videoconvert ! video/x-raw,format=GRAY8 ! "
                    "queue leaky=2 max-size-buffers=10 ! videoconvert ! video/x-raw,format=RGB ! "
                )
            else:
                s_convert = (
                    f"video/x-raw,format={f_gst},width={w},height={h},framerate={fps}/1 ! "
                    "videorate max-rate=10 ! video/x-raw,framerate=10/1 ! "
                    "queue leaky=2 max-size-buffers=10 ! videoconvert ! video/x-raw,format=RGB ! "
                )
            return s_convert + object_detection_nnstreamer(
                w, h, True, use_npu, use_float
            )


# Given one format dict, return its gstreamer string.
# Now use camera_type to handle Boson camera GRAY16_LE using nnstreamer pipeline.
def v4l2_format_to_gst(
    format_dict, camera_type="", add_object_detection=False, gray16_para=(0, 0, 0)
):
    """
    Given one format dict, camera type and flag to add AI detection, gray16 stats, return its gstreamer string list.

    Arguments:
    format_dict  --  Input one format dict with multiple sizes.
    camera_type  --  Camera type string.
    add_object_detection    --  Bool flag to add AI object detection to the stream list for go2rtc.
    gray16_para --  Tuple (beta, alpha16, alpha8) from function boson_stats.boson_show_telemetry().

    Returns:
    list[int, int, str, str] --  Output list of tuples each = (width, height, format description, gstreamer long string).

    Notes:
    (width, height, format description) will be the key of the dict in go2rtc stream list.
    So they must be unique.

    """

    s_list = []
    obj_list = []

    for sz in format_dict["sizes"]:
        # Make sure we have these keys in dict.
        if ("width" not in sz) or ("height" not in sz):
            continue
        if "fps" not in sz:
            continue

        w = sz["width"]
        h = sz["height"]
        if w == 0 or h == 0:
            continue

        # print(sz)

        # No fps field. Set to 60.
        fps = 60 if (sz["fps"] == []) else int(math.ceil(sz["fps"][0]))
        f = format_dict["pixelformat"]
        f_gst = fourcc_to_gst(f)

        # Skip some slow formats of global shutter camera.
        if camera_type == "ar0234" and f_gst in Formats_Exclude_AR0234:
            continue

        if camera_type == "boson" and f_gst == "GRAY16_LE":
            # Boson gray16 special treatment.
            s8 = (
                boson_gray16_nnstreamer(w, h, fps, f_gst, False, gray16_para)
                + "videoconvert "
            )
            s16 = (
                boson_gray16_nnstreamer(w, h, fps, f_gst, True, gray16_para)
                + "videoconvert "
            )
            t8 = (w, h, f"fps={fps},format={f_gst}, out=8bit", s8, fps)
            t16 = (w, h, f"fps={fps},format={f_gst}, out=16bit", s16, fps)
            s_list.append(t8)
            s_list.append(t16)
        # elif f_gst == "NV12GRAY8":
        #    s = f"video/x-raw,width={w},height={h},framerate={fps}/1,format=NV12 ! videoconvert ! video/x-raw,format=GRAY8 ! videoconvert"
        #    t = (w, h, f"fps={fps},format={f_gst}", s, fps)
        #    s_list.append(t)
        else:
            # Regular gst string.
            s = f"video/x-raw,width={w},height={h},framerate={fps}/1,format={f_gst} ! videoconvert"
            t = (w, h, f"fps={fps},format={f_gst}", s, fps)
            s_list.append(t)

        # Add object detection gst str if required.
        if add_object_detection and camera_type == "boson":
            sobj = object_detection_gst(w, h, fps, f_gst, False, True, gray16_para)
            sthermal = object_detection_gst(w, h, fps, f_gst, False, False, gray16_para)
            if sobj:
                tobj = (w, h, f"fps={fps},format={f_gst}, AI yolov8n", sobj, fps)
                obj_list.append(tobj)
            if sthermal:
                tobj = (w, h, f"fps={fps},format={f_gst}, AI thermal", sthermal, fps)
                obj_list.append(tobj)

    return s_list + obj_list


# Given camera device path, return supported gstreamer str list.
def camera_to_gst_list(device):
    """
    Given camera device path, return its full supported format info list containing gstreamer strings.

    Arguments:
    device  --  Input camera device path such as /dev/video0.

    Returns:
    list[int, int, str, str] --  Output list of tuples each = (width, height, format description, gstreamer long string).

    Notes:
    The output list will be used by go2rtc directly to be appeared on webRTC port 1984 stream list.

    """

    camera_type, cam_path = detect_camera_type(device)
    # print(camera_type)

    camera_formats = formats_filter_out_unwanted(parse_v4l2_formats(device))

    if camera_type == "zoomblock":
        # Add full resolution and framerate support for ZoomBlock (from visca commands)
        print("Create new format list for ZoomBlock cameras.")
        camera_formats = add_formats_lvds(camera_formats)

    # print(json.dumps(camera_formats, indent=2))

    # For Boson camera, grab one frame of gray16 format and calculate stats for linear transform of gray16 => 16bit and 8bit
    if camera_type == "boson":
        dev_len = len("/dev/video")
        camera_id = int(device[dev_len:]) if len(device) > dev_len else 0
        gray16_para = boson_calculate_linear(camera_id, 320, 256)
        # camera_formats = add_formats_boson(camera_formats)
    else:
        # Default 14bits to 16bits and 8bits tuple
        gray16_para = (0, 4.0, 0.0155649)

    info_list = []
    for fd in camera_formats:
        s_list = v4l2_format_to_gst(fd, camera_type, True, gray16_para)
        info_list += s_list

    return info_list


# Given camera device path, return its supported list of settings compatible with Portal.
def camera_to_setting_list(device):
    camera_type, cam_path = detect_camera_type(device)
    # print(camera_type)

    camera_formats = formats_filter_out_unwanted(parse_v4l2_formats(device))

    if camera_type == "zoomblock":
        # Add full resolution and framerate support for ZoomBlock (from visca commands)
        print("Create new format list for ZoomBlock cameras.")
        camera_formats = add_formats_lvds(camera_formats)

    # Skip all info using nnstreamer now for camera input settings.
    setting_list = []
    for fd in camera_formats:
        for sz in fd["sizes"]:
            # Make sure we have these keys in dict.
            if ("width" not in sz) or ("height" not in sz):
                continue
            if "fps" not in sz:
                continue

            w = sz["width"]
            h = sz["height"]
            if w == 0 or h == 0:
                continue

            # print(sz)

            # No fps field. Set to 60.
            fps = 60 if (sz["fps"] == []) else int(math.ceil(sz["fps"][0]))
            f = fd["pixelformat"]
            f_gst = fourcc_to_gst(f)

            # Skip some slow formats of global shutter camera.
            if camera_type == "ar0234" and f_gst in Formats_Exclude_AR0234:
                continue

            # Regular gst string.
            # s = f"video/x-raw,width={w},height={h},framerate={fps}/1,format={f_gst} ! videoconvert"
            # t = (w, h, f"fps={fps},format={f_gst}", s, fps)
            one = {}
            one["format"] = f_gst
            one["fps"] = fps
            one["resolution"] = f"{w}x{h}"
            one["device"] = device
            setting_list.append(one)

    return setting_list


# Example Usage
if __name__ == "__main__":
    """
    v4l2_detect_formats.py main() function.

    With user input argument of camera device path, this program calls v4l2 command to parse all supported formats, optinally add special gray16 formats and AI model nnstreamer pipelines to the final go2rtc stream list.

    """

    parser = argparse.ArgumentParser(
        description="Detect camera formats by parsing v4l2 command outputs",
        prog="v4l2_detect_formats",
    )
    parser.add_argument(
        "-d", "--device", type=str, default="/dev/video0", help="camera device path"
    )

    # Default is False.
    parser.add_argument(
        "-s",
        "--settings",
        action="store_true",
        help="generate and show camera settings only. Default = False.",
    )

    args = parser.parse_args()

    if args.settings:
        # Get and show camera settings compatible with Portal.
        settings_list = camera_to_setting_list(args.device)

        for one_setting in settings_list:
            print(one_setting)
    else:
        # Get go2RTC version of camera formats list containing gstreamer strings.
        info_list = camera_to_gst_list(args.device)

        for info in info_list:
            print(info)
