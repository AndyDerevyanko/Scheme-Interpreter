"""Core value representation.

Mapping between Scheme and Python values:

    Scheme            Python
    ------            ------
    symbol            Symbol (interned str subclass)
    pair / list       Pair chain terminated by `nil`
    empty list        nil (singleton)
    boolean           bool  (#f is the ONLY false value)
    integer           int
    rational          fractions.Fraction (auto-normalized to int)
    real              float
    complex           complex
    string            str
    character         Char
    vector            Python list
    bytevector        bytearray
    procedure         Procedure (Scheme) or any Python callable (native)
    unspecified       None
"""

from fractions import Fraction

from .errors import SchemeTypeError


# ---------------------------------------------------------------- symbols

class Symbol(str):
    __slots__ = ()

    def __repr__(self):
        return str(self)


_symbol_table = {}


def intern(name):
    """Return the canonical Symbol for `name` (eq? works via identity)."""
    sym = _symbol_table.get(name)
    if sym is None:
        sym = Symbol(name)
        _symbol_table[name] = sym
    return sym


_gensym_counter = [0]


def gensym(prefix="g"):
    """A fresh, uninterned symbol - never eq? to anything else."""
    _gensym_counter[0] += 1
    return Symbol(f"{prefix}~{_gensym_counter[0]}")


# ---------------------------------------------------------------- nil

class Nil:
    _instance = None
    __slots__ = ()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "()"

    def __iter__(self):
        return iter(())

    def __bool__(self):
        # '() is truthy in Scheme; only #f is false.
        return True


nil = Nil()


# ---------------------------------------------------------------- pairs

class Pair:
    __slots__ = ("car", "cdr")

    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr

    def __iter__(self):
        """Iterate over the cars of the proper-list portion."""
        cur = self
        while isinstance(cur, Pair):
            yield cur.car
            cur = cur.cdr

    def __repr__(self):
        return scm_repr(self)


def slist(items, tail=nil):
    """Build a Scheme list from a Python iterable."""
    result = tail
    for item in reversed(list(items)):
        result = Pair(item, result)
    return result


def pylist(x, what="list"):
    """Convert a proper Scheme list to a Python list, else raise."""
    out = []
    cur = x
    fast = x
    while isinstance(cur, Pair):
        out.append(cur.car)
        cur = cur.cdr
        # Floyd cycle detection so circular data raises instead of hanging.
        if isinstance(fast, Pair):
            fast = fast.cdr
            if isinstance(fast, Pair):
                fast = fast.cdr
                if fast is cur:
                    raise SchemeTypeError(f"circular {what} passed where a "
                                          "proper list is required")
    if cur is not nil:
        raise SchemeTypeError(f"expected a proper {what}, got {scm_repr(x)}")
    return out


def is_scheme_list(x):
    # Floyd cycle detection: a circular list is not a proper list,
    # and must not hang us.
    slow = fast = x
    while isinstance(fast, Pair):
        fast = fast.cdr
        if not isinstance(fast, Pair):
            break
        fast = fast.cdr
        slow = slow.cdr
        if slow is fast:
            return False
    return fast is nil


def to_python(x):
    """Deep-convert a Scheme value to plain Python (lists, str, numbers).

    Useful for host integration and for comparing against Python-native
    expected values in test harnesses.
    """
    if x is nil:
        return []
    if isinstance(x, Pair):
        out = []
        cur = x
        while isinstance(cur, Pair):
            out.append(to_python(cur.car))
            cur = cur.cdr
        if cur is not nil:  # improper list -> tuple with tail marker
            return tuple(out + [to_python(cur)])
        return out
    if isinstance(x, list):
        return [to_python(v) for v in x]
    if isinstance(x, Char):
        return x.c
    return x


# ---------------------------------------------------------------- chars

class Char:
    __slots__ = ("c",)

    def __init__(self, c):
        self.c = c

    def __eq__(self, other):
        return isinstance(other, Char) and self.c == other.c

    def __lt__(self, other):
        return self.c < other.c

    def __hash__(self):
        return hash(("char", self.c))

    def __repr__(self):
        return scm_repr(self)


_CHAR_NAMES = {
    " ": "space", "\n": "newline", "\t": "tab", "\r": "return",
    "\x00": "null", "\x07": "alarm", "\x08": "backspace",
    "\x7f": "delete", "\x1b": "escape",
}
CHAR_BY_NAME = {v: k for k, v in _CHAR_NAMES.items()}


# ---------------------------------------------------------------- procedures

class Procedure:
    """A Scheme closure: parameter list, body forms, captured environment."""

    __slots__ = ("params", "rest", "body", "env", "name")

    def __init__(self, params, rest, body, env, name=None):
        self.params = params      # list of Symbol
        self.rest = rest          # Symbol or None (variadic tail)
        self.body = body          # non-empty Python list of body forms
        self.env = env
        self.name = name

    def __repr__(self):
        return f"#<procedure {self.name or 'lambda'}>"


class Macro:
    """A non-hygienic macro: a transformer procedure applied to raw forms."""

    __slots__ = ("proc",)

    def __init__(self, proc):
        self.proc = proc

    def __repr__(self):
        return "#<macro>"


class Continuation(Exception):
    """Escape continuation payload used by call/cc."""

    def __init__(self, tag, value):
        super().__init__("continuation invoked outside its extent")
        self.tag = tag
        self.value = value


# ---------------------------------------------------------------- printing

def normalize_number(x):
    """Collapse Fraction n/1 to int so exact arithmetic stays tidy."""
    if isinstance(x, Fraction) and x.denominator == 1:
        return int(x)
    return x


def scm_repr(x, display=False):
    """Render a value as Scheme source text (write) or for humans (display)."""
    if x is None:
        return "#<unspecified>"
    if x is True:
        return "#t"
    if x is False:
        return "#f"
    if x is nil:
        return "()"
    if isinstance(x, Symbol):
        return str(x)
    if isinstance(x, str):
        if display:
            return x
        escaped = x.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
        return f'"{escaped}"'
    if isinstance(x, Char):
        if display:
            return x.c
        name = _CHAR_NAMES.get(x.c)
        return f"#\\{name}" if name else f"#\\{x.c}"
    if isinstance(x, Fraction):
        return f"{x.numerator}/{x.denominator}"
    if isinstance(x, complex):
        real = "" if x.real == 0 else repr(x.real if x.real % 1 else int(x.real))
        imag = x.imag if x.imag % 1 else int(x.imag)
        sign = "+" if (imag >= 0 and real) else ""
        return f"{real}{sign}{imag}i"
    if isinstance(x, Pair):
        parts = []
        seen = set()
        cur = x
        while isinstance(cur, Pair):
            if id(cur) in seen:
                parts.append("...circular...")
                cur = nil
                break
            seen.add(id(cur))
            parts.append(scm_repr(cur.car, display))
            cur = cur.cdr
        if cur is not nil:
            parts.append(".")
            parts.append(scm_repr(cur, display))
        return "(" + " ".join(parts) + ")"
    if isinstance(x, list):
        return "#(" + " ".join(scm_repr(v, display) for v in x) + ")"
    if isinstance(x, bytearray):
        return "#u8(" + " ".join(str(b) for b in x) + ")"
    if isinstance(x, Procedure):
        return repr(x)
    if isinstance(x, Macro):
        return repr(x)
    if callable(x):
        name = getattr(x, "scheme_name", None) or getattr(x, "__name__", "native")
        return f"#<builtin {name}>"
    return repr(x)
