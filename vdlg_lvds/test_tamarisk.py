import pytest
from .tamarisk import Tamarisk

def test_checksum_example_from_pdf():
    # Example from the PDF: message = [0x01, 0x2A, 0x02, 0x00, 0x01]
    # Expected checksum = 0xD2
    command_id = 0x2A
    params = bytes([0x00, 0x01])
    expected_checksum = 0xD2

    calculated = Tamarisk._checksum(None, command_id, params)
    assert calculated == expected_checksum, f"Expected {hex(expected_checksum)}, got {hex(calculated)}"

def test_command_packet():
    T = Tamarisk()
    bytes = T._build_msg(0x07, b'')
    assert len(bytes) == 4
    assert bytes[0] == 0x01
    assert bytes[1] == 0x07
    assert bytes[2] == 0x00
    assert bytes[3] == 0xF8
    # Checksum is 0xF8, which is the expected value for this example