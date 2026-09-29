import asyncio

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

        self._read_request_count = 0
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
        if set_values is not None:
            for offset, value in enumerate(set_values):
                changed_address = address + offset
                int_value = int(value)

                if changed_address < len(self.values):
                    self.values[changed_address] = int_value

                self.register_changed.emit(changed_address, int_value)

            self.communication_log.emit(
                f"WRITE FC={function_code:#04x}, "
                f"ADDR={address}, VALUES={list(set_values)}"
            )
        else:
            self._read_request_count += 1

            if self._read_request_count == 1 or self._read_request_count % 15 == 0:
                end_address = address + count - 1
                self.communication_log.emit(
                    f"POLL FC={function_code:#04x}, "
                    f"ADDR={address}~{end_address}, COUNT={count}"
                )

        return None

    async def _update_register(self, address, value):
        value = int(value)

        if address >= len(self.values) or self.values[address] == value:
            return

        await self._server.async_setValues(
            self.config["communication"]["slave_id"],
            6,
            address,
            [value],
        )

        self.values[address] = value
        self.register_changed.emit(address, value)

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
                        self.communication_log.emit(
                            f"ENV MODE={environment_result['mode']}, "
                            f"V={updates[5] / 10.0:.1f}V, "
                            f"I={environment_result['current']:.2f}A"
                        )

                if (
                    power_status != self._previous_power_status
                    or updates["set_voltage"] != self._previous_set_voltage
                ):
                    state = "ON" if power_status == 1 else "OFF"
                    self.communication_log.emit(
                        f"SIM POWER={state}, "
                        f"SET={updates['set_voltage']:.1f}V, "
                        f"TARGET={updates['target_voltage']:.1f}V"
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

        self.server_status.emit("RTU 서버 실행 중")
        self._simulation_task = asyncio.create_task(self._simulation_loop())

        try:
            await self._server.serve_forever()
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
            self._server.async_setValues(
                self.config["communication"]["slave_id"],
                6,
                address,
                [value],
            ),
            self._loop,
        )

        def completed(result):
            try:
                result.result()
                if address < len(self.values):
                    self.values[address] = value
                self.register_changed.emit(address, value)
            except Exception as error:
                self.server_error.emit(str(error))

        future.add_done_callback(completed)

    def stop_server(self):
        if self._loop is None or self._server is None:
            return

        asyncio.run_coroutine_threadsafe(self._server.shutdown(), self._loop)

    def set_active_tb_count(self, count):
        self._active_tb_count = int(count)
