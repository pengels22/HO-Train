import pytest

from railroad.api import server


def test_hardware_mode_requires_physical_estop_and_registered_controllers():
    with pytest.raises(RuntimeError, match="hardware safety configuration incomplete"):
        server.configure_runtime("hardware")
    # The test process remains explicitly simulation-safe.
    server.configure_runtime("simulation")
    assert server.DISPATCHER.simulation


def test_simulation_startup_is_disarmed_and_has_no_usb_outputs():
    server.configure_runtime("simulation")
    assert not server.DISPATCHER.snapshot()["motion_armed"]
    assert server.USB_CONTROLLERS.status() == []
