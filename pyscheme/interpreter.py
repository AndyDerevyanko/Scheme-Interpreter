"""Embeddable interpreter facade.

This is the API a host application (e.g. a LilyPond-style engraver) uses:

    interp = Interpreter()
    interp.define("make-note", lambda pitch, dur: ...)   # host binding
    result = interp.eval_string("(make-note \"c\" 1/4)")

Host-facing conversion helpers live in pyscheme.types (to_python, slist).
"""

import sys

from .builtins import make_global_env
from .evaluator import apply_procedure, seval
from .reader import parse
from .types import intern, scm_repr

# Non-tail recursion (deeply recursive Scheme code, deep data) needs more
# Python stack than the default.
if sys.getrecursionlimit() < 20000:
    sys.setrecursionlimit(20000)


class Interpreter:
    def __init__(self):
        self.env = make_global_env()

    # ------------------------------------------------------------ eval

    def eval(self, form):
        """Evaluate one already-parsed form at the top level."""
        return seval(form, self.env, toplevel=True)

    def eval_string(self, source, filename="<string>"):
        """Evaluate all forms in `source`; return the last value."""
        result = None
        for form in parse(source, filename):
            result = self.eval(form)
        return result

    def eval_file(self, path):
        with open(path, "r", encoding="utf-8-sig") as fh:
            return self.eval_string(fh.read(), filename=str(path))

    # ------------------------------------------------------------ host API

    def define(self, name, value):
        """Bind a host value or Python callable as a global."""
        self.env.define(intern(name), value)

    def lookup(self, name):
        return self.env.lookup(intern(name))

    def call(self, name, *args):
        """Call a Scheme procedure from the host side."""
        return apply_procedure(self.lookup(name), list(args))

    def native(self, name):
        """Decorator: @interp.native("note") def note(...): ..."""
        def wrap(fn):
            self.define(name, fn)
            return fn
        return wrap

    @staticmethod
    def repr(value, display=False):
        return scm_repr(value, display=display)
