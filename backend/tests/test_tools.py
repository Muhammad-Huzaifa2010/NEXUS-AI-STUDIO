import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.tools.calculator import calculate
from app.tools.unit_converter import convert_units
from app.tools.registry import execute_tool


class CalculatorTests(unittest.TestCase):
    def test_basic_expression(self):
        result = calculate("(12 + 8) * 3")
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], 60)

    def test_division_by_zero_is_rejected(self):
        result = calculate("10 / 0")
        self.assertFalse(result["success"])

    def test_complex_result_is_rejected(self):
        result = calculate("(-1) ** 0.5")
        self.assertFalse(result["success"])

    def test_infinite_literal_is_rejected(self):
        result = calculate("1e309")
        self.assertFalse(result["success"])
        self.assertIn("finite", result["error"].lower())

    def test_non_finite_intermediate_result_is_rejected(self):
        result = calculate("1e308 * 1e308")
        self.assertFalse(result["success"])
        self.assertIn("finite", result["error"].lower())

    def test_non_finite_operands_are_rejected(self):
        result = calculate("1e309 - 1e309")
        self.assertFalse(result["success"])
        self.assertIn("finite", result["error"].lower())

    def test_python_code_is_rejected(self):
        result = calculate("__import__('os').system('echo unsafe')")
        self.assertFalse(result["success"])


class UnitConverterTests(unittest.TestCase):
    def test_kilometers_to_meters(self):
        result = convert_units(2, "km", "m")
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], 2000)

    def test_temperature_conversion(self):
        result = convert_units(0, "c", "f")
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], 32)

    def test_below_absolute_zero_is_rejected(self):
        result = convert_units(-300, "c", "k")
        self.assertFalse(result["success"])

    def test_incompatible_units_are_rejected(self):
        result = convert_units(10, "kg", "km")
        self.assertFalse(result["success"])


class ToolRegistryTests(unittest.TestCase):
    def test_unknown_tool_is_not_executed(self):
        result = execute_tool("shell", {"command": "echo unsafe"})
        self.assertFalse(result["success"])

    def test_registered_calculator_tool(self):
        result = execute_tool("calculator", {"expression": "6 * 7"})
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], 42)


if __name__ == "__main__":
    unittest.main(verbosity=2)
