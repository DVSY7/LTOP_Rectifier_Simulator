# RTU 정류기 Simulator 개발 인수인계

## 1. 문서 목적

이 문서는 산업용 PC의 정류기 HMI와 Modbus RTU로 통신하면서 실제 정류기 제어보드 역할을 대신하는 Simulator 개발 내용을 기록한다.

나중에 개발을 다시 시작할 때 이 문서를 먼저 읽고, 확정된 내용과 아직 확인되지 않은 프로토콜 정보를 구분하여 작업한다.

## 2. 개발 목적

현재 실제 정류기 프로그램과 제어보드가 완성되지 않았으므로, 별도의 PC 프로그램이 가상 정류기 역할을 수행한다.

Simulator는 다음 기능을 제공해야 한다.

1. 산업용 PC HMI와 Modbus RTU 통신
2. 부팅 시 제어보드 연결 및 초기화 상태 응답
3. HMI가 보낸 설정전압 Write 수신
4. 설정전압 변화에 따른 출력전류 계산
5. 전류 및 전압 변화에 따른 TB 전위 계산
6. 계산된 출력전압·출력전류·TB 데이터를 레지스터에 반영
7. HMI의 Read 요청에 현재 레지스터값 응답
8. UI에서 통신·레지스터·모델 상태 확인 및 시험값 조정

## 3. 통신 역할

```text
[산업용 PC HMI]
Modbus RTU Master/Client
        │
        │ Read/Write 요청
        ▼
[정류기 Simulator]
Modbus RTU Slave/Server
        │
        ├─ Register Store
        ├─ 전류 변화 모델
        ├─ TB 변화 모델
        └─ UI
```

- 산업용 PC가 요청을 시작한다.
- Simulator가 먼저 데이터를 일방적으로 전송하지 않는다.
- Simulator는 산업용 PC의 Read 요청에 현재 레지스터값을 응답한다.
- 산업용 PC가 설정전압을 Write하면 Simulator가 해당 값을 저장하고 시스템 반응을 계산한다.

## 4. 초기화 상태 레지스터

산업용 PC HMI는 부팅 과정에서 제어보드와의 연결 및 초기화 상태를 확인하기 위해 Addr 0을 읽는다.

| Addr 0 값 | 의미 |
|---:|---|
| 0 | 준비 중 |
| 1 | 초기화 완료 |
| 2 | 초기화 스킵 |

### 기본 상태 흐름

```text
Simulator 실행
    ↓
Addr 0 = 0
    ↓
설정 파일 로드
통신 초기화
레지스터 초기화
환경모델 로드
    ↓
초기화 성공
    ↓
Addr 0 = 1
    ↓
산업용 PC가 Addr 0 Read
    ↓
Simulator가 값 1 응답
```

초기화에 실패하면 Addr 0은 0으로 유지하고 오류를 로그와 UI에 표시한다.

### 스킵 값 2의 소유권

아직 확인이 필요하다.

- Simulator가 모델 로딩을 생략할 때 자체적으로 2를 설정하는 방식인지
- 사용자가 HMI에서 스킵을 선택하고 산업용 PC가 2를 Write하는 방식인지
- 산업용 PC가 별도 명령 레지스터에 스킵 명령을 Write하는 방식인지

기존 HMI 프로토콜을 확인하기 전에는 추측하여 고정하지 않는다.

## 5. 첫 번째 구현 목표

환경모델보다 RTU 연결과 Addr 0 응답을 먼저 검증한다.

첫 번째 버전의 범위는 다음과 같다.

1. UI 실행
2. COM Port와 통신조건 선택
3. Modbus RTU Slave 시작·중지
4. 실행 직후 Addr 0을 0으로 설정
5. 초기화가 끝나면 Addr 0을 1로 변경
6. UI에서 0·1·2 상태를 시험용으로 수동 변경
7. 산업용 PC의 Addr 0 Read 요청에 현재값 응답
8. 요청과 응답을 UI 로그에 표시

첫 번째 버전에서는 아래 기능을 제외한다.

- 설정전압 Write 처리
- 전류모델
- TB모델
- 자동 시스템 반응
- 강화학습 모델
- 실제 장비 제어

### 첫 번째 버전 완료 조건

- 산업용 PC가 Simulator를 제어보드로 인식한다.
- HMI 부팅 시 통신 연결 확인 과정이 정상적으로 넘어간다.
- Addr 0의 0·1·2 값이 HMI에 의도대로 표시된다.
- 요청이 반복되어도 UI가 멈추지 않는다.
- RTU 요청과 응답이 로그에 기록된다.
- 통신 중지 및 재시작이 가능하다.

