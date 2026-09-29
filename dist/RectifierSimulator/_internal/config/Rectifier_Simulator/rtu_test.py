from pymodbus import FramerType, pymodbus_apply_logging_config
from pymodbus.server import StartSerialServer
from pymodbus.simulator import DataType, SimData, SimDevice


PORT = "COM7"
SLAVE_ID = 9
BAUDRATE = 115200

# Holding Register 주소 0~99
# 주소 0의 초기값은 1(완료)
register_values = [1] + [0] * 99

device = SimDevice(
    id=SLAVE_ID,
    simdata=[
        SimData(
            address=0,
            values=register_values,
            datatype=DataType.REGISTERS,
        )
    ],
)

pymodbus_apply_logging_config("DEBUG")

print("=" * 50)
print("정류기 RTU 시뮬레이터 시작")
print(f"포트       : {PORT}")
print(f"Slave ID   : {SLAVE_ID}")
print(f"통신 설정  : {BAUDRATE}, 8-N-1")
print("주소 0 값  : 1 (완료)")
print("종료       : Ctrl+C")
print("=" * 50)

StartSerialServer(
    context=[device],
    port=PORT,
    framer=FramerType.RTU,
    baudrate=BAUDRATE,
    bytesize=8,
    parity="N",
    stopbits=1,
)