from enum import IntEnum

MAGIC = b"HR"
VERSION = 1

class Target(IntEnum):
    NONE = 0; TOWN = 1; MINE = 2; SKI = 3; FARM = 4; TIPPER = 5; YARD = 6; MANUAL = 7

def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc

def encode(train_id: int, status: int, target: Target, speed: int) -> bytes:
    if not 0 <= train_id <= 255 or not -255 <= speed <= 255:
        raise ValueError("train_id or speed out of range")
    payload = bytes((VERSION, train_id, status & 0xFF, int(target), abs(speed)))
    return MAGIC + payload + bytes((crc8(payload),))

def decode(packet: bytes) -> dict[str, int]:
    if len(packet) != 8 or packet[:2] != MAGIC:
        raise ValueError("invalid frame")
    version, train_id, status, target, magnitude, checksum = packet[2:]
    if version != VERSION or crc8(packet[2:-1]) != checksum:
        raise ValueError("invalid version or CRC")
    direction = -1 if status & 1 else 1
    return {"train_id": train_id, "status": status, "target": target, "speed": direction * magnitude}
