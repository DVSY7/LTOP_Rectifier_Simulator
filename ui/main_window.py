from datetime import datetime
from copy import deepcopy

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from ui.output_graph import OutputGraph
from ui.user_guide import COLOR_GUIDES, CONTROL_GUIDES, register_guide

from communication.modbus_worker import ModbusWorker
from communication.serial_ports import choose_port_index, format_port_label
from config.register_map import (
    build_initial_values,
    build_register_map,
    format_register_value,
    physical_to_raw,
    raw_to_physical,
)


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.register_map = build_register_map(config)
        self.register_values = build_initial_values(config, self.register_map)
        self.active_tb_count = config["tb"]["active_count"]
        self.row_by_address = {}
        self.worker = None
        self.settings = QSettings("AI_CP", "RectifierSimulator")
        self.server_control_widgets = []

        self.setWindowTitle("정류기 RTU 시뮬레이터")
        self.resize(1200, 900)
        self._create_ui()
        self._rebuild_table()
        self._refresh_serial_ports()
        self._set_server_controls_enabled(False)
        self.graph_timer = QTimer(self)
        self.graph_timer.setInterval(1000)
        self.graph_timer.timeout.connect(self._sample_graph)

    def _populate_combo(self, combo, address):
        values = self.register_map[address].get("values", {})
        for value, label in sorted(values.items()):
            combo.addItem(str(label), int(value))

        initial_index = combo.findData(self.register_values[address])
        if initial_index >= 0:
            combo.setCurrentIndex(initial_index)

    def _create_ui(self):
        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        communication = self.config["communication"]

        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("통신 포트"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(250)
        info_layout.addWidget(self.port_combo)

        self.refresh_port_button = QPushButton("새로고침")
        self.refresh_port_button.clicked.connect(self._refresh_serial_ports)
        info_layout.addWidget(self.refresh_port_button)

        self.start_server_button = QPushButton("서버 시작")
        self.start_server_button.clicked.connect(self._start_server)
        info_layout.addWidget(self.start_server_button)

        self.stop_server_button = QPushButton("서버 정지")
        self.stop_server_button.clicked.connect(self._stop_server)
        self.stop_server_button.setEnabled(False)
        info_layout.addWidget(self.stop_server_button)

        info_layout.addWidget(QLabel(f"Slave ID: {communication['slave_id']}"))
        info_layout.addWidget(QLabel(f"Baud rate: {communication['baudrate']}"))
        self.status_label = QLabel("서버 정지")
        info_layout.addWidget(self.status_label)
        info_layout.addStretch()
        root_layout.addLayout(info_layout)

        control_layout = QHBoxLayout()

        control_layout.addWidget(self._guide_button("보드 상태 ⓘ", CONTROL_GUIDES["보드 상태"]))
        self.board_status_combo = QComboBox()
        self._populate_combo(self.board_status_combo, 0)
        board_button = QPushButton("상태 적용")
        board_button.clicked.connect(self._apply_board_status)
        control_layout.addWidget(self.board_status_combo)
        control_layout.addWidget(board_button)

        control_layout.addSpacing(20)
        control_layout.addWidget(self._guide_button("정류기 전원 ⓘ", CONTROL_GUIDES["정류기 전원"]))
        self.power_status_combo = QComboBox()
        self._populate_combo(self.power_status_combo, 1)
        power_button = QPushButton("전원 적용")
        power_button.clicked.connect(self._apply_power_status)
        control_layout.addWidget(self.power_status_combo)
        control_layout.addWidget(power_button)

        control_layout.addSpacing(20)
        control_layout.addWidget(self._guide_button("운전 모드 ⓘ", CONTROL_GUIDES["운전 모드"]))
        self.control_mode_combo = QComboBox()
        self._populate_combo(self.control_mode_combo, 2)
        mode_button = QPushButton("모드 적용")
        mode_button.clicked.connect(self._apply_control_mode)
        control_layout.addWidget(self.control_mode_combo)
        control_layout.addWidget(mode_button)

        control_layout.addSpacing(20)
        control_layout.addWidget(self._guide_button("활성 TB 수 ⓘ", CONTROL_GUIDES["활성 TB 수"]))
        self.tb_count_spin = QSpinBox()
        self.tb_count_spin.setRange(0, self.config["tb"]["max_count"])
        self.tb_count_spin.setValue(self.active_tb_count)
        tb_button = QPushButton("TB 수 적용")
        tb_button.clicked.connect(self._apply_tb_count)
        control_layout.addWidget(self.tb_count_spin)
        control_layout.addWidget(tb_button)
        control_layout.addStretch()
        root_layout.addLayout(control_layout)
        self.server_control_widgets.extend(
            [
                self.board_status_combo,
                board_button,
                self.power_status_combo,
                power_button,
                self.control_mode_combo,
                mode_button,
                self.tb_count_spin,
                tb_button,
            ]
        )

        legend_layout = QHBoxLayout()
        for text, color in (
            ("  상단 제어  ", "#DCEEFF"),
            ("  직접 입력 가능  ", "#FFF4CC"),
            ("  모델 자동 계산  ", "#E6E6E6"),
        ):
            label = self._guide_button(text.strip() + " ⓘ", COLOR_GUIDES[text.strip()])
            label.setStyleSheet(f"background-color: {color}; padding: 4px;")
            legend_layout.addWidget(label)
        legend_layout.addStretch()
        root_layout.addLayout(legend_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["주소", "데이터명", "R/W", "Raw 값", "표시값"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._edit_register_value)
        self.table.cellClicked.connect(self._show_register_guide)
        for column in (2, 3):
            self.table.setColumnHidden(column, True)
        self.table.setHorizontalHeaderLabels(["주소", "항목", "R/W", "Raw 값", "현재 값"])
        self.table.setColumnWidth(4, 170)
        self.guide_text = QLabel("사용 안내\n위쪽 색상 버튼이나 표의 항목을 클릭하면 설명이 표시됩니다.\n\n1. 통신 포트를 선택하고 서버를 시작합니다.\n2. 노란색 값을 더블클릭하거나 상단에서 상태를 적용합니다.\n3. 그래프 목록의 체크를 켜고 꺼서 표시 항목을 선택합니다.")
        self.guide_text.setWordWrap(True)
        self.guide_text.setAlignment(Qt.AlignTop)
        self.guide_text.setMinimumWidth(220)
        self.guide_text.setStyleSheet("background: #F1F6FC; padding: 16px; color: #24354B;")
        table_split = QSplitter(Qt.Horizontal)
        table_split.addWidget(self.table)
        table_split.addWidget(self.guide_text)
        table_split.setSizes([820, 330])
        self.content_split = QSplitter(Qt.Vertical)
        self.content_split.addWidget(table_split)
        self.graph = OutputGraph(self.register_map)
        self.content_split.addWidget(self.graph)
        self.content_split.setSizes([320, 330])
        root_layout.addWidget(self.content_split, 1)

        root_layout.addWidget(QLabel("통신 및 동작 기록"))
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(90)
        self.log_text.document().setMaximumBlockCount(500)
        self.log_text.setPlaceholderText(
            "서버를 시작하면 통신 및 설정 변경 내용이 표시됩니다."
        )
        root_layout.addWidget(self.log_text)
        self.setCentralWidget(central_widget)

    def _guide_button(self, title, description):
        button = QPushButton(title)
        button.setToolTip("클릭하면 사용 안내를 표시합니다.")
        button.clicked.connect(lambda: self.guide_text.setText(description))
        return button

    def _show_register_guide(self, row, column):
        address = int(self.table.item(row, 0).text())
        self.guide_text.setText(register_guide(self.register_map[address]))

    def _sample_graph(self):
        if self.worker is not None:
            self.graph.sample(self.register_values)

    def _refresh_serial_ports(self):
        """연결 가능한 직렬 포트를 다시 검색하고 적절한 포트를 선택한다."""

        previous_port = self.port_combo.currentData()
        saved_port = self.settings.value("last_serial_port", "", type=str)
        configured_port = str(self.config["communication"].get("port", ""))
        requested_port = previous_port or saved_port

        ports = sorted(list_ports.comports(), key=lambda port: port.device)
        self.port_combo.clear()

        for port in ports:
            self.port_combo.addItem(
                format_port_label(port),
                port.device,
            )

        if not ports:
            self.port_combo.addItem("사용 가능한 COM 포트 없음", None)
            self.start_server_button.setEnabled(False)
            self.status_label.setText("포트 연결 대기")
            return

        selected_index = choose_port_index(
            ports,
            requested_port=requested_port,
            configured_port=configured_port,
        )
        if selected_index >= 0:
            self.port_combo.setCurrentIndex(selected_index)

        self.start_server_button.setEnabled(self.worker is None)
        self.status_label.setText("서버 정지")

    def _set_server_controls_enabled(self, enabled):
        for widget in self.server_control_widgets:
            widget.setEnabled(enabled)

    def _start_server(self):
        if self.worker is not None:
            return

        selected_port = self.port_combo.currentData()
        if not selected_port:
            QMessageBox.warning(
                self,
                "통신 포트 선택",
                "USB-Serial 장치를 연결한 뒤 사용할 COM 포트를 선택해 주세요.",
            )
            return

        worker_config = deepcopy(self.config)
        worker_config["communication"]["port"] = selected_port
        worker_config["tb"]["active_count"] = self.active_tb_count
        self.settings.setValue("last_serial_port", selected_port)

        worker = ModbusWorker(worker_config, self.register_values)
        worker.server_status.connect(self._on_server_status)
        worker.register_changed.connect(self._update_register)
        worker.communication_log.connect(self._update_log)
        worker.server_error.connect(self._show_error)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker

        self.port_combo.setEnabled(False)
        self.refresh_port_button.setEnabled(False)
        self.start_server_button.setEnabled(False)
        self.stop_server_button.setEnabled(True)
        self.status_label.setText("서버 시작 중...")
        self._update_log(f"{selected_port}에서 통신을 시작하고 있습니다.")
        worker.start()

    def _stop_server(self):
        worker = self.worker
        if worker is None:
            return

        self.stop_server_button.setEnabled(False)
        self.status_label.setText("서버 정지 중...")
        worker.stop_server()
        if not worker.wait(3000):
            QMessageBox.warning(
                self,
                "서버 정지 지연",
                "서버가 아직 종료 중입니다. 잠시 후 다시 확인해 주세요.",
            )

    def _on_server_status(self, message):
        self.status_label.setText(message)
        if message == "RTU 서버 실행 중":
            self._set_server_controls_enabled(True)
            self.graph.clear()
            self.graph.sample(self.register_values)
            self.graph_timer.start()
            self._update_log("서버가 시작되었습니다. 연결된 장치의 통신 요청을 기다립니다.")

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is not self.worker:
            return
        selected_port = self.port_combo.currentData()
        self.worker = None
        self.graph_timer.stop()
        worker.deleteLater()
        self._set_server_controls_enabled(False)
        self.port_combo.setEnabled(True)
        self.refresh_port_button.setEnabled(True)
        self.start_server_button.setEnabled(self.port_combo.currentData() is not None)
        self.stop_server_button.setEnabled(False)
        self.status_label.setText("서버 정지")
        self._update_log(f"{selected_port} 통신 서버가 정지되었습니다. 그래프 기록을 멈춥니다.")

    def _require_worker(self):
        if self.worker is None:
            QMessageBox.information(
                self,
                "서버 정지",
                "먼저 통신 포트를 선택하고 서버를 시작해 주세요.",
            )
            return None
        return self.worker

    def _visible_registers(self):
        return [
            register
            for _, register in sorted(self.register_map.items())
            if register["device_type"] == "rectifier"
            or register["tb_number"] <= self.active_tb_count
        ]

    def _rebuild_table(self):
        registers = self._visible_registers()
        self.graph.set_active_registers(registers)
        self.table.setRowCount(len(registers))
        self.row_by_address.clear()

        for row, register in enumerate(registers):
            address = register["address"]
            raw_value = self.register_values[address]
            self.row_by_address[address] = row

            for column, text in enumerate(
                (address, register["label"], register["access"].upper(), raw_value)
            ):
                self.table.setItem(row, column, QTableWidgetItem(str(text)))

            display_item = QTableWidgetItem(
                format_register_value(register, raw_value)
            )
            if address in (0, 1, 2):
                display_item.setBackground(QColor("#DCEEFF"))
                display_item.setToolTip("상단 제어 영역에서 변경할 수 있습니다.")
            elif address in (5, 6) or register["name"].endswith("measured_potential"):
                display_item.setBackground(QColor("#E6E6E6"))
                display_item.setToolTip("시뮬레이션 모델이 자동 계산합니다.")
            else:
                display_item.setBackground(QColor("#FFF4CC"))
                display_item.setToolTip("더블클릭하면 값을 변경할 수 있습니다.")
            self.table.setItem(row, 4, display_item)

    def _edit_register_value(self, row, column):
        if column != 4:
            return

        address = int(self.table.item(row, 0).text())
        register = self.register_map[address]

        if address in (0, 1, 2):
            QMessageBox.information(
                self, "상태값 변경", "상단 제어 영역에서 변경해 주세요."
            )
            return
        if address in (5, 6) or register["name"].endswith("measured_potential"):
            QMessageBox.information(
                self, "자동 계산 항목", "시뮬레이션 모델이 계산하는 값입니다."
            )
            return

        unit = register.get("unit", "")
        value, accepted = QInputDialog.getDouble(
            self,
            "시뮬레이터 값 변경",
            f"{register['label']} ({unit})",
            raw_to_physical(register, self.register_values[address]),
            -100000.0,
            100000.0,
            2,
        )
        if not accepted:
            return

        raw_value = physical_to_raw(register, value)
        if not 0 <= raw_value <= 65535:
            QMessageBox.warning(
                self, "입력 범위 오류", "Modbus 값은 0~65535 범위여야 합니다."
            )
            return

        worker = self._require_worker()
        if worker is None:
            return
        worker.set_register(address, raw_value)


    def _update_register(self, address, value):
        if address >= len(self.register_values):
            return
        self.register_values[address] = value

        if address in self.row_by_address:
            row = self.row_by_address[address]
            register = self.register_map[address]
            self.table.item(row, 3).setText(str(value))
            self.table.item(row, 4).setText(
                format_register_value(register, value)
            )

        combo_by_address = {
            0: self.board_status_combo,
            1: self.power_status_combo,
            2: self.control_mode_combo,
        }
        combo = combo_by_address.get(address)
        if combo is not None:
            combo_index = combo.findData(value)
            if combo_index >= 0:
                combo.setCurrentIndex(combo_index)

    def _apply_board_status(self):
        worker = self._require_worker()
        if worker is not None:
            worker.set_register(0, self.board_status_combo.currentData())

    def _apply_power_status(self):
        worker = self._require_worker()
        if worker is None:
            return
        value = self.power_status_combo.currentData()
        worker.set_register(1, value)


    def _apply_control_mode(self):
        worker = self._require_worker()
        if worker is None:
            return
        value = self.control_mode_combo.currentData()
        worker.set_register(2, value)

    def _apply_tb_count(self):
        worker = self._require_worker()
        if worker is None:
            return
        new_count = self.tb_count_spin.value()
        old_count = self.active_tb_count
        if new_count == old_count:
            return

        tb_config = self.config["tb"]
        for tb_index in range(min(old_count, new_count), max(old_count, new_count)):
            tb_start = (
                tb_config["start_address"]
                + tb_index * tb_config["registers_per_device"]
            )
            activating = new_count > old_count
            for field in tb_config["fields"]:
                address = tb_start + field["offset"]
                value = field.get("initial", 0) if activating else 0
                self.register_values[address] = value
                worker.set_register(address, value)

        self.active_tb_count = new_count
        worker.set_active_tb_count(new_count)
        self._rebuild_table()
        self._update_log(f"활성 TB 수가 {new_count}개로 변경되었습니다.")

    def _update_log(self, message):
        current_time = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{current_time}] {message}")
        scroll_bar = self.log_text.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def _show_error(self, message):
        self._update_log("통신 또는 시뮬레이션에 문제가 발생했습니다. 포트 연결과 설정을 확인해 주세요.")
        dialog = QMessageBox(QMessageBox.Critical, "통신 / 시뮬레이션 오류",
                             "정상적으로 처리하지 못했습니다. 통신 포트와 연결 상태를 확인해 주세요.",
                             parent=self)
        dialog.setDetailedText(message)
        dialog.exec()

    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.stop_server()
            self.worker.wait(3000)
        event.accept()
