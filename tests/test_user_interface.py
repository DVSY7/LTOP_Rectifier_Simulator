import asyncio
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from communication.modbus_worker import ModbusWorker
from config.loader import load_config
from config.register_map import build_initial_values, build_register_map
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_logs_use_physical_values_and_throttle_reads(app):
    config = load_config()
    values = build_initial_values(config, build_register_map(config))
    with patch("communication.modbus_worker.EnvironmentRuntime"):
        worker = ModbusWorker(config, values)
    messages = []
    worker.communication_log.connect(messages.append)
    asyncio.run(worker.register_action(6, 9, 3, 1, [], [435]))
    assert "설정전압" in messages[-1] and "43.5 V" in messages[-1]
    asyncio.run(worker.register_action(3, 9, 0, 17, [], None))
    assert any("정상적으로" in message for message in messages)
    assert any("TB1 측정전위: -1593 mV" in message for message in messages)
    count = len(messages)
    asyncio.run(worker.register_action(3, 9, 0, 17, [], None))
    assert len(messages) == count
    assert not any(token in " ".join(messages) for token in ("ADDR", "FC=", "RAW", "0x"))


def test_guides_graph_selection_and_bounded_history(app):
    with patch("ui.main_window.list_ports.comports", return_value=[]):
        window = MainWindow(load_config())
    window.show()
    app.processEvents()
    button = next(b for b in window.findChildren(QPushButton) if "직접 입력 가능" in b.text())
    button.click()
    assert "더블클릭" in window.guide_text.text()
    window._show_register_guide(window.row_by_address[3], 1)
    assert "출력전압" in window.guide_text.text()
    assert window.graph.selected_addresses() == [3, 5, 6, 12]
    for i in range(305):
        window.register_values[5] = i
        window.graph.sample(window.register_values)
    assert len(window.graph.history) == 305
    assert window.graph.history[-1][1][12] == -1593
    window.active_tb_count = 0
    window._rebuild_table()
    assert 12 not in window.graph.selected_addresses()
    window.graph.sample(window.register_values)
    assert 12 not in window.graph.history[-1][1]
    for i in range(window.graph.items.count()):
        window.graph.items.item(i).setCheckState(Qt.Unchecked)
    assert window.graph.selected_addresses() == []
    app.processEvents()
    assert not window.grab().isNull()
    window.close()


def test_graph_time_range_keeps_history_and_expires_after_one_day(app):
    from ui.output_graph import OutputGraph, RETENTION_SECONDS, reduced_series
    config = load_config()
    registers = build_register_map(config)
    values = build_initial_values(config, registers)
    graph = OutputGraph(registers)
    for timestamp in (0, 60, 300, 3600, RETENTION_SECONDS):
        with patch("ui.output_graph.monotonic", return_value=timestamp):
            graph.sample(values)
    graph.range_combo.setCurrentIndex(graph.range_combo.findData(60))
    assert [t for t, _ in graph.visible_history()] == [RETENTION_SECONDS]
    graph.range_combo.setCurrentIndex(graph.range_combo.findData(RETENTION_SECONDS))
    assert len(graph.visible_history()) == 5
    with patch("ui.output_graph.monotonic", return_value=RETENTION_SECONDS + 1):
        graph.sample(values)
    assert graph.history[0][0] == 60
    assert len(graph.history) == 5
    points = reduced_series([(t, {5: 99 if t == 50 else 0}) for t in range(100)],
                            5, 0, 100, 2)
    assert (50, 99) in points
    assert len(points) <= 8
    assert None in reduced_series([(0, {5: 1}), (1, {}), (2, {5: 2})], 5, 0, 2, 10)
    graph.close()


def test_simulation_updates_do_not_flood_communication_log(app):
    config = load_config()
    values = build_initial_values(config, build_register_map(config))
    with patch("communication.modbus_worker.EnvironmentRuntime"):
        worker = ModbusWorker(config, values)
    messages = []
    worker.communication_log.connect(messages.append)

    class CallbackServer:
        async def async_setValues(self, device, code, address, values):
            await worker.register_action(code, device, address, len(values), [], values)

    worker._server = CallbackServer()
    asyncio.run(worker._update_register(5, 435))
    assert worker.values[5] == 435
    assert messages == []
    asyncio.run(worker.register_action(6, 9, 3, 1, [], [430]))
    assert len(messages) == 1 and "43 V" in messages[0]


@pytest.mark.parametrize("can_start", [True, False])
def test_server_announces_ready_only_after_port_opens(app, can_start):
    config = load_config()
    values = build_initial_values(config, build_register_map(config))
    with patch("communication.modbus_worker.EnvironmentRuntime"):
        worker = ModbusWorker(config, values)
    statuses = []
    worker.server_status.connect(statuses.append)

    class FakeServer:
        def __init__(self, **kwargs):
            self.serving = asyncio.get_running_loop().create_future()

        async def serve_forever(self, *, background=False):
            assert background is True
            assert statuses == []
            if not can_start:
                raise RuntimeError("port unavailable")
            self.serving.set_result(True)

    with patch("communication.modbus_worker.ModbusSerialServer", FakeServer):
        if can_start:
            asyncio.run(worker._run_server())
            assert statuses == ["RTU 서버 실행 중"]
        else:
            with pytest.raises(RuntimeError, match="port unavailable"):
                asyncio.run(worker._run_server())
            assert statuses == []
