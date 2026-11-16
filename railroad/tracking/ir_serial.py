"""Parse decoded IR events from Nano USB serial; do not time 38kHz on Linux."""
from __future__ import annotations
import json

RECEIVERS=("Tunnel Entrance","Yard Entrance","Ski Entrance","Tunnel Exit East",
           "Tunnel Exit West","Underground Entrance","Tipper Entrance",
           "Stall 1A","Stall 1B","Stall 2","Stall 3",
           "Mine Station","Farm Station","Town Station")
STATION_IDS={name.lower().replace(" ", "_"): name for name in RECEIVERS}

def parse_event(line:str)->dict:
    obj=json.loads(line)
    if not isinstance(obj,dict):raise ValueError("event must be object")
    receiver=obj.get("receiver")
    if receiver is None:
        station_id=obj.get("station_id")
        receiver=STATION_IDS.get(station_id)
        if receiver is None: raise ValueError("invalid station_id")
        obj["receiver"] = receiver
    train_id=obj.get("train_id")
    if receiver not in RECEIVERS: raise ValueError("invalid receiver")
    if train_id == "no_train": return obj
    if type(train_id) is not int or not 1<=train_id<=255:
        raise ValueError("invalid receiver or train_id")
    if not isinstance(obj.get("speed",0),int) or not -255<=obj.get("speed",0)<=255:
        raise ValueError("invalid speed")
    return obj
