"""Lexical environments: a dict of bindings plus a parent pointer."""

from .errors import SchemeNameError

_MISSING = object()


class Env:
    __slots__ = ("vars", "outer")

    def __init__(self, outer=None, vars=None):
        self.vars = vars if vars is not None else {}
        self.outer = outer

    def lookup(self, symbol):
        env = self
        while env is not None:
            value = env.vars.get(symbol, _MISSING)
            if value is not _MISSING:
                return value
            env = env.outer
        raise SchemeNameError(f"undefined symbol '{symbol}'")

    def maybe_lookup(self, symbol):
        """Like lookup but returns None instead of raising."""
        env = self
        while env is not None:
            value = env.vars.get(symbol, _MISSING)
            if value is not _MISSING:
                return value
            env = env.outer
        return None

    def define(self, symbol, value):
        self.vars[symbol] = value

    def set(self, symbol, value):
        env = self
        while env is not None:
            if symbol in env.vars:
                env.vars[symbol] = value
                return
            env = env.outer
        raise SchemeNameError(f"set!: undefined symbol '{symbol}'")
