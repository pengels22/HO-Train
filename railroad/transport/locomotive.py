"""Named locomotive command transport.

The wire format retains the historical ESTOP/REARM fields for compatibility
with already-flashed controllers. New runtime code uses these names so the
transport is not confused with a physical E-stop input.
"""
from .estop import ALL_TRAINS, ESTOP_FLAG, REARM_FLAG
from .estop import EmergencyStop as LocomotiveCommandTransport
from .estop import EStopFanout as LocomotiveStopFanout
from .estop import create_bench_sender

__all__ = ["ALL_TRAINS", "ESTOP_FLAG", "REARM_FLAG", "LocomotiveCommandTransport",
           "LocomotiveStopFanout", "create_bench_sender"]
