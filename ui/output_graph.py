"""Bounded, one-second history with independent axes for each physical unit."""
from collections import deque
from collections.abc import Mapping
from array import array
from math import isnan
from time import monotonic

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from config.register_map import raw_to_physical


RETENTION_SECONDS = 24 * 60 * 60
TIME_RANGES = [("1분", 60), ("5분", 300), ("30분", 1800),
               ("1시간", 3600), ("6시간", 21600), ("12시간", 43200),
               ("하루", RETENTION_SECONDS)]


class CompactSample(Mapping):
    """Store a day's numeric readings without a dictionary per sample."""
    def __init__(self, register_map, active, values):
        self.values = array("d", [float("nan")]) * (max(register_map) + 1)
        for address, register in register_map.items():
            if address in active and register.get("unit"):
                self.values[address] = raw_to_physical(register, values[address])

    def __getitem__(self, address):
        if not 0 <= address < len(self.values) or isnan(self.values[address]):
            raise KeyError(address)
        return self.values[address]

    def __iter__(self):
        return (a for a, value in enumerate(self.values) if not isnan(value))

    def __len__(self):
        return sum(1 for _ in self)


def reduced_series(history, address, start, span, width):
    """Keep each pixel's first, minimum, maximum and last point, and gaps."""
    result = []
    bucket = []
    previous_pixel = None

    def flush():
        if bucket:
            points = {bucket[0], min(bucket, key=lambda p: p[1]),
                      max(bucket, key=lambda p: p[1]), bucket[-1]}
            result.extend(sorted(points))
            bucket.clear()

    for timestamp, sample in history:
        if address not in sample:
            flush()
            if result and result[-1] is not None:
                result.append(None)
            previous_pixel = None
            continue
        pixel = int((timestamp - start) / span * width)
        if pixel != previous_pixel:
            flush()
        bucket.append((timestamp, sample[address]))
        previous_pixel = pixel
    flush()
    return result


class TrendCanvas(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setMinimumHeight(230)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        groups = {}
        for address in self.owner.selected_addresses():
            register = self.owner.register_map[address]
            groups.setdefault(register["unit"], []).append(address)
        if not groups or not self.owner.history:
            painter.setPen(QColor("#526175"))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "표시할 항목을 선택해 주세요." if not groups else
                             "서버를 시작하면 출력 변화가 여기에 표시됩니다.")
            return
        history = self.owner.visible_history()
        end = self.owner.history[-1][0]
        span = self.owner.range_combo.currentData()
        start = end - span
        height = self.height() / len(groups)
        for index, (unit, addresses) in enumerate(groups.items()):
            rect = QRectF(76, index * height + 22, max(1, self.width() - 96), height - 48)
            series = {a: reduced_series(history, a, start, span, rect.width())
                      for a in addresses}
            values = [point[1] for points in series.values() for point in points
                      if point is not None]
            if not values:
                continue
            low, high = min(values), max(values)
            margin = max((high - low) * .1, .1 if unit != "mV" else 1)
            low, high = low - margin, high + margin
            painter.setPen(QColor("#526175"))
            painter.drawText(QRectF(8, index * height, 150, 20), unit)
            for fraction in (0, .5, 1):
                y = rect.bottom() - fraction * rect.height()
                painter.setPen(QColor("#E5EAF0"))
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                painter.setPen(QColor("#526175"))
                painter.drawText(QRectF(0, y - 9, 69, 18), Qt.AlignRight,
                                 f"{low + fraction * (high - low):.1f}")
            for address in addresses:
                painter.setPen(QPen(self.owner.color(address), 2))
                path = QPainterPath()
                connected = False
                for sample in series[address]:
                    if sample is None:
                        connected = False
                        continue
                    timestamp, value = sample
                    point = QPointF(rect.left() + (timestamp - start) / span * rect.width(),
                                    rect.bottom() - (value - low) / (high - low) * rect.height())
                    if connected:
                        path.lineTo(point)
                    else:
                        path.moveTo(point)
                        painter.drawEllipse(point, 2, 2)
                    connected = True
                painter.drawPath(path)
            painter.setPen(QColor("#526175"))
            painter.drawText(QRectF(rect.left(), rect.bottom() + 3, rect.width(), 20),
                             Qt.AlignLeft, f"{self.owner.range_combo.currentText()} 전")
            painter.drawText(QRectF(rect.left(), rect.bottom() + 3, rect.width(), 20),
                             Qt.AlignRight, "최근 기록")


class OutputGraph(QWidget):
    def __init__(self, register_map):
        super().__init__()
        self.register_map = register_map
        self.history = deque(maxlen=RETENTION_SECONDS + 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("출력 그래프 · 조회 범위"))
        self.range_combo = QComboBox()
        for label, seconds in TIME_RANGES:
            self.range_combo.addItem(label, seconds)
        self.range_combo.setCurrentIndex(1)
        self.range_combo.setToolTip("최근 기록을 기준으로 표시합니다. 기록이 없는 시간은 빈 공간으로 표시됩니다.")
        heading.addWidget(self.range_combo)
        heading.addWidget(QLabel("1초 간격 · 최대 하루 보관 · 단위별 자동 눈금"))
        heading.addStretch()
        layout.addLayout(heading)
        split = QSplitter(Qt.Horizontal)
        self.items = QListWidget()
        self.items.setMinimumWidth(180)
        self.items.setMaximumWidth(270)
        self.items.itemChanged.connect(self._selection_changed)
        split.addWidget(self.items)
        self.canvas = TrendCanvas(self)
        self.range_combo.currentIndexChanged.connect(self.canvas.update)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        split.addWidget(scroll)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.set_active_registers(list(register_map.values()))

    def color(self, address):
        return QColor.fromHsv((address * 137) % 360, 185, 170)

    def selected_addresses(self):
        return [self.items.item(i).data(Qt.UserRole) for i in range(self.items.count())
                if not self.items.item(i).isHidden()
                and self.items.item(i).checkState() == Qt.Checked]

    def set_active_registers(self, registers):
        active = {r["address"] for r in registers}
        if not self.items.count():
            for address, register in self.register_map.items():
                if not register.get("unit"):
                    continue
                item = QListWidgetItem(register["label"])
                item.setData(Qt.UserRole, address)
                item.setForeground(self.color(address))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if address in (3, 5, 6) or
                                   register["name"].endswith("measured_potential") else Qt.Unchecked)
                self.items.addItem(item)
        self.active = active
        for i in range(self.items.count()):
            item = self.items.item(i)
            item.setHidden(item.data(Qt.UserRole) not in active)
        self._selection_changed()

    def _selection_changed(self, *args):
        units = {self.register_map[a]["unit"] for a in self.selected_addresses()}
        self.canvas.setMinimumHeight(max(230, len(units) * 105))
        self.canvas.update()

    def sample(self, values):
        now = monotonic()
        self.history.append((now, CompactSample(self.register_map, self.active, values)))
        while self.history and self.history[0][0] < now - RETENTION_SECONDS:
            self.history.popleft()
        self.canvas.update()

    def visible_history(self):
        if not self.history:
            return []
        cutoff = self.history[-1][0] - self.range_combo.currentData()
        visible = []
        for entry in reversed(self.history):
            if entry[0] < cutoff:
                break
            visible.append(entry)
        visible.reverse()
        return visible

    def clear(self):
        self.history.clear()
        self.canvas.update()
