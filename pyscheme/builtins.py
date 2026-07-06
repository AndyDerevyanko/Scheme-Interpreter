"""Native (Python-implemented) procedures and the global environment."""

import cmath
import math
import sys
import time
from fractions import Fraction
from functools import reduce

from .environment import Env
from .errors import SchemeError, SchemeTypeError
from .evaluator import apply_procedure, is_true
from .types import (Char, Continuation, Pair, Procedure, Symbol, gensym,
                    intern, is_scheme_list, nil, normalize_number, pylist,
                    scm_repr, slist)


def _check_number(x, who):
    if isinstance(x, bool) or not isinstance(x, (int, float, complex, Fraction)):
        raise SchemeTypeError(f"{who}: expected a number, got {scm_repr(x)}")
    return x


def _check_pair(x, who):
    if not isinstance(x, Pair):
        raise SchemeTypeError(f"{who}: expected a pair, got {scm_repr(x)}")
    return x


# ------------------------------------------------------------- arithmetic

def _add(*args):
    result = 0
    for a in args:
        result = result + _check_number(a, "+")
    return normalize_number(result)


def _mul(*args):
    result = 1
    for a in args:
        result = result * _check_number(a, "*")
    return normalize_number(result)


def _sub(first, *rest):
    _check_number(first, "-")
    if not rest:
        return normalize_number(-first)
    result = first
    for a in rest:
        result = result - _check_number(a, "-")
    return normalize_number(result)


def _div(first, *rest):
    _check_number(first, "/")
    values = (first,) + rest if rest else (1, first)
    result = values[0]
    for a in values[1:]:
        _check_number(a, "/")
        if isinstance(result, (int, Fraction)) and isinstance(a, (int, Fraction)):
            if a == 0:
                raise SchemeError("division by zero")
            result = Fraction(result) / Fraction(a)
        else:
            result = result / a
    return normalize_number(result)


def _chain(op, name):
    def compare(first, *rest):
        _check_number(first, name)
        prev = first
        for a in rest:
            _check_number(a, name)
            if not op(prev, a):
                return False
            prev = a
        return True
    compare.scheme_name = name
    return compare


def _sqrt(x):
    _check_number(x, "sqrt")
    if isinstance(x, complex) or x < 0:
        return cmath.sqrt(x)
    if isinstance(x, int):
        root = math.isqrt(x)
        if root * root == x:
            return root
    return math.sqrt(x)


def _expt(base, power):
    result = base ** power
    return normalize_number(result)


def _number_to_string(x, radix=10):
    if radix == 10:
        return scm_repr(x)
    if radix == 16:
        return format(x, "x")
    if radix == 8:
        return format(x, "o")
    if radix == 2:
        return format(x, "b")
    raise SchemeError(f"number->string: unsupported radix {radix}")


def _string_to_number(s, radix=10):
    from .reader import parse_number
    if radix != 10:
        try:
            return int(s, radix)
        except ValueError:
            return False
    value = parse_number(s)
    return value if value is not None else False


# ------------------------------------------------------------- equality

def eqv(a, b):
    if a is b:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float, complex, Fraction)) \
            and isinstance(b, (int, float, complex, Fraction)):
        exact_a = isinstance(a, (int, Fraction))
        exact_b = isinstance(b, (int, Fraction))
        return exact_a == exact_b and a == b
    if isinstance(a, Char) and isinstance(b, Char):
        return a.c == b.c
    return False


def scheme_equal(a, b, _seen=None):
    if isinstance(a, Pair) and isinstance(b, Pair):
        # Track visited pair-id pairs so equal? terminates on cycles
        # (R7RS requires equal? to handle circular structure).
        if _seen is None:
            _seen = set()
        while isinstance(a, Pair) and isinstance(b, Pair):
            key = (id(a), id(b))
            if key in _seen:
                return True
            _seen.add(key)
            if not scheme_equal(a.car, b.car, _seen):
                return False
            a, b = a.cdr, b.cdr
        return scheme_equal(a, b, _seen)
    if isinstance(a, Symbol) or isinstance(b, Symbol):
        return a is b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(scheme_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, bytearray) and isinstance(b, bytearray):
        return a == b
    return eqv(a, b)


# ------------------------------------------------------------- lists

def _car(x):
    return _check_pair(x, "car").car


def _cdr(x):
    return _check_pair(x, "cdr").cdr


