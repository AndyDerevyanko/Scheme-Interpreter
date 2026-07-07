"""Error hierarchy for the interpreter.

Errors deliberately subclass the corresponding Python builtins
(SyntaxError, TypeError, NameError) so host code and test harnesses can
catch either the Scheme-specific or the generic Python flavor.
"""


class SchemeError(Exception):
    """Base class for all interpreter errors."""


class SchemeSyntaxError(SchemeError, SyntaxError):
    """Malformed source text or special form."""

    def __init__(self, message, line=None, col=None):
        if line is not None:
            message = f"{message} (line {line}, column {col})"
        super().__init__(message)
        self.line = line
        self.col = col


class SchemeTypeError(SchemeError, TypeError):
    """Wrong type or wrong number of arguments."""


class SchemeNameError(SchemeError, NameError):
    """Reference to an unbound symbol."""
