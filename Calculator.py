import sympy as sp


class Tools:
    def __init__(self):
        pass

    def calculator(self, equation: str) -> str:
        """
        Calculate the result of an equation safely.
        :param equation: The equation to calculate.
        :return: The result of the equation.
        """
        try:
            # Parse the equation using sympy
            expr = sp.sympify(equation)
            result = expr.evalf()
            return f"{equation} = {result}"
        except (sp.SympifyError, ValueError) as e:
            print(e)
            return "Invalid equation"
