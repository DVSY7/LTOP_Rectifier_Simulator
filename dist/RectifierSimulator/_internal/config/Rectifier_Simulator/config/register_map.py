def build_register_map(config):
    register_map = {}

    for register in config["registers"]:
        item = dict(register)
        item["device_type"] = "rectifier"
        register_map[item["address"]] = item

    tb_config = config["tb"]

    for tb_index in range(tb_config["max_count"]):
        tb_number = tb_index + 1
        tb_start = (
            tb_config["start_address"]
            + tb_index * tb_config["registers_per_device"]
        )

        for field in tb_config["fields"]:
            address = tb_start + field["offset"]
            item = dict(field)
            item["address"] = address
            item["name"] = f"tb{tb_number}_{field['name']}"
            item["label"] = f"TB{tb_number} {field['label']}"
            item["device_type"] = "tb"
            item["tb_number"] = tb_number
            register_map[address] = item

    return register_map


def build_initial_values(config, register_map):
    values = [0] * (max(register_map) + 1)
    active_count = config["tb"]["active_count"]

    for address, register in register_map.items():
        if register["device_type"] == "rectifier":
            values[address] = register.get("initial", 0)
        elif register["tb_number"] <= active_count:
            values[address] = register.get("initial", 0)

    return values


def format_register_value(register, raw_value):
    value_map = register.get("values")
    if value_map is not None:
        return str(value_map.get(raw_value, f"알 수 없음({raw_value})"))

    value = raw_value
    if "multiplier" in register:
        value *= register["multiplier"]
    if "divisor" in register:
        value /= register["divisor"]

    unit = register.get("unit", "")
    display = (
        f"{value:.2f}".rstrip("0").rstrip(".")
        if isinstance(value, float)
        else str(value)
    )
    return f"{display} {unit}".strip()


def raw_to_physical(register, raw_value):
    value = float(raw_value)
    if "multiplier" in register:
        value *= float(register["multiplier"])
    if "divisor" in register:
        value /= float(register["divisor"])
    return value


def physical_to_raw(register, physical_value):
    value = float(physical_value)
    if "multiplier" in register:
        multiplier = float(register["multiplier"])
        if multiplier != 0:
            value /= multiplier
    if "divisor" in register:
        value *= float(register["divisor"])
    return round(value)
