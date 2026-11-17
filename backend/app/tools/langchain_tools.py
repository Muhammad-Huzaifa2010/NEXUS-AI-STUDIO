import json

from pydantic import BaseModel, Field
from langchain_core.tools import tool

from app.tools.registry import execute_tool


class CalculatorInput(BaseModel):
    expression: str = Field(
        description="A mathematical expression using basic arithmetic operators."
    )


class UnitConverterInput(BaseModel):
    value: float = Field(description="The numeric value to convert.")
    from_unit: str = Field(description="Original unit, such as km, kg, or c.")
    to_unit: str = Field(description="Target unit, such as m, lb, or f.")


@tool("calculator", args_schema=CalculatorInput)
def calculator_tool(expression: str) -> str:
    """Calculate a mathematical expression."""
    result = execute_tool("calculator", {"expression": expression})
    return json.dumps(result)


@tool("unit_converter", args_schema=UnitConverterInput)
def unit_converter_tool(
    value: float,
    from_unit: str,
    to_unit: str,
) -> str:
    """Convert length, mass, and temperature units."""
    result = execute_tool(
        "unit_converter",
        {
            "value": value,
            "from_unit": from_unit,
            "to_unit": to_unit,
        },
    )
    return json.dumps(result)
