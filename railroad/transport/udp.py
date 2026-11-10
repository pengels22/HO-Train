"""Broadcast-only command transport. Socket creation is explicit; simulation never transmits."""
from __future__ import annotations
import socket
import struct
from dataclasses import dataclass

PORT=4210
BROADCAST="10.77.0.255"
MAGIC=b"HC"
VERSION=1

def crc16(data:bytes)->int:
    crc=0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc=(crc>>1)^ (0xA001 if crc&1 else 0)
    return crc

@dataclass(frozen=True)
class Command:
    train_id:int
    sequence:int
    speed:int
    target:int=0
    flags:int=0

    def encode(self)->bytes:
        if not (0<=self.train_id<=255 and 0<=self.sequence<=65535 and -255<=self.speed<=255
                and 0<=self.target<=7 and 0<=self.flags<=255):
            raise ValueError("invalid command")
        body=struct.pack("<2sBBHhBB",MAGIC,VERSION,self.train_id,self.sequence,self.speed,self.target,self.flags)
        return body+struct.pack("<H",crc16(body))

    @classmethod
    def decode(cls,data:bytes)->"Command":
        if len(data)!=12 or data[:2]!=MAGIC or crc16(data[:-2])!=struct.unpack("<H",data[-2:])[0]:
            raise ValueError("invalid command frame")
        _,version,tid,seq,speed,target,flags=struct.unpack("<2sBBHhBB",data[:-2])
        if version!=VERSION:raise ValueError("unsupported version")
        return cls(tid,seq,speed,target,flags)

class Broadcaster:
    def __init__(self,host:str=BROADCAST,port:int=PORT):
        self.host,self.port=host,port
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
    def send(self,command:Command):
        self.socket.sendto(command.encode(),(self.host,self.port))
    def send_rearm(self, transaction: str):
        import json
        packet = b"HR" + json.dumps({"version": 1, "id": 255, "transaction": transaction}, separators=(",", ":")).encode()
        self.socket.sendto(packet, (self.host, self.port))
    def close(self):self.socket.close()
