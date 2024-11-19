import argparse
from vdlg_lvds.serial import LvdsSerial
from time import sleep

SONY_RESOLUTIONS = {
    "720p25": ["81010424720101FF", "81010424740000FF", "8101041903FF"],
    "720p30": ["8101042472000FFF", "81010424740000FF", "8101041903FF"],
    "720p50": ["8101042472000CFF", "81010424740000FF", "8101041903FF"],
    "720p60": ["8101042472000AFF", "81010424740000FF", "8101041903FF"],
    "1080p25": ["81010424720008FF", "81010424740000FF", "8101041903FF"],
    "1080p30": ["81010424720007FF", "81010424740000FF", "8101041903FF"],
    "1080p50": ["81010424720104FF", "81010424740001FF", "8101041903FF"],
    "1080p60": ["81010424720105FF", "81010424740001FF", "8101041903FF"],
}

WONWOO_RESOLUTIONS = {
    "720p25": ["81010424720101FF", "81010424740000FF"],
    "720p30": ["8101042472000EFF", "81010424740000FF"],
    "720p50": ["8101042472000CFF", "81010424740000FF"],
    "720p60": ["81010424720009FF", "81010424740000FF"],
    "1080p25": ["81010424720008FF", "81010424740000FF"],
    "1080p30": ["81010424720006FF", "81010424740000FF"],
    "1080p50": ["81010424720104FF", "81010424740001FF"],
    "1080p60": ["81010424720103FF", "81010424740001FF"],
}

def detect_camera_brand(serial_device):
    response = serial_device.transceive(bytearray.fromhex("81090002FF"))
    if b"0711" in response:
        return "Sony"
    elif b"0466" in response:
        return "Wonwoo"
    else:
        raise ValueError(f"Unknown camera: {response}")

def set_resolution(serial_device, resolution, brand):
    if brand == "Sony":
        commands = SONY_RESOLUTIONS.get(resolution)
    elif brand == "Wonwoo":
        commands = WONWOO_RESOLUTIONS.get(resolution)
    else:
        raise ValueError(f"Unsupported camera brand: {brand}")

    if not commands:
        raise ValueError(f"Unsupported resolution: {resolution}")

    for command in commands:
        serial_device.transceive(bytearray.fromhex(command))

def poll_command(serial_device, command, retries=20, delay=0.1):
    for _ in range(retries):
        response = serial_device.transceive(bytearray.fromhex(command))
        if b"9041ff" in response:
            return response
        sleep(delay)
    raise RuntimeError(f"Failed to execute command: {command}")

def main():
    parser = argparse.ArgumentParser(description="Set camera resolution via LvdsSerial")
    parser.add_argument("resolution", type=str, help="Resolution in the form of '720p60'")
    parser.add_argument("-d", "--dev", type=str, default="/dev/v4l-subdev1", help="Device path")
    args = parser.parse_args()

    serial_device = LvdsSerial(args.dev)
    brand = detect_camera_brand(serial_device)
    commands = SONY_RESOLUTIONS.get(args.resolution) if brand == "Sony" else WONWOO_RESOLUTIONS.get(args.resolution)

    if not commands:
        raise ValueError(f"Unsupported resolution: {args.resolution}")

    for command in commands:
        retry_command(serial_device, command)

if __name__ == "__main__":
    main()
