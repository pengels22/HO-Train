"""Three physical yard power sections; 1A and 1B share track 1."""
from dataclasses import dataclass, field


class RelayOutput:
    """Fail-closed relay GPIO adapter; setup drives the relay inactive."""
    def __init__(self, pin: int, *, active_low: bool = True, backend=None, enabled: bool = False):
        self.pin, self.active_low, self.backend, self.enabled = pin, active_low, backend, bool(enabled)
        if self.enabled:
            if backend is None: raise RuntimeError("relay backend is not configured")
            backend.setup_output(pin, self._level(False))
    def _level(self, enabled: bool) -> int:
        return int(not enabled) if self.active_low else int(enabled)
    def set(self, enabled: bool) -> None:
        if not self.enabled or self.backend is None: raise RuntimeError("relay output is disabled")
        self.backend.write(self.pin, self._level(enabled))
    def safe_stop(self) -> None:
        if self.enabled: self.set(False)

@dataclass
class YardPower:
    enabled:dict[str,bool]=field(default_factory=lambda:{"1":False,"2":False,"3":False})
    occupied:dict[str,int|None]=field(default_factory=lambda:{"1A":None,"1B":None,"2":None,"3":None})
    outputs:dict[str,RelayOutput]=field(default_factory=dict, repr=False)
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
        if track in self.outputs:
            self.outputs[track].set(True)

    def stop_all(self) -> None:
        for output in self.outputs.values():
            output.safe_stop()
        for track in self.enabled:
            self.enabled[track] = False
