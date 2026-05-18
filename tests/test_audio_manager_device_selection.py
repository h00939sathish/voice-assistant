from assistant import audio_manager


class FakeDefault:
    def __init__(self, input_device=1, output_device=4):
        self.device = [input_device, output_device]


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.active = False
        self.closed = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self):
        self.default = FakeDefault()
        self.streams = []
        self.devices = [
            {"name": "Speaker", "max_input_channels": 0},
            {"name": "Microphone Array", "max_input_channels": 4},
            {"name": "Headset (Airdopes 800)", "max_input_channels": 1},
        ]

    def query_devices(self, device=None, kind=None):
        if kind == "input":
            return self.devices[self.default.device[0]]
        if device is not None:
            return self.devices[device]
        return self.devices

    def InputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


def make_manager(monkeypatch, device_config):
    fake_sd = FakeSoundDevice()
    monkeypatch.setattr(audio_manager, "sd", fake_sd)
    monkeypatch.setattr(audio_manager, "AUDIO_INPUT_DEVICE", device_config)
    return audio_manager.AudioManager(), fake_sd


def test_auto_uses_current_default_input(monkeypatch):
    manager, fake_sd = make_manager(monkeypatch, "auto")

    manager.start_stream()

    assert manager.input_device == 1
    assert fake_sd.streams[-1].kwargs["device"] == 1


def test_auto_switches_when_default_input_changes(monkeypatch):
    manager, fake_sd = make_manager(monkeypatch, "auto")
    manager._device_check_interval = 0
    manager.start_stream()
    manager.start_recording()

    fake_sd.default.device[0] = 2
    manager.get_audio_chunk(timeout=0.001)

    assert manager.input_device == 2
    assert manager._active_input_device == 2
    assert fake_sd.streams[-1].kwargs["device"] == 2
    assert manager.is_recording is True


def test_named_input_device_remains_pinned(monkeypatch):
    manager, fake_sd = make_manager(monkeypatch, "Airdopes")
    manager.start_stream()

    fake_sd.default.device[0] = 1
    manager._device_check_interval = 0
    manager.get_audio_chunk(timeout=0.001)

    assert manager.input_device == 2
    assert fake_sd.streams[-1].kwargs["device"] == 2


def test_index_input_device_remains_pinned(monkeypatch):
    manager, fake_sd = make_manager(monkeypatch, "1")

    manager.start_stream()

    assert manager.input_device == 1
    assert fake_sd.streams[-1].kwargs["device"] == 1
