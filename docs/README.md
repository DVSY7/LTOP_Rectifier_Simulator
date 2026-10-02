# 정류기 RTU 시뮬레이터

## 화면 사용 안내 (2026-09-30)

- 상단의 색상 버튼과 제어 항목 이름을 클릭하면 오른쪽에 변경 방법과 영향이 표시됩니다. 표의 항목을 한 번 클릭해도 해당 설명을 볼 수 있습니다.
- 파란색은 상단에서 선택 후 적용, 노란색은 현재 값을 더블클릭해 입력, 회색은 모델이 계산하는 값입니다.
- 표에는 항목과 실제 단위로 환산한 현재 값을 표시합니다. 통신 주소와 원시값은 숨겼습니다.
- 그래프 왼쪽 목록에서 항목을 체크하거나 해제합니다. 설정전압·출력전압·출력전류·활성 TB 측정전위가 기본 선택되며, 단위별로 그래프가 나뉩니다.
- 그래프는 서버 실행 중 1초 간격으로 최대 하루를 기록합니다. 조회 범위는 1분·5분·30분·1시간·6시간·12시간·하루 중 선택하며, 기본값은 5분입니다. 범위를 바꿔도 기록은 유지되고, 기록이 없는 시간은 빈 공간으로 표시됩니다. 정지하면 마지막 기록을 유지하고, 서버를 다시 시작하면 새 기록을 시작합니다. 기록은 파일에 저장하지 않습니다. 표와 그래프 사이 경계선을 드래그해 높이를 조절할 수 있습니다.
- 통신 기록에는 설정 변경과 실제 통신 요청 수신을 쉬운 문장으로 표시합니다. 반복 조회 기록은 최대 10초에 한 번 표시하며, 모델의 매 갱신마다 기록을 추가하지 않습니다. 서버 시작 안내는 실제 장치와 통신했다는 의미가 아닙니다.
- 오류의 기술적인 내용은 오류 창의 상세 정보에서 확인할 수 있습니다.

자동 검증: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`

실제 직렬 통신 검증은 USB-Serial 장치 및 상대 장치 연결 후 진행해야 합니다.

산업용 PC HMI의 Modbus RTU Master 요청에 응답하는 정류기 Slave 시뮬레이터입니다.

## 실행

```powershell
python main.py
```

`rtu_test.py`와 동시에 실행하면 COM 포트 충돌이 발생합니다.

## 모듈

- `communication`: Modbus RTU 서버 및 레지스터 I/O
- `config`: 통신/레지스터 설정과 레지스터 맵 생성
- `simulation`: 정류기 물리 응답 시뮬레이션
- `models`: 이후 연결할 전류/TB 학습모델
- `ui`: PySide6 화면
- `tests`: 설정 및 레지스터 맵 테스트

## 환경모델 동작

- `ENV MODE=MODEL`: 학습된 Current/TB RandomForest 모델 사용
- `ENV MODE=FALLBACK`: 학습 전압 범위 밖에서 등가저항 기반 대체식 사용
- `ENV MODE=OFF`: 전원이 꺼져 잔류전류로 감쇠

환경모델 갱신주기는 `config/registers.yaml`의
`environment_models.update_interval`에서 조절합니다. UI 갱신주기와 분리되어 있습니다.
# 정류기 RTU 시뮬레이터

## 실행 순서

1. USB-Serial 장치를 PC에 연결합니다.
2. 프로그램을 실행합니다.
3. 상단 `통신 포트`에서 사용할 COM 포트를 선택합니다.
4. 포트가 보이지 않으면 `새로고침`을 누릅니다.
5. `서버 시작`을 누르면 Modbus RTU 서버가 실행됩니다.
6. 서버 실행 중에는 포트를 변경할 수 없습니다. 다른 포트를 사용하려면 먼저 `서버 정지`를 누릅니다.

FTDI `VID:PID=0403:6001` 장치를 발견하면 우선 선택하며, 마지막으로 사용한 포트가 현재도 존재하면 그 포트를 먼저 선택합니다.

## Windows 실행파일 빌드

가상환경에 의존성을 설치합니다.

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

오류 확인용 콘솔 버전:

```powershell
.\build_windows.ps1 -Mode Debug
```

최종 GUI 버전:

```powershell
.\build_windows.ps1 -Mode Release
```

결과는 각각 아래에 생성됩니다.

```text
dist\RectifierSimulatorDebug\RectifierSimulatorDebug.exe
dist\RectifierSimulator\RectifierSimulator.exe
```

`onedir` 빌드이므로 배포할 때는 EXE만 꺼내지 말고 생성된 폴더 전체를 복사해야 합니다.
