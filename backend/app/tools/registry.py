from app.tools.calculator import calculate
from app.tools.unit_converter import convert_units

TOOL_REGISTRY = {
    "calculator": {
        "description": "Evaluates basic mathematical expressions.",
        "function": calculate,
    },
    "unit_converter": {
        "description": "Converts length, mass, and temperature units.",
        "function": convert_units,
    },
}


def execute_tool(tool_name: str, arguments: dict):
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return {
            "success": False,
            "error": f"Tool '{tool_name}' is not approved.",
        }

    if tool_name == "calculator":
        expression = arguments.get("expression")
        if not isinstance(expression, str):
            return {"success": False, "error": "Expression must be a string."}
        return calculate(expression)

    if tool_name == "unit_converter":
        return convert_units(
            arguments.get("value"),
            arguments.get("from_unit"),
            arguments.get("to_unit"),
        )

    return {"success": False, "error": "Tool not implemented."}


def list_tools():
    return {
        name: details["description"]
        for name, details in TOOL_REGISTRY.items()
    }
