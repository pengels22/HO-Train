import pytest
from railroad.hardware.turnout_return import STANDARDS, TurnoutAutoReturn, relay_input_level


def test_nc_standard_polarity():
    assert relay_input_level("A", "diverging") == 1
    assert relay_input_level("A", "straight") == 0
    for name in "BCDEFGH":
        assert relay_input_level(name, "straight") == 1
        assert relay_input_level(name, "diverging") == 0


def test_open_for_1000ms_and_confirmed_last_car():
    sent = []
    t = TurnoutAutoReturn(lambda a, b: sent.append((a, b)))
    t.command_position("H", "diverging")
    t.reed_event("turnout_H_divergent", closed=True, now=1.0)
    t.reed_event("turnout_H_divergent", closed=False, now=2.0)
    assert t.tick(5.0, route_holds=set(), occupied=set(), connected=True) == ()
    t.confirm_tail_clear("H", exit_reed="turnout_H_divergent")
    assert t.tick(2.99, route_holds=set(), occupied=set(), connected=True) == ()
    assert t.tick(3.0, route_holds=set(), occupied=set(), connected=True) == ("H",)
    assert sent == [("H", "diverging"), ("H", "straight")]


def test_inter_car_close_resets_timer_and_tail_confirmation():
    t = TurnoutAutoReturn(lambda *_: None)
    t.command_position("C", "diverging")
    t.reed_event("turnout_C_divergent", closed=True, now=0)
    t.reed_event("turnout_C_divergent", closed=False, now=1)
    t.confirm_tail_clear("C", exit_reed="turnout_C_divergent")
    t.reed_event("turnout_C_divergent", closed=True, now=1.5)
    t.reed_event("turnout_C_divergent", closed=False, now=2)
    assert t.tick(4, route_holds=set(), occupied=set(), connected=True) == ()
    t.confirm_tail_clear("C", exit_reed="turnout_C_divergent")
    assert t.tick(4, route_holds=set(), occupied=set(), connected=True) == ("C",)


def test_route_occupancy_and_disconnection_block_restore():
    t = TurnoutAutoReturn(lambda *_: None)
    t.command_position("A", "straight")
    t.reed_event("turnout_A_straight", closed=True, now=0)
    t.reed_event("turnout_A_straight", closed=False, now=1)
    t.confirm_tail_clear("A", exit_reed="turnout_A_straight")
    assert t.tick(3, route_holds={"A"}, occupied=set(), connected=True) == ()
    assert t.tick(3, route_holds=set(), occupied={"A"}, connected=True) == ()
    assert t.tick(3, route_holds=set(), occupied=set(), connected=False) == ()
    assert t.tick(3, route_holds=set(), occupied=set(), connected=True) == ("A",)


def test_other_exit_never_triggers_restore():
    t = TurnoutAutoReturn(lambda *_: None)
    t.command_position("G", "diverging")
    t.reed_event("turnout_G_straight", closed=True, now=0)
    t.reed_event("turnout_G_straight", closed=False, now=1)
    t.confirm_tail_clear("G", exit_reed="turnout_G_straight")
    assert t.tick(5, route_holds=set(), occupied=set(), connected=True) == ()


def test_failed_relay_write_does_not_change_position():
    def failed(*_): raise OSError("USB disconnected")
    t = TurnoutAutoReturn(failed)
    with pytest.raises(OSError):
        t.command_position("B", "diverging")
    assert t.positions["B"] == "straight"
