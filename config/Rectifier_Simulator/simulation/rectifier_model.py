import math


class RectifierModel:
    """설정전압에 대한 정류기 출력전압의 1차 지연 응답."""

    def __init__(self, config, initial_output_voltage=0.0):
        self.update_interval = float(config["update_interval"])
        self.input_voltage = float(config["input_voltage"])
        self.output_time_constant = float(config["output_time_constant"])
        self.max_output_voltage = float(config["max_output_voltage"])
        self.off_residual_voltage = float(
            config.get("off_residual_voltage", 0.15)
        )
        self.output_voltage = float(initial_output_voltage)
        self.response_rate = 1.0 - math.exp(
            -self.update_interval / self.output_time_constant
        )

    def initial_input_voltage_raw(self):
        return round(self.input_voltage * 10)

    def step(self, power_status, set_voltage):
        set_voltage = max(0.0, min(float(set_voltage), self.max_output_voltage))
        target_voltage = (
            set_voltage if int(power_status) == 1 else self.off_residual_voltage
        )

        self.output_voltage += self.response_rate * (
            target_voltage - self.output_voltage
        )

        if abs(target_voltage - self.output_voltage) < 0.01:
            self.output_voltage = target_voltage

        return {
            5: round(self.output_voltage * 10),
            "set_voltage": set_voltage,
            "target_voltage": target_voltage,
        }