def _length(x):
    if not is_scheme_list(x):
        raise SchemeTypeError(f"length: not a proper list: {scm_repr(x)}")
    count = 0
    cur = x
    while isinstance(cur, Pair):
        count += 1
        cur = cur.cdr
    return count


def _append(*lists):
    if not lists:
        return nil
    result = lists[-1]
    for lst in reversed(lists[:-1]):
        result = slist(pylist(lst, "append argument"), result)
    return result


def _list_tail(lst, k):
    cur = lst
    for _ in range(k):
        cur = _check_pair(cur, "list-tail").cdr
    return cur


def _assoc_maker(pred, name):
    def assoc(key, alist):
        cur = alist
        while isinstance(cur, Pair):
            entry = cur.car
            if isinstance(entry, Pair) and pred(entry.car, key):
                return entry
            cur = cur.cdr
        return False
    assoc.scheme_name = name
    return assoc


def _member_maker(pred, name):
    def member(item, lst):
        cur = lst
        while isinstance(cur, Pair):
            if pred(cur.car, item):
                return cur
            cur = cur.cdr
        return False
    member.scheme_name = name
    return member


def _map(proc, *lists):
    columns = [pylist(lst, "map argument") for lst in lists]
    return slist([apply_procedure(proc, list(row)) for row in zip(*columns)])


def _for_each(proc, *lists):
    columns = [pylist(lst, "for-each argument") for lst in lists]
    for row in zip(*columns):
        apply_procedure(proc, list(row))
    return None


def _apply(proc, *args):
    if not args:
        raise SchemeTypeError("apply: expected at least 2 arguments")
    final = pylist(args[-1], "apply's last argument")
    return apply_procedure(proc, list(args[:-1]) + final)


# ------------------------------------------------------------- call/cc

def _call_cc(proc):
    tag = object()

    def escape(*values):
        raise Continuation(tag, values[0] if values else None)
    escape.scheme_name = "continuation"

    try:
        return apply_procedure(proc, [escape])
    except Continuation as c:
        if c.tag is tag:
            return c.value
        raise


# ------------------------------------------------------------- output

def _display(x, *rest):
    sys.stdout.write(scm_repr(x, display=True))
    return None


def _write(x, *rest):
    sys.stdout.write(scm_repr(x))
    return None


def _newline(*rest):
    sys.stdout.write("\n")
    return None


def _error(message, *irritants):
    text = scm_repr(message, display=True)
    if irritants:
        text += " " + " ".join(scm_repr(i) for i in irritants)
    raise SchemeError(text)


# ------------------------------------------------------------- predicates

def _is_number(x):
    return not isinstance(x, bool) and isinstance(x, (int, float, complex, Fraction))


def _is_integer(x):
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float):
        return x == int(x) if math.isfinite(x) else False
    if isinstance(x, Fraction):
        return x.denominator == 1
    return False


def _exact(x):
    _check_number(x, "exact")
    if isinstance(x, (int, Fraction)):
        return x
    return normalize_number(Fraction(x).limit_denominator(10 ** 12))


def _inexact(x):
    _check_number(x, "inexact")
    return float(x) if not isinstance(x, complex) else x


# ------------------------------------------------------------- environment

