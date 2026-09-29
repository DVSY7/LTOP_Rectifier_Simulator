# 정류기 RTU 시뮬레이터

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
