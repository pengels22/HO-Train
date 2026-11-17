from railroad.dispatcher import Dispatcher


class Sender:
    def __init__(self):
        self.commands = []

    def send_motion(self, train_id, speed):
        self.commands.append((train_id, speed))


def test_stop_train_is_zero_speed_and_does_not_require_motion_arm():
    sender = Sender()
    dispatcher = Dispatcher()
    dispatcher.attach_estop(sender, require_rearm=True)
    dispatcher.trains[1].velocity = 55
    dispatcher.stop_train(1)
    assert sender.commands == [(1, 0)]
    assert dispatcher.trains[1].velocity == 0
