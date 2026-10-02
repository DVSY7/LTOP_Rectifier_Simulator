import asyncio
from contextvars import ContextVar
from time import monotonic

from config.register_map import build_register_map, format_register_value

from PySide6.QtCore import QThread, Signal
from pymodbus import FramerType
from pymodbus.server import ModbusSerialServer
from pymodbus.simulator import DataType, SimData, SimDevice

from models.environment_runtime import EnvironmentRuntime
from simulation.rectifier_model import RectifierModel


class ModbusWorker(QThread):
    server_status = Signal(str)
    register_changed = Signal(int, int)
    communication_log = Signal(str)
    server_error = Signal(str)

    def __init__(self, config, initial_values):
        super().__init__()
        self.config = config
        self.values = list(initial_values)

        self.register_map = build_register_map(config)
        self._last_read_log = None
        self._local_write = ContextVar("local_write", default=False)
        self._loop = None
        self._server = None
        self._simulation_task = None
        self._rectifier = RectifierModel(
            config["simulation"],
            initial_output_voltage=self.values[5] / 10.0,
        )
        self._active_tb_count = int(config["tb"]["active_count"])
        self._environment = EnvironmentRuntime(
            config["environment_models"],
            self.values,
            config["tb"],
        )

        self._previous_power_status = None
        self._previous_set_voltage = None

    async def register_action(
        self,
        function_code,
        device_id,
        address,
        count,
        current_values,
        set_values,
    ):
        if self._local_write.get():
            return None
        if set_values is not None:
            for offset, value in enumerate(set_values):
                changed_address = address + offset
                int_value = int(value)

                if changed_address < len(self.values):
                    self.values[changed_address] = int_value

                self.register_changed.emit(changed_address, int_value)

                self._log_change(changed_address, int_value)
        else:
            now = monotonic()
            if self._last_read_log is None or now - self._last_read_log >= 10:
                self._last_read_log = now
                self.communication_log.emit("통신 요청을 정상적으로 받았습니다. 연결된 장치가 현재 값을 확인하고 있습니다.")
                for read_address in range(address, address + count):
                    register = self.register_map.get(read_address)
                    if register and (read_address in (5, 6) or
                                     register["name"].endswith("measured_potential")):
                        if register.get("tb_number", 0) > self._active_tb_count:
                            continue
                        self.communication_log.emit(
                            f"{register['label']}: {format_register_value(register, self.values[read_address])}입니다."
                        )

        return None

    async def _update_register(self, address, value):
        value = int(value)

        if address >= len(self.values) or self.values[address] == value:
            return

        await self._write_local(address, value)

        self.values[address] = value
        self.register_changed.emit(address, value)

    async def _write_local(self, address, value):
        # Local model updates also invoke the pymodbus action callback.
        # Keep them out of the external communication log.
        token = self._local_write.set(True)
        try:
            await self._server.async_setValues(
                self.config["communication"]["slave_id"], 6, address, [value]
            )
        finally:
            self._local_write.reset(token)

    async def _simulation_loop(self):
        await self._update_register(4, self._rectifier.initial_input_voltage_raw())

        while True:
            try:
                power_status = self.values[1]
                set_voltage = self.values[3] / 10.0
                updates = self._rectifier.step(power_status, set_voltage)

                await self._update_register(5, updates[5])

                environment_result = self._environment.step(
                    power_status=power_status,
                    output_voltage=updates[5] / 10.0,
                    active_tb_count=self._active_tb_count,
                )
                if environment_result is not None:
                    for address, value in environment_result["registers"].items():
                        await self._update_register(address, value)

                    if environment_result["mode_changed"]:
                        descriptions = {
                            "MODEL": "학습 모델로 출력전류와 TB 측정전위를 계산하고 있습니다.",
                            "FALLBACK": "학습 범위 밖의 전압이므로 대체 계산식으로 출력전류와 TB 측정전위를 계산하고 있습니다.",
                            "OFF": "정류기 전원이 꺼져 잔류 출력 상태로 전환하고 있습니다.",
                        }
                        self.communication_log.emit(descriptions[environment_result["mode"]])

                if (
                    power_status != self._previous_power_status
                    or updates["set_voltage"] != self._previous_set_voltage
                ):
                    state = "켜짐" if power_status == 1 else "꺼짐"
                    self.communication_log.emit(
                        f"정류기 전원은 {state} 상태입니다. "
                        f"설정전압은 {updates['set_voltage']:.1f} V, "
                        f"출력 목표는 {updates['target_voltage']:.1f} V입니다."
                    )
                    self._previous_power_status = power_status
                    self._previous_set_voltage = updates["set_voltage"]

                await asyncio.sleep(self._rectifier.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as error:
                self.server_error.emit(f"시뮬레이션 오류: {error}")
                await asyncio.sleep(self._rectifier.update_interval)

    def run(self):
        try:
            asyncio.run(self._run_server())
        except Exception as error:
            self.server_error.emit(str(error))
            self.server_status.emit("서버 오류")

    async def _run_server(self):
        communication = self.config["communication"]
        self._loop = asyncio.get_running_loop()

        device = SimDevice(
            id=communication["slave_id"],
            simdata=[
                SimData(
                    address=0,
                    values=self.values,
                    datatype=DataType.REGISTERS,
                )
            ],
            action=self.register_action,
        )

        self._server = ModbusSerialServer(
            context=[device],
            port=communication["port"],
            framer=FramerType.RTU,
            baudrate=communication["baudrate"],
            bytesize=communication["bytesize"],
            parity=communication["parity"],
            stopbits=communication["stopbits"],
        )

        await self._server.serve_forever(background=True)
        self.server_status.emit("RTU 서버 실행 중")
        self._simulation_task = asyncio.create_task(self._simulation_loop())

        try:
            await self._server.serving
        finally:
            if self._simulation_task is not None:
                self._simulation_task.cancel()
                try:
                    await self._simulation_task
                except asyncio.CancelledError:
                    pass

    def set_register(self, address, value):
        if self._loop is None or self._server is None:
            return

        address = int(address)
        value = int(value)
        future = asyncio.run_coroutine_threadsafe(
            self._write_local(address, value),
            self._loop,
        )

        def completed(result):
            try:
                result.result()
                if address < len(self.values):
                    self.values[address] = value
                self.register_changed.emit(address, value)
                self._log_change(address, value)
            except Exception as error:
                self.server_error.emit(str(error))

        future.add_done_callback(completed)

    def _log_change(self, address, value):
        register = self.register_map.get(address)
        if register is None:
            return
        self.communication_log.emit(
            f"{register['label']} 변경 완료: {format_register_value(register, value)}."
        )

    def stop_server(self):
        if self._loop is None or self._server is None:
            return

        asyncio.run_coroutine_threadsafe(self._server.shutdown(), self._loop)

    def set_active_tb_count(self, count):
        self._active_tb_count = int(count)
