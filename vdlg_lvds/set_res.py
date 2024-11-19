import argparse
from time import sleep
from vdlg_lvds.serial import LvdsSerial

resolution_commands = {
    "sony": {
        "720p25": ["81010424720101FF", "81010424740000FF", "8101041903FF"],
        "720p30": ["8101042472000FFF", "81010424740000FF", "8101041903FF"],
        "720p50": ["8101042472000CFF", "81010424740000FF", "8101041903FF"],
        "720p60": ["8101042472000AFF", "81010424740000FF", "8101041903FF"],
        "1080p25": ["81010424720008FF", "81010424740000FF", "8101041903FF"],
        "1080p30": ["81010424720007FF", "81010424740000FF", "8101041903FF"],
        "1080p50": ["81010424720104FF", "81010424740001FF", "8101041903FF"],
        "1080p60": ["81010424720105FF", "81010424740001FF", "8101041903FF"],
    },
    "wonwoo": {
    "720p25": ["81010424720101FF", "81010424740000FF"],
    "720p30": ["8101042472000EFF", "81010424740000FF"],
    "720p50": ["8101042472000CFF", "81010424740000FF"],
    "720p60": ["81010424720009FF", "81010424740000FF"],
    "1080p25": ["81010424720008FF", "81010424740000FF"],
    "1080p30": ["81010424720006FF", "81010424740000FF"],
    "1080p50": ["81010424720104FF", "81010424740001FF"],
    "1080p60": ["81010424720103FF", "81010424740001FF"],
    }
}
brands = {
    "sony": "0711",
    "wonwoo": "0466"
}

def poll_command(serial_device, command, retries=2, delay=0.1):
    for _ in range(retries):
        response = serial_device.transceive(bytearray.fromhex(command)).hex()
        if "9041ff" in response:
            return response
        sleep(delay)
    raise RuntimeError(f"Failed to execute command: {command}")

def detect_camera_brand(serial_device):
    response = serial_device.transceive(bytearray.fromhex("81090002FF")).hex()
    for brand, code in brands.items():
        if code in response:
            print(f"Camera ID response: {response}.\nDetected {brand.upper()} zoomblock")
            return brand
    raise ValueError(f"Unknown camera: {response}")

def set_resolution(serial_device, resolution, brand):
    if brand.lower() not in resolution_commands:
        raise ValueError(f"Unsupported camera: {brand}")
    else:
        if resolution not in resolution_commands[brand.lower()]:
            raise ValueError(f"Unsupported resolution: {resolution}")
        else:
            commands = resolution_commands[brand].get(resolution)
            for command in commands:
                retry = 20 if "1041903" in command else 2
                res = poll_command(serial_device, command, retries=retry)
                print(f"cmd: {command}, res: {res}")

def main():
    parser = argparse.ArgumentParser(description="Set camera resolution via LvdsSerial")
    parser.add_argument("resolution", type=str, help="Resolution in the form of '720p60'")
    parser.add_argument("-d", "--dev", type=str, default="/dev/v4l-subdev1", help="Device path")
    args = parser.parse_args()

    serial_device = LvdsSerial(args.dev)
    brand = detect_camera_brand(serial_device)
    set_resolution(serial_device, args.resolution, brand)

if __name__ == "__main__":
    main()
