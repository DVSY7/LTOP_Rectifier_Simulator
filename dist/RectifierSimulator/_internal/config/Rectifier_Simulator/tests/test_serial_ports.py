from dataclasses import dataclass

from communication.serial_ports import choose_port_index, format_port_label


@dataclass
class Port:
    device: str
    description: str = "USB Serial Port"
    vid: int | None = None
    pid: int | None = None


def test_last_selected_port_has_priority():
    ports = [
        Port("COM3", vid=0x0403, pid=0x6001),
        Port("COM8"),
    ]
    assert choose_port_index(ports, requested_port="COM8") == 1


def test_ftdi_adapter_is_selected_before_yaml_default():
    ports = [
        Port("COM7"),
        Port("COM9", vid=0x0403, pid=0x6001),
    ]
    assert choose_port_index(ports, configured_port="COM7") == 1


def test_yaml_default_is_used_without_preferred_adapter():
    ports = [Port("COM4"), Port("COM7")]
    assert choose_port_index(ports, configured_port="COM7") == 1


def test_empty_port_list_returns_negative_index():
    assert choose_port_index([]) == -1


def test_port_label_includes_vid_and_pid():
    port = Port("COM7", vid=0x0403, pid=0x6001)
    assert format_port_label(port) == "COM7 - USB Serial Port [0403:6001]"
