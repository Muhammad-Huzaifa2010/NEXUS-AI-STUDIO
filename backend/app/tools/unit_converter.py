import math

UNIT_GROUPS = {
    "length": {
        "mm": 0.001,
        "cm": 0.01,
        "m": 1.0,
        "km": 1000.0,
        "in": 0.0254,
        "ft": 0.3048,
        "yd": 0.9144,
        "mi": 1609.344,
    },
    "mass": {
        "mg": 0.000001,
        "g": 0.001,
        "kg": 1.0,
        "oz": 0.028349523125,
        "lb": 0.45359237,
    },
}

ALIASES = {
    "meter": "m", "meters": "m",
    "metre": "m", "metres": "m",
    "kilometer": "km", "kilometers": "km",
    "kilometre": "km", "kilometres": "km",
    "centimeter": "cm", "centimeters": "cm",
    "millimeter": "mm", "millimeters": "mm",
    "inch": "in", "inches": "in",
    "foot": "ft", "feet": "ft",
    "yard": "yd", "yards": "yd",
    "mile": "mi", "miles": "mi",
    "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg",
    "milligram": "mg", "milligrams": "mg",
    "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb",
    "celsius": "c", "fahrenheit": "f", "kelvin": "k",
}


def normalize_unit(unit: str) -> str:
    unit = unit.strip().lower()
    return ALIASES.get(unit, unit)


def convert_temperature(value, source, target):
    if source == "c":
        celsius = value
    elif source == "f":
        celsius = (value - 32) * 5 / 9
    else:
        celsius = value - 273.15

    if celsius < -273.15 - 1e-9:
        raise ValueError("Temperature cannot be below absolute zero.")

    if target == "c":
        return celsius
    if target == "f":
        return celsius * 9 / 5 + 32
    return celsius + 273.15


def convert_units(value, from_unit, to_unit):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {"success": False, "error": "Value must be numeric."}

    if not math.isfinite(value):
        return {"success": False, "error": "Value must be finite."}

    if not isinstance(from_unit, str) or not isinstance(to_unit, str):
        return {"success": False, "error": "Units must be strings."}

    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)

    temperature_units = {"c", "f", "k"}

    if source in temperature_units and target in temperature_units:
        try:
            result = convert_temperature(value, source, target)
        except ValueError as error:
            return {"success": False, "error": str(error)}

    else:
        result = None

        for category, units in UNIT_GROUPS.items():
            if source in units and target in units:
                result = value * units[source] / units[target]
                break

        if result is None:
            return {
                "success": False,
                "error": f"Unsupported or incompatible units: {from_unit} to {to_unit}.",
            }

    if not math.isfinite(result):
        return {"success": False, "error": "Conversion result is invalid."}

    return {
        "success": True,
        "value": value,
        "from_unit": source,
        "to_unit": target,
        "result": round(result, 6),
    }
