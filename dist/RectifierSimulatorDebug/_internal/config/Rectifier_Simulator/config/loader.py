from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).with_name("registers.yaml")


def load_config(path=None):
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)
