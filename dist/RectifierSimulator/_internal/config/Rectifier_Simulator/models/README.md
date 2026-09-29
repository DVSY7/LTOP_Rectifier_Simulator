# Models

학습된 전류 모델과 TB 모델 파일 및 런타임 어댑터를 배치하는 폴더입니다.

- `current_model_v1.joblib`: 현재 전압·전류와 전압 변화에 대한 전류 예측기
- `tb_history_model_v1.joblib`: 최근 TB 이력에 대한 다음 TB 예측기
- `environment_runtime.py`: 모델 결과를 Modbus Raw 레지스터로 변환

학습 유효전압은 약 42.1~45.1V입니다. 이 범위 밖에서는 설정된 등가저항 기반
대체식을 사용하며, 통신 로그에 `ENV MODE=FALLBACK`으로 표시됩니다.
