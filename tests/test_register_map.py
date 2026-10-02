from config.loader import load_config
from config.register_map import build_initial_values, build_register_map


def test_rectifier_and_tb_register_addresses():
    config = load_config()
    register_map = build_register_map(config)

    assert set(range(10)).issubset(register_map)
    assert register_map[10]["name"] == "tb1_min_potential"
    assert register_map[17]["name"] == "tb2_min_potential"
    assert max(register_map) == 121


def test_explore_mode_and_initial_values():
    config = load_config()
    config["tb"]["active_count"] = 2
    register_map = build_register_map(config)
    values = build_initial_values(config, register_map)

    assert register_map[2]["values"][2] == "탐색"
    assert values[0] == 1
    assert values[10] == 850
    assert values[17] == 850
    assert values[24] == 0


def test_environment_model_configuration():
    config = load_config()

    assert config["environment_models"]["enabled"] is True
    assert config["environment_models"]["current_model_file"].endswith(".joblib")
    assert config["environment_models"]["tb_model_file"].endswith(".joblib")
