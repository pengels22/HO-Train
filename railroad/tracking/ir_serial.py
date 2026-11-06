"""Parse decoded IR events from Nano USB serial; do not time 38kHz on Linux."""
from __future__ import annotations
import json

RECEIVERS=("Tunnel Entrance","Yard Entrance","Ski Entrance","Tunnel Exit East",
           "Tunnel Exit West","Underground Entrance","Tipper Entrance",
           "Stall 1A","Stall 1B","Stall 2","Stall 3")

def parse_event(line:str)->dict:
    obj=json.loads(line)
    if not isinstance(obj,dict):raise ValueError("event must be object")
    receiver=obj.get("receiver")
    train_id=obj.get("train_id")
    if receiver not in RECEIVERS or type(train_id) is not int or not 1<=train_id<=255:
        raise ValueError("invalid receiver or train_id")
    if not isinstance(obj.get("speed",0),int) or not -255<=obj.get("speed",0)<=255:
        raise ValueError("invalid speed")
    return obj
