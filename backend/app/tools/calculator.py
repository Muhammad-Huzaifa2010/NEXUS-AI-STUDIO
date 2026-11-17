import ast
import math
import operator


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _ensure_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numbers are not supported.")
    return value


def evaluate(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric values are supported.")
        return _ensure_finite(node.value)

    if isinstance(node, ast.BinOp):
        operation = OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("Unsupported mathematical operator.")

        left = evaluate(node.left)
        right = evaluate(node.right)

        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise ValueError("Exponent is too large.")

        result = operation(left, right)

        if isinstance(result, complex) or not isinstance(result, (int, float)):
            raise ValueError("Complex or non-numeric results are not supported.")

        result = _ensure_finite(result)

        if abs(result) > 1e100:
            raise ValueError("Result is too large.")

        return result

    if isinstance(node, ast.UnaryOp):
        operation = OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("Unsupported unary operator.")
        return _ensure_finite(operation(evaluate(node.operand)))

    raise ValueError("Unsupported expression.")


def calculate(expression: str):
    if not expression or len(expression) > 200:
        raise ValueError("Expression must contain 1–200 characters.")

    try:
        tree = ast.parse(expression, mode="eval")
        result = evaluate(tree.body)
        return {
            "success": True,
            "expression": expression,
            "result": result,
        }
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
        return {
            "success": False,
            "expression": expression,
            "error": str(error),
        }
    except SyntaxError:
        return {
            "success": False,
            "expression": expression,
            "error": "Invalid mathematical expression.",
        }
