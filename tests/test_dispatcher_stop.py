from railroad.dispatcher import Dispatcher
from railroad.transport.locomotive import LocomotiveCommandTransport


class Sender:
    def __init__(self):
        self.commands = []

    def send(self, command):
        self.commands.append((command.train_id, command.speed))


def test_stop_train_is_zero_speed_and_does_not_require_motion_arm():
    sender = Sender()
    dispatcher = Dispatcher()
    transport = LocomotiveCommandTransport(sender, start_armed=True)
    dispatcher.attach_motion_transport(transport, require_rearm=False)
    dispatcher.trains[1].velocity = 55
    dispatcher.stop_train(1)
    assert sender.commands == [(1, 0)]
    assert dispatcher.trains[1].velocity == 0
    transport.shutdown()
