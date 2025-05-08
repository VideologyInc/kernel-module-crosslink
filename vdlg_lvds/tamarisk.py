from vdlg_lvds.serial import LvdsSerial
import struct
import argparse
import sys

START_BYTE = 0x01
MTU = 252

class Tamarisk:
    def __init__(self, device=None, baudrate=57600):
        # LvdsSerial uses IOCTLs, baudrate sets the FPGA bridge UART speed
        # ignore serial if dev is None
        if device:
            self.serial = LvdsSerial(device, baud=baudrate)

    def _checksum(self, command_id, params):
        checksum = -START_BYTE
        checksum -= command_id
        checksum -= len(params)
        for b in params:
            checksum -= b
        return checksum & 0xFF

    def _verify_crc(self, msg_bytes):
        body = msg_bytes[:-1]
        expected_crc = msg_bytes[-1]
        calculated = self._checksum(body[1], body[3:-1])
        return expected_crc == calculated

    def _build_msg(self, command_id, params=b''):
        if len(params) > MTU:
            raise ValueError("Parameters exceed MTU size")
        length = len(params)
        checksum = self._checksum(command_id, params)
        return bytes([START_BYTE, command_id, length]) + params + bytes([checksum])


    def send_command(self, command_id, params=b'', expect_response=True):
        """Sends a command and optionally receives a response using LvdsSerial."""
        msg_to_send = self._build_msg(command_id, params)

        if expect_response:
            # Use transceive to send and then wait for/read the response
            # Setting count=0 reads all available data after the wait period in transceive.
            raw_response = self.serial.transceive(msg_to_send, count=0)

            if not raw_response:
                raise TimeoutError("No response received from Tamarisk")

            # Basic validation: check start byte and minimum length (header + checksum)
            if len(raw_response) < 4 or raw_response[0] != START_BYTE:
                 # Attempt to read again with a small delay? Or just fail?
                 # Let's try one more time after a short sleep, maybe the buffer wasn't stable
                 import time
                 time.sleep(0.05)
                 raw_response = self.serial.recv() # Read any remaining data
                 if not raw_response or len(raw_response) < 4 or raw_response[0] != START_BYTE:
                    raise ValueError(f"Invalid or incomplete response received: {raw_response.hex()}")

            # Verify CRC on the received message
            if not self._verify_crc(raw_response):
                raise ValueError(f"Checksum mismatch in response: {raw_response.hex()}")

            # Extract response ID and payload
            # Response format: START_BYTE, response_id, length, payload..., checksum
            response_id = raw_response[1]
            length = raw_response[2]
            payload = raw_response[3:-1]

            # Validate payload length
            if len(payload) != length:
                raise ValueError(f"Response length mismatch: expected {length}, got {len(payload)}")

            return response_id, payload
        else:
            # Just send the command, don't wait for or read any response
            self.serial.send(msg_to_send)
            # Optionally clear RX buffer if needed after sending, though maybe not necessary
            # self.serial.recv()
            return None
    # Command methods
    def get_system_version(self):
        return self.send_command(0x07)

    def read_customer_nv(self):
        return self.send_command(0xCA)

    def write_customer_nv(self, data: bytes):
        return self.send_command(0xCB, data)

    def set_colorization(self, enable: bool):
        val = 0x0001 if enable else 0x0000
        return self.send_command(0xCC, struct.pack(">H", val))

    def set_color_palette(self, palette_id: int):
        return self.send_command(0xCD, struct.pack(">H", palette_id))

    def set_video_orientation(self, orientation: int):
        return self.send_command(0xCF, struct.pack(">H", orientation))

    def set_digital_video_source(self, source_id: int):
        return self.send_command(0xD7, struct.pack(">H", source_id))

    def set_baudrate(self, baud_id: int):
        # Send the command to the camera to change its baud rate.
        # Note: This does NOT change the LvdsSerial (FPGA bridge) baud rate.
        # The user must reinstantiate Tamarisk with the new baud rate if communication continues.
        self.send_command(0xF1, struct.pack(">H", baud_id), expect_response=False)
        # Optionally, update self.serial.baud if LvdsSerial allowed dynamic changes, but it doesn't seem to.

    def get_system_status(self):
        return self.send_command(0xF2)

    def perform_calibration(self, cal_id: int = 3):
        return self.send_command(0x27, struct.pack(">H", cal_id))

    def set_auto_calibration(self, enable: bool):
        val = 0x0001 if enable else 0x0000
        return self.send_command(0xAC, struct.pack(">H", val))

# CLI
def main():
    parser = argparse.ArgumentParser(description="Tamarisk 640 UART CLI")
    parser.add_argument("-d", "--dev", type=str, required=True, help="UART device path (e.g., /dev/ttyUSB0)")
    parser.add_argument("command", type=str, help="Command name (e.g. get_system_version)")
    parser.add_argument("params", nargs="?", default="", help="Hex string of params (e.g. '0001')")
    args = parser.parse_args()

    cam = Tamarisk(args.dev)

    # Convert hex string to bytes
    params_bytes = bytes.fromhex(args.params)

    if args.command == "get_system_version":
        resp = cam.get_system_version()
    elif args.command == "read_customer_nv":
        resp = cam.read_customer_nv()
    elif args.command == "write_customer_nv":
        resp = cam.write_customer_nv(params_bytes)
    elif args.command == "set_colorization":
        resp = cam.set_colorization(params_bytes != b'\x00\x00')
    elif args.command == "set_color_palette":
        resp = cam.set_color_palette(int.from_bytes(params_bytes, "big"))
    elif args.command == "set_video_orientation":
        resp = cam.set_video_orientation(int.from_bytes(params_bytes, "big"))
    elif args.command == "set_digital_video_source":
        resp = cam.set_digital_video_source(int.from_bytes(params_bytes, "big"))
    elif args.command == "set_baudrate":
        cam.set_baudrate(int.from_bytes(params_bytes, "big"))
        print("Baudrate set, no response expected.")
        return
    elif args.command == "get_system_status":
        resp = cam.get_system_status()
    elif args.command == "perform_calibration":
        resp = cam.perform_calibration(int.from_bytes(params_bytes, "big"))
    elif args.command == "set_auto_calibration":
        resp = cam.set_auto_calibration(params_bytes != b'\x00\x00')
    else:
        print("Unknown command")
        return

    print("Response ID:", hex(resp[0]))
    print("Payload:", resp[1].hex())

if __name__ == "__main__":
    main()