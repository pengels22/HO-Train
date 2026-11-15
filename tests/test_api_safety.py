from railroad.api import server


def test_hardware_mode_does_not_require_pi_gpio_estop():
    server.configure_runtime("hardware")
    try:
        assert not server.DISPATCHER.simulation
        assert server.DISPATCHER.physical_estop is None
    finally:
        # The test process remains explicitly simulation-safe.
        server.configure_runtime("simulation")
    assert server.DISPATCHER.simulation


def test_simulation_startup_is_disarmed_and_has_no_usb_outputs():
    server.configure_runtime("simulation")
    assert not server.DISPATCHER.snapshot()["motion_armed"]
    assert server.USB_CONTROLLERS.status() == []