## 6. UI 권장 구성

Python과 PySide6를 이용한 Windows 데스크톱 프로그램을 우선 고려한다.

```text
┌────────────────────────────────────────────────────┐
│ 정류기 Simulator                                   │
├────────────────────────────────────────────────────┤
│ 통신 설정                                          │
│ COM Port / Baud / Data bits / Parity / Stop bits  │
│ Slave ID                  [통신 시작] [통신 중지] │
├──────────────────────┬─────────────────────────────┤
│ 초기화·통신 상태     │ 정류기 상태                 │
│ RTU 실행 여부        │ 설정전압                    │
│ 마지막 요청 시각     │ 출력전압                    │
│ Addr 0 현재값        │ 출력전류                    │
│ [준비][완료][스킵]   │ TB 전위                     │
├──────────────────────┴─────────────────────────────┤
│ 레지스터 모니터                                    │
│ 주소 / 이름 / 원시값 / 변환값 / R/W / 변경시각   │
├────────────────────────────────────────────────────┤
│ 통신 및 시뮬레이션 로그                            │
└────────────────────────────────────────────────────┘
```

### UI 기본 기능

- 사용 가능한 COM Port 목록 조회
- Baud rate, Parity, Data bits, Stop bits 선택
- Slave ID 입력
- 통신 시작·중지
- 초기화 상태 표시 및 시험용 수동 변경
- 레지스터값 실시간 표시
- RX/TX 및 오류 로그 표시
- 추후 자동반응과 수동값 설정 모드 전환

## 7. 프로그램 내부 구조

UI, RTU 통신, 환경모델 계산을 분리한다.

```text
UI Thread
├─ 화면 표시
├─ 버튼 이벤트
└─ 상태 조회

RTU Worker
├─ Modbus 요청 대기
├─ Read 응답
├─ Write 처리
└─ 통신 로그 전달

Simulation Worker
├─ 설정전압 변화 확인
├─ 전류모델 계산
├─ TB모델 계산
└─ 출력 레지스터 갱신

Register Store
└─ UI·RTU·Simulation이 공유하는 현재 상태
```

RTU 서버나 Simulation Loop를 UI 메인 스레드에서 무한 반복하지 않는다. UI가 멈추지 않도록 `QThread`, 별도 Thread 또는 비동기 Worker로 분리한다.

## 8. 핵심 Register Store

Register Store는 Simulator의 단일 상태 원본이다.

```text
산업용 PC Write
    ↓
RTU Worker
    ↓
Register Store의 설정전압 변경
    ↓
Simulation Worker가 변화 확인
    ↓
전류·TB 모델 계산
    ↓
Register Store의 출력값 변경
    ↓
산업용 PC Read 요청에 변경값 응답
```

UI도 Register Store에서 현재값을 읽어 화면에 표시한다.

RTU Worker와 Simulation Worker가 동시에 접근할 수 있으므로 Lock 또는 스레드 안전한 상태 관리 방식을 사용한다.

## 9. 권장 프로젝트 구조

```text
rectifier_simulator/
├─ main.py
├─ requirements.txt
├─ config/
│  ├─ serial.yaml
│  └─ register_map.yaml
├─ ui/
│  ├─ main_window.py
│  └─ widgets/
├─ communication/
│  ├─ rtu_server.py
│  └─ register_store.py
├─ simulation/
│  ├─ plant_state.py
│  └─ simulation_loop.py
├─ models/
│  ├─ current_model.py
│  └─ tb_model.py
├─ logging_config/
│  └─ logger.py
└─ tests/
   ├─ test_register_store.py
   ├─ test_initialization.py
   └─ test_model_response.py
```

첫 번째 단계에서는 `main.py`, `ui`, `communication`, `config`, `tests`만 구현한다.

## 10. 레지스터 설정 예시

주소와 배율을 Python 코드에 직접 작성하지 않고 YAML로 관리한다.

```yaml
registers:
  initialization_status:
    address: 0
    type: holding
    access: read
    values:
      preparing: 0
      completed: 1
      skipped: 2

  set_voltage:
    address: 3
    type: holding
    access: read_write
    scale: 0.1
    unit: V

  output_voltage:
    address: 5
    type: holding
    access: read
    scale: 0.1
    unit: V

  output_current:
    address: 6
    type: holding
    access: read
    scale: 0.1
    unit: A

  tb_potential:
    address: 12
    type: holding
    access: read
    scale: 1.0
    unit: mV
```

Addr 0 이외의 주소와 배율은 예시이며 HMI 프로토콜 확인 후 확정한다.

