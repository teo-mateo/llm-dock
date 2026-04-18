"""SymPy MCP Server — exposes symbolic math tools via stdio."""

from mcp.server.fastmcp import FastMCP
import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

mcp = FastMCP("sympy-math")

TRANSFORMS = standard_transformations + (implicit_multiplication_application,)


def _parse(expr_str: str):
    """Parse a string into a SymPy expression."""
    return parse_expr(expr_str, transformations=TRANSFORMS)


@mcp.tool()
def solve_equation(equation: str, variable: str = "x") -> str:
    """Solve an equation symbolically.

    The equation should be in the form 'expression = 0' (just provide the expression).
    Examples: solve_equation("x**2 - 4") returns [-2, 2]
              solve_equation("2*x + 3") returns [-3/2]
    """
    var = sympy.Symbol(variable)
    expr = _parse(equation)
    result = sympy.solve(expr, var)
    return str(result)


@mcp.tool()
def simplify_expression(expression: str) -> str:
    """Simplify a mathematical expression.

    Example: simplify_expression("(x**2 - 1)/(x - 1)") returns "x + 1"
    """
    expr = _parse(expression)
    return str(sympy.simplify(expr))


@mcp.tool()
def differentiate(expression: str, variable: str = "x", order: int = 1) -> str:
    """Compute the derivative of an expression.

    Example: differentiate("x**3 * sin(x)") returns "x**3*cos(x) + 3*x**2*sin(x)"
    """
    var = sympy.Symbol(variable)
    expr = _parse(expression)
    result = sympy.diff(expr, var, order)
    return str(result)


@mcp.tool()
def integrate_expression(expression: str, variable: str = "x") -> str:
    """Compute the indefinite integral of an expression.

    Example: integrate_expression("x**2") returns "x**3/3"
    """
    var = sympy.Symbol(variable)
    expr = _parse(expression)
    result = sympy.integrate(expr, var)
    return str(result)


@mcp.tool()
def definite_integral(expression: str, variable: str = "x", lower: str = "0", upper: str = "1") -> str:
    """Compute a definite integral.

    Example: definite_integral("x**2", "x", "0", "1") returns "1/3"
    """
    var = sympy.Symbol(variable)
    expr = _parse(expression)
    a = _parse(lower)
    b = _parse(upper)
    result = sympy.integrate(expr, (var, a, b))
    return str(result)


@mcp.tool()
def evaluate_expression(expression: str, precision: int = 15) -> str:
    """Evaluate a mathematical expression numerically.

    Example: evaluate_expression("sqrt(2) * pi") returns "4.44288293815837"
    """
    expr = _parse(expression)
    result = expr.evalf(precision)
    return str(result)


@mcp.tool()
def to_latex(expression: str) -> str:
    """Convert a mathematical expression to LaTeX notation.

    Example: to_latex("sqrt(x**2 + 1)/2") returns "\\frac{\\sqrt{x^{2} + 1}}{2}"
    """
    expr = _parse(expression)
    return sympy.latex(expr)


@mcp.tool()
def expand_expression(expression: str) -> str:
    """Expand a mathematical expression.

    Example: expand_expression("(x + 1)**3") returns "x**3 + 3*x**2 + 3*x + 1"
    """
    expr = _parse(expression)
    return str(sympy.expand(expr))


@mcp.tool()
def factor_expression(expression: str) -> str:
    """Factor a mathematical expression.

    Example: factor_expression("x**2 - 4") returns "(x - 2)*(x + 2)"
    """
    expr = _parse(expression)
    return str(sympy.factor(expr))


@mcp.tool()
def limit_expression(expression: str, variable: str = "x", point: str = "oo") -> str:
    """Compute the limit of an expression.

    Use 'oo' for infinity, '-oo' for negative infinity.
    Example: limit_expression("sin(x)/x", "x", "0") returns "1"
    """
    var = sympy.Symbol(variable)
    expr = _parse(expression)
    pt = sympy.oo if point == "oo" else (-sympy.oo if point == "-oo" else _parse(point))
    result = sympy.limit(expr, var, pt)
    return str(result)


@mcp.tool()
def matrix_operation(matrix_str: str, operation: str = "det") -> str:
    """Perform matrix operations.

    matrix_str: Matrix in format "[[1,2],[3,4]]"
    operation: One of "det", "inv", "eigenvals", "eigenvects", "rank", "transpose", "rref", "nullspace", "charpoly"
    Example: matrix_operation("[[1,2],[3,4]]", "det") returns "-2"
    """
    import ast
    data = ast.literal_eval(matrix_str)
    m = sympy.Matrix(data)
    x = sympy.Symbol('x')
    ops = {
        "det": lambda: m.det(),
        "inv": lambda: m.inv(),
        "eigenvals": lambda: m.eigenvals(),
        "eigenvects": lambda: m.eigenvects(),
        "rank": lambda: m.rank(),
        "transpose": lambda: m.T,
        "rref": lambda: m.rref(),
        "nullspace": lambda: m.nullspace(),
        "charpoly": lambda: m.charpoly(x),
    }
    if operation not in ops:
        return f"Unknown operation '{operation}'. Use: {', '.join(ops.keys())}"
    return str(ops[operation]())


if __name__ == "__main__":
    mcp.run(transport="stdio")
