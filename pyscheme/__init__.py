"""pyscheme: a small embeddable Scheme interpreter in pure Python.

Designed as the scripting core for a LilyPond-style music notation
program, but usable standalone (python -m pyscheme).
"""

from .errors import (SchemeError, SchemeNameError, SchemeSyntaxError,
                     SchemeTypeError)
from .interpreter import Interpreter
from .reader import parse, parse_one
from .types import (Char, Pair, Procedure, Symbol, intern, nil, pylist,
                    scm_repr, slist, to_python)

__all__ = [
    "Interpreter", "parse", "parse_one",
    "SchemeError", "SchemeSyntaxError", "SchemeTypeError", "SchemeNameError",
    "Symbol", "Pair", "Char", "Procedure", "nil",
    "intern", "slist", "pylist", "to_python", "scm_repr",
]

__version__ = "0.1.0"
