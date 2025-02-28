import argparse
from time import sleep
from vdlg_lvds.serial import LvdsSerial
import glob

resolution_commands = {
    "sony_ev75xx": {
        "720p25": ["81010424720101FF", "81010424740000FF", "8101041903FF"],
        "720p30": ["8101042472000FFF", "81010424740000FF", "8101041903FF"],
        "720p50": ["8101042472000CFF", "81010424740000FF", "8101041903FF"],
        "720p60": ["8101042472000AFF", "81010424740000FF", "8101041903FF"],
        "1080p25": ["81010424720008FF", "81010424740000FF", "8101041903FF"],
        "1080p30": ["81010424720007FF", "81010424740000FF", "8101041903FF"],
        "1080p50": ["81010424720104FF", "81010424740001FF", "8101041903FF"],
        "1080p60": ["81010424720105FF", "81010424740001FF", "8101041903FF"],
    },
    "sony_ev95xx": {
        "720p25": ["81010424720101FF", "81010424740000FF", "8101041903FF"],
        "720p30": ["8101042472000FFF", "81010424740000FF", "8101041903FF"],
        "720p50": ["8101042472000CFF", "81010424740000FF", "8101041903FF"],
        "720p60": ["8101042472000AFF", "81010424740000FF", "8101041903FF"],
        "1080p25": ["81010424720008FF", "81010424740000FF", "8101041903FF"],
        "1080p30": ["81010424720007FF", "81010424740000FF", "8101041903FF"],
        "1080p50": ["81010424720104FF", "81010424740001FF", "8101041903FF"],
        "1080p60": ["81010424720105FF", "81010424740001FF", "8101041903FF"],
    },
    "videology": {
        "720p25": ["81010424720101FF", "81010424740000FF"],
        "720p30": ["8101042472000EFF", "81010424740000FF"],
        "720p50": ["8101042472000CFF", "81010424740000FF"],
        "720p60": ["81010424720009FF", "81010424740000FF"],
        "1080p25": ["81010424720008FF", "81010424740000FF"],
        "1080p30": ["81010424720006FF", "81010424740000FF"],
        "1080p50": ["81010424720104FF", "81010424740001FF"],
        "1080p60": ["81010424720103FF", "81010424740001FF"],
    },
    "tamron":{
        "720p25": ["81010424720101FF", "81010424740000FF", "8101041903FF"],
        "720p30": ["8101042472000FFF", "81010424740000FF", "8101041903FF"],
        "720p50": ["81010424720006FF", "81010424740000FF", "8101041903FF"],
        "720p60": ["81010424720005FF", "81010424740000FF", "8101041903FF"],
        "1080p25": ["81010424720002FF", "81010424740000FF", "8101041903FF"],
        "1080p30": ["81010424720001FF", "81010424740000FF", "8101041903FF"],
        "1080p50": ["81010424720008FF", "81010424740001FF", "8101041903FF"],
        "1080p60": ["81010424720007FF", "81010424740001FF", "8101041903FF"],
    }
}

brands = {
    "sony_ev75xx" : "2006", # Y0 50 00 20 HH HH JJ JJ KK FF
    "sony_ev95xx" : "2007", #
                            # Y05000 2006 xxJJJJFF : EV7520A (to be tested)
                            # Y05000 2007 xxJJJJFF : EV95..L
                            #             HH HH = 0640: FCB-EV7520A
                            #             HH HH = 070E: FCB-EV9500L (tested)
                            #             HH HH = 0711: FCB-EV9520L (tested)
    "videology": "2004",    # Y0 50 00 20 mn pq rs tu vw FF
                            # Y05000 2004 66tuvwFF
                            #             mn pq = 0466: 24Z2.1-10X-LVDS-462 (tested)
                            #             mn pq = 0466: 24Z2.1-20X-LVDS     (tested)
                            #             mn pq = 0466: 24Z2.1-30X-LVDS-462 (tested)
                            #             mn pq = 0466: 24Z2.1-40X          (tested)
                            #             mn pq = 0466: 24Z2.1-55X          (tested)
                            #             mn pq = 0466: 25Z2.4-36X Global shutter (tested)

    "tamron"   : "23F0"     # Y0 50 00 23 HH HH JJ JJ KK FF
                            # Y05000 23F0 1xJJJJFF
                            #             HH HH = F011: MP1010-VC
                            #             HH HH = F017: MP3010M-EV  (tested)
}

def poll_command(serial_device, command, retries=2, delay=0):
    if retries < 1:
        return serial_device.transceive(bytearray.fromhex(command)).hex()
    else:
        for _ in range(retries):
            response = serial_device.transceive(bytearray.fromhex(command)).hex()
            if "9041ff" in response:
                return response
            sleep(delay)
            print(f"polling {command}")
        raise RuntimeError(f"Failed to execute command: {command}")

def poll_status(serial_device, retries=50, delay=0.1):
    for poll in range(retries):
        response = serial_device.transceive(bytearray.fromhex("81090400FF")).hex()
        if "9050" in response:
            if poll > 5:
                print(f"Camera status okay")
            break;
        sleep(delay)
        print(f"polling camera status")

def detect_camera_brand(serial_device):
    response = serial_device.transceive(bytearray.fromhex("81090002FF")).hex().upper()
    for brand, code in brands.items():
        if code in response:
            print(f"Camera ID response: {response} with {code}.\nDetected {brand.upper()} zoomblock")
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
                retry = 0 if "1041903" in command else 2
                try:
                    res = poll_command(serial_device, command, retries=retry)
                except RuntimeError as e:
                    print(f"Failed to exec cmd {command}")
                else:
                    print(f"cmd: {command}, res: {res}")
            poll_status(serial_device)

def main():
    lvds_devs = glob.glob("/dev/links/lvds*")
    default_lvds = lvds_devs[0] if lvds_devs else "/dev/v4l-subdev1"
    parser = argparse.ArgumentParser(description="Set camera resolution via LvdsSerial")
    parser.add_argument("resolution", type=str, help="Resolution in the form of '720p60'")
    parser.add_argument("-d", "--dev", type=str, default=default_lvds, help="Device path")
    args = parser.parse_args()

    serial_device = LvdsSerial(args.dev)
    brand = detect_camera_brand(serial_device)
    set_resolution(serial_device, args.resolution, brand)

if __name__ == "__main__":
    main()
