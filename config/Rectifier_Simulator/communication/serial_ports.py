PREFERRED_USB_VID = 0x0403
PREFERRED_USB_PID = 0x6001


def format_port_label(port):
    """사용자가 장치를 구분할 수 있는 COM 포트 표시 문자열을 만든다."""

    description = port.description or "직렬 포트"
    hardware = ""
    if port.vid is not None and port.pid is not None:
        hardware = f" [{port.vid:04X}:{port.pid:04X}]"
    return f"{port.device} - {description}{hardware}"


def choose_port_index(
    ports,
    *,
    requested_port=None,
    configured_port=None,
    preferred_vid=PREFERRED_USB_VID,
    preferred_pid=PREFERRED_USB_PID,
):
    """마지막 선택, 지정 USB 장치, YAML 기본값 순서로 포트를 선택한다."""

    if requested_port:
        for index, port in enumerate(ports):
            if port.device == requested_port:
                return index

    for index, port in enumerate(ports):
        if port.vid == preferred_vid and port.pid == preferred_pid:
            return index

    if configured_port:
        for index, port in enumerate(ports):
            if port.device == configured_port:
                return index

    return 0 if ports else -1
