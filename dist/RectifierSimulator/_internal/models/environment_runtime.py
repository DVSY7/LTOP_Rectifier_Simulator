import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


class EnvironmentRuntime:
    """학습된 전류/TB 모델을 RTU 시뮬레이터의 레지스터 값으로 변환한다."""

    def __init__(self, config, initial_values, tb_config):
        self.config = config
        self.tb_config = tb_config
        self.enabled = bool(config.get("enabled", True))
        self.update_interval = float(config.get("update_interval", 1.0))
        self.valid_voltage_min = float(config.get("valid_voltage_min", 42.1))
        self.valid_voltage_max = float(config.get("valid_voltage_max", 45.1))
        self.model_voltage_min = float(config.get("model_voltage_min", 43.3133))
        self.model_voltage_max = float(config.get("model_voltage_max", 43.9525))
        self.current_control_gain = float(config.get("current_control_gain", 0.17))
        self.max_delta_v_per_step = float(config.get("max_delta_v_per_step", 0.2))
        self.tb_control_weight = float(config.get("tb_control_weight", 10.0))
        self.tb_control_limit = float(config.get("tb_control_limit", 3.0))
        self.fallback_resistance = float(config.get("fallback_resistance", 7.37))
        self.off_residual_current = float(config.get("off_residual_current", 0.15))
        self.initial_tb = float(config.get("initial_tb", -1593.0))

        model_dir = Path(__file__).resolve().parent
        self.current_model = joblib.load(model_dir / config["current_model_file"])
        self.tb_model = joblib.load(model_dir / config["tb_model_file"])

        for model in (self.current_model, self.tb_model):
            if hasattr(model, "n_jobs"):
                model.n_jobs = 1

        self.current = float(config.get("initial_current", 0.15))
        self.reference_current = float(config.get("reference_current", 5.91))
        self.previous_voltage = None
        self.control_current_offset = 0.0
        self.last_update = 0.0
        self.tb_histories = {}
        self.last_mode = None

        self._initialize_tb_histories(initial_values, tb_config["max_count"])

    def _initialize_tb_histories(self, values, max_count):
        start = self.tb_config["start_address"]
        width = self.tb_config["registers_per_device"]

        for index in range(max_count):
            address = start + index * width + 2
            tb_value = -float(values[address]) if values[address] else self.initial_tb
            self.tb_histories[index + 1] = [tb_value] * 7

    def _predict_current(self, voltage, delta_v):
        model_voltage = float(
            np.clip(voltage, self.model_voltage_min, self.model_voltage_max)
        )
        model_input = pd.DataFrame(
            {
                "Rectifier_Current": [self.current],
                "Rectifier_Voltage": [model_voltage],
                "Delta_V": [0.0],
            }
        )
        natural_delta = float(self.current_model.predict(model_input)[0])
        action_delta = self.current_control_gain * delta_v
        self.current = max(0.0, self.current + natural_delta + action_delta)
        self.control_current_offset += action_delta
        return action_delta

    def _predict_tb(self, tb_number, control_current_offset):
        history = self.tb_histories[tb_number]
        tb_t = history[-1]
        lag1 = history[-2]
        lag2 = history[-3]
        lag3 = history[-4]
        lag6 = history[-7]
        model_input = pd.DataFrame(
            {
                "TB1-Volt": [tb_t],
                "TB_Lag1": [lag1],
                "TB_Lag2": [lag2],
                "TB_Lag3": [lag3],
                "TB_Lag6": [lag6],
                "TB_Change_10m": [tb_t - lag1],
                "TB_Change_30m": [tb_t - lag3],
            }
        )
        natural_next = float(self.tb_model.predict(model_input)[0])
        control_effect = float(
            np.clip(
                -self.tb_control_weight * control_current_offset,
                -self.tb_control_limit,
                self.tb_control_limit,
            )
        )
        next_tb = natural_next + control_effect
        self.tb_histories[tb_number] = (history + [next_tb])[-7:]
        return next_tb

    def due(self):
        now = time.monotonic()
        if now - self.last_update < self.update_interval:
            return False
        self.last_update = now
        return True

    def step(self, power_status, output_voltage, active_tb_count):
        if not self.enabled or not self.due():
            return None

        output_voltage = float(output_voltage)
        updates = {}

        if int(power_status) != 1:
            self.current += 0.25 * (self.off_residual_current - self.current)
            if abs(self.current - self.off_residual_current) < 0.01:
                self.current = self.off_residual_current
            mode = "OFF"
        elif self.valid_voltage_min <= output_voltage <= self.valid_voltage_max:
            measured_delta_v = (
                0.0
                if self.previous_voltage is None
                else output_voltage - self.previous_voltage
            )
            delta_v = float(
                np.clip(
                    measured_delta_v,
                    -self.max_delta_v_per_step,
                    self.max_delta_v_per_step,
                )
            )
            self._predict_current(output_voltage, delta_v)
            mode = "MODEL"
        else:
            self.current = max(0.0, output_voltage / self.fallback_resistance)
            mode = "FALLBACK"

        self.previous_voltage = output_voltage
        updates[6] = max(0, min(65535, round(self.current * 10)))

        start = self.tb_config["start_address"]
        width = self.tb_config["registers_per_device"]
        for tb_number in range(1, active_tb_count + 1):
            if mode == "MODEL":
                tb_value = self._predict_tb(
                    tb_number,
                    self.control_current_offset,
                )
            else:
                # 학습범위 밖에서는 전류와 TB 방향성만 보존하는 안전한 대체식
                tb_value = self.initial_tb - self.tb_control_weight * (
                    self.current - self.reference_current
                )
                self.tb_histories[tb_number] = (
                    self.tb_histories[tb_number] + [tb_value]
                )[-7:]

            address = start + (tb_number - 1) * width + 2
            updates[address] = max(0, min(65535, round(-tb_value)))

        mode_changed = mode != self.last_mode
        self.last_mode = mode
        return {
            "registers": updates,
            "mode": mode,
            "mode_changed": mode_changed,
            "current": self.current,
        }