## 11. 환경모델 연결 방향

최종적으로 Simulator의 시스템 반응과 강화학습 학습 환경의 시스템 반응이 같은 원리를 사용해야 한다.

```text
설정전압 Vset 변경
    ↓
출력전압의 동적 반응 계산
    ↓
전류 변화 모델
    ↓
TB 변화 모델
    ↓
출력전압·출력전류·TB 레지스터 갱신
```

### 전류모델 개념

```text
입력: 이전 전압, 설정전압, 이전 전류, 전압 변화량, 필요 시 시간간격
출력: 다음 출력전류
```

### TB모델 개념

```text
입력: 이전 TB, 출력전압, 출력전류, 전압·전류 변화량, 필요 시 시간간격
출력: 다음 TB 전위
```

환경모델 파일을 UI나 RTU 코드에 직접 결합하지 않는다. 공통 인터페이스를 정의하여 Simulation Worker가 모델을 교체할 수 있게 한다.

```python
next_current = current_model.predict(current_state, set_voltage, dt)
next_tb = tb_model.predict(current_state, next_current, dt)
```

## 12. 시뮬레이션 주기

통신 응답과 시스템 반응 계산은 분리한다.

- RTU Worker: 산업용 PC 요청이 들어올 때마다 즉시 응답
- Simulation Worker: 설정된 계산 주기마다 상태 갱신
- UI: 별도의 화면 갱신 주기로 현재 상태 표시

예시:

```text
RTU 응답: 요청 기반
환경모델 계산: 1초마다
UI 화면 갱신: 0.2~0.5초마다
```

실제 계산 주기는 산업용 PC의 폴링주기와 환경모델의 학습 간격을 확인한 후 결정한다.

## 13. 단계별 개발 계획

### 1단계: Addr 0 통신

- UI 기본 화면
- Serial 설정
- RTU Slave 시작·중지
- Addr 0 상태값 응답
- RX/TX 로그

### 2단계: 기본 레지스터

- 설정전압 Write 수신
- 출력전압 Read
- 출력전류 Read
- TB 전위 Read
- 레지스터 모니터

### 3단계: 수동 Simulator

- UI에서 출력전압·전류·TB 값 수동 입력
- HMI에서 값이 정상 표시되는지 검증
- 자료형, 배율, signed 변환 검증

### 4단계: 전류모델

- 설정전압 변화 감지
- 전류모델 연동
- 출력전류 자동 갱신
- 동적 반응 및 제한값 적용

### 5단계: TB모델

- 전류·전압 변화에 따른 TB모델 연동
- TB 전위 자동 갱신
- 반응 지연 및 노이즈 설정

### 6단계: 통합검증

- 산업용 PC HMI와 연속 통신
- 엣지 제어 프로그램의 TCP 제어 반영
- 설정전압에서 전류·TB까지 폐루프 확인
- 로그 및 재현성 검증

## 14. 구현 전 확인사항

다음 정보가 확인되기 전에는 임의로 확정하지 않는다.

1. RS-232 또는 RS-485 구분
2. 산업용 PC와 Simulator 각각의 COM Port
3. Baud rate
4. Data bits
5. Parity
6. Stop bits
7. Modbus Slave ID
8. Addr 0의 Register 종류
9. Addr 0 Read Function Code
10. 주소 체계가 0-base인지 1-base인지
11. 스킵 값 2를 설정하는 주체
12. 설정전압 Write 주소와 Function Code
13. 출력전압·전류·TB 주소 및 배율
14. TB 음수값의 signed 변환 방식
15. 산업용 PC의 폴링주기

## 15. 다음 작업용 Codex 프롬프트

```text
RECTIFIER_SIMULATOR_CONTEXT.md를 먼저 읽고 지침을 준수해줘.

이번 작업은 정류기 Simulator 1단계만 구현한다.

목표:
- PySide6 기반 기본 UI
- Serial 통신 설정 입력
- Modbus RTU Slave 시작 및 중지
- Addr 0 Holding Register 제공
- 시작 시 Addr 0=0
- 초기화 완료 시 Addr 0=1
- UI에서 시험용으로 0/1/2 변경 가능
- 산업용 PC의 Addr 0 Read 요청과 응답을 UI 로그에 표시

제외 범위:
- 설정전압 Write
- 출력전압·전류·TB 레지스터
- 전류모델과 TB모델
- 강화학습 모델

먼저 현재 프로젝트 구조와 Git 상태를 확인하고 구현 계획을 제시해줘.
프로토콜 값이 불명확하면 추측하지 말고 TODO로 남겨줘.
```