def make_global_env():
    """Build a fresh global environment with all primitives bound."""
    env = Env()
    d = env.vars

    def define(name, value):
        sym = intern(name)
        if callable(value) and not hasattr(value, "scheme_name"):
            try:
                value.scheme_name = name
            except (AttributeError, TypeError):
                pass
        d[sym] = value

    import operator as op

    # numbers
    define("+", _add)
    define("-", _sub)
    define("*", _mul)
    define("/", _div)
    define("=", _chain(op.eq, "="))
    define("<", _chain(op.lt, "<"))
    define(">", _chain(op.gt, ">"))
    define("<=", _chain(op.le, "<="))
    define(">=", _chain(op.ge, ">="))
    define("abs", lambda x: normalize_number(abs(_check_number(x, "abs"))))
    define("min", lambda *xs: min(xs))
    define("max", lambda *xs: max(xs))
    define("quotient", lambda a, b: int(math.trunc(a / b)) if b else _error("quotient: division by zero"))
    define("remainder", lambda a, b: a - b * int(math.trunc(a / b)))
    define("modulo", op.mod)
    define("gcd", lambda *xs: reduce(math.gcd, [abs(int(x)) for x in xs], 0))
    define("lcm", lambda *xs: reduce(math.lcm, [abs(int(x)) for x in xs], 1))
    define("expt", _expt)
    define("sqrt", _sqrt)
    define("exact-integer-sqrt", lambda n: math.isqrt(n))
    define("floor", lambda x: normalize_number(math.floor(x)) if not isinstance(x, float) else float(math.floor(x)))
    define("ceiling", lambda x: normalize_number(math.ceil(x)) if not isinstance(x, float) else float(math.ceil(x)))
    define("truncate", lambda x: normalize_number(math.trunc(x)) if not isinstance(x, float) else float(math.trunc(x)))
    define("round", lambda x: normalize_number(round(x)) if not isinstance(x, float) else float(round(x)))
    define("number->string", _number_to_string)
    define("string->number", _string_to_number)
    define("zero?", lambda x: _check_number(x, "zero?") == 0)
    define("positive?", lambda x: x > 0)
    define("negative?", lambda x: x < 0)
    define("even?", lambda x: int(x) % 2 == 0)
    define("odd?", lambda x: int(x) % 2 == 1)
    define("exact", _exact)
    define("inexact", _inexact)
    define("exact->inexact", _inexact)
    define("inexact->exact", _exact)
    define("exact?", lambda x: isinstance(x, (int, Fraction)) and not isinstance(x, bool))
    define("inexact?", lambda x: isinstance(x, (float, complex)))
    define("nan?", lambda x: isinstance(x, float) and math.isnan(x))
    define("numerator", lambda x: x.numerator if isinstance(x, (int, Fraction)) else x)
    define("denominator", lambda x: x.denominator if isinstance(x, (int, Fraction)) else 1)
    define("square", lambda x: normalize_number(x * x))
    for name in ("sin", "cos", "tan", "asin", "acos", "exp"):
        define(name, getattr(math, name))
    define("atan", lambda y, *x: math.atan2(y, x[0]) if x else math.atan(y))
    define("log", lambda x, *base: math.log(x, *base))

    # booleans / predicates
    define("not", lambda x: x is False)
    define("boolean?", lambda x: isinstance(x, bool))
    define("boolean=?", lambda a, b: a is b)
    define("number?", _is_number)
    define("complex?", _is_number)
    define("real?", lambda x: _is_number(x) and not isinstance(x, complex))
    define("rational?", lambda x: isinstance(x, (int, Fraction)) and not isinstance(x, bool)
           or (isinstance(x, float) and math.isfinite(x)))
    define("integer?", _is_integer)
    define("exact-integer?", lambda x: isinstance(x, int) and not isinstance(x, bool))
    define("symbol?", lambda x: isinstance(x, Symbol))
    define("string?", lambda x: isinstance(x, str) and not isinstance(x, Symbol))
    define("char?", lambda x: isinstance(x, Char))
    define("pair?", lambda x: isinstance(x, Pair))
    define("null?", lambda x: x is nil)
    define("list?", is_scheme_list)
    define("vector?", lambda x: isinstance(x, list))
    define("bytevector?", lambda x: isinstance(x, bytearray))
    define("procedure?", lambda x: isinstance(x, Procedure)
           or (callable(x) and not isinstance(x, (Symbol, type))))

    # equality
    define("eq?", lambda a, b: a is b or eqv(a, b) and isinstance(a, (int, Char)))
    define("eqv?", eqv)
    define("equal?", scheme_equal)

    # pairs & lists
    define("cons", Pair)
    define("car", _car)
    define("cdr", _cdr)
    define("caar", lambda x: _car(_car(x)))
    define("cadr", lambda x: _car(_cdr(x)))
    define("cdar", lambda x: _cdr(_car(x)))
    define("cddr", lambda x: _cdr(_cdr(x)))
    define("caddr", lambda x: _car(_cdr(_cdr(x))))
    define("cdddr", lambda x: _cdr(_cdr(_cdr(x))))
    define("set-car!", lambda p, v: setattr(_check_pair(p, "set-car!"), "car", v))
    define("set-cdr!", lambda p, v: setattr(_check_pair(p, "set-cdr!"), "cdr", v))
    define("list", lambda *xs: slist(xs))
    define("length", _length)
    define("append", _append)
    define("reverse", lambda lst: slist(reversed(pylist(lst, "reverse argument"))))
    define("list-tail", _list_tail)
    define("list-ref", lambda lst, k: _car(_list_tail(lst, k)))
    define("list-copy", lambda lst: slist(pylist(lst, "list-copy argument")))
    define("assq", _assoc_maker(lambda a, b: a is b or eqv(a, b), "assq"))
    define("assv", _assoc_maker(eqv, "assv"))
    define("assoc", _assoc_maker(scheme_equal, "assoc"))
    define("memq", _member_maker(lambda a, b: a is b or eqv(a, b), "memq"))
    define("memv", _member_maker(eqv, "memv"))
    define("member", _member_maker(scheme_equal, "member"))
    define("map", _map)
    define("for-each", _for_each)
    define("apply", _apply)
    define("filter", lambda pred, lst: slist(
        [v for v in pylist(lst, "filter argument")
         if is_true(apply_procedure(pred, [v]))]))
    define("reduce", lambda fn, init, lst: reduce(
        lambda acc, v: apply_procedure(fn, [v, acc]),
        pylist(lst, "reduce argument"), init))

    # symbols & strings
    define("symbol->string", lambda s: str(s))
    define("string->symbol", lambda s: intern(s))
    define("string-length", len)
    define("string-append", lambda *ss: "".join(ss))
    define("substring", lambda s, start, end=None: s[start:end])
    define("string-ref", lambda s, k: Char(s[k]))
    define("string->list", lambda s: slist([Char(c) for c in s]))
    define("list->string", lambda lst: "".join(
        c.c for c in pylist(lst, "list->string argument")))
    define("string", lambda *cs: "".join(c.c for c in cs))
    define("string-upcase", lambda s: s.upper())
    define("string-downcase", lambda s: s.lower())
    define("string=?", lambda *ss: all(a == b for a, b in zip(ss, ss[1:])))
    define("string<?", lambda *ss: all(a < b for a, b in zip(ss, ss[1:])))
    define("string>?", lambda *ss: all(a > b for a, b in zip(ss, ss[1:])))
    define("string<=?", lambda *ss: all(a <= b for a, b in zip(ss, ss[1:])))
    define("string>=?", lambda *ss: all(a >= b for a, b in zip(ss, ss[1:])))
    define("string-copy", lambda s, start=0, end=None: s[start:end])
    define("string-contains", lambda s, sub: s.find(sub) if sub in s else False)
    define("string-split", lambda s, sep=" ": slist(s.split(sep)))
    define("string-join", lambda lst, sep="": sep.join(pylist(lst, "string-join")))

    # characters
    define("char->integer", lambda c: ord(c.c))
    define("integer->char", lambda n: Char(chr(n)))
    define("char=?", lambda *cs: all(a.c == b.c for a, b in zip(cs, cs[1:])))
    define("char<?", lambda *cs: all(a.c < b.c for a, b in zip(cs, cs[1:])))
    define("char>?", lambda *cs: all(a.c > b.c for a, b in zip(cs, cs[1:])))
    define("char-alphabetic?", lambda c: c.c.isalpha())
    define("char-numeric?", lambda c: c.c.isdigit())
    define("char-whitespace?", lambda c: c.c.isspace())
    define("char-upcase", lambda c: Char(c.c.upper()))
    define("char-downcase", lambda c: Char(c.c.lower()))

    # vectors
    define("vector", lambda *xs: list(xs))
    define("make-vector", lambda n, fill=0: [fill] * n)
    define("vector-length", len)
    define("vector-ref", lambda v, k: v[k])
    define("vector-set!", lambda v, k, val: v.__setitem__(k, val))
    define("vector->list", lambda v: slist(v))
    define("list->vector", lambda lst: pylist(lst, "list->vector argument"))
    define("vector-fill!", lambda v, val: v.__setitem__(slice(None), [val] * len(v)))
    define("vector-copy", lambda v, start=0, end=None: v[start:end])
    define("vector-map", lambda proc, *vs: [
        apply_procedure(proc, list(row)) for row in zip(*vs)])
    define("vector-for-each", lambda proc, *vs: [
        apply_procedure(proc, list(row)) for row in zip(*vs)] and None)

    # control
    define("call/cc", _call_cc)
    define("call-with-current-continuation", _call_cc)

    # I/O and misc
    define("display", _display)
    define("write", _write)
    define("newline", _newline)
    define("error", _error)
    define("gensym", gensym)
    define("current-second", time.time)
    define("runtime", time.perf_counter)
    define("void", lambda *a: None)

    return env
