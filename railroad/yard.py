"""Three physical yard power sections; 1A and 1B share track 1."""
from dataclasses import dataclass, field

@dataclass
class YardPower:
    enabled:dict[str,bool]=field(default_factory=lambda:{"1":False,"2":False,"3":False})
    occupied:dict[str,int|None]=field(default_factory=lambda:{"1A":None,"1B":None,"2":None,"3":None})
    @staticmethod
    def track(stall:str)->str:
        if stall not in ("1A","1B","2","3"):raise ValueError("invalid stall")
        return "1" if stall in ("1A","1B") else stall
    def park(self,stall:str,train_id:int):
        if self.occupied[stall] not in (None,train_id):
            raise RuntimeError("stall occupied")
        self.occupied[stall]=train_id
        self.enabled[self.track(stall)]=False
    def energize_for_departure(self,stall:str,stopped_train_ids:set[int],confirmed_safe:bool):
        track=self.track(stall)
        if not confirmed_safe or self.occupied[stall] is None:
            raise RuntimeError("departure not authorized")
        if track=="1":
            other="1B" if stall=="1A" else "1A"
            if self.occupied[other] is not None and self.occupied[other] not in stopped_train_ids:
                raise RuntimeError("other locomotive on shared track 1 not held stopped")
        self.enabled[track]=True
