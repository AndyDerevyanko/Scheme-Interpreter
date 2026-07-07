"""The evaluator: a trampolined eval loop with proper tail calls.

Special forms are dispatched on interned symbols. Everything else is a
procedure application. Tail positions (if branches, begin/let/cond/and/or
tails, procedure bodies) update `x`/`env` and continue the loop instead of
recursing, so tail-recursive Scheme runs in constant Python stack space.
"""

from .environment import Env
from .errors import (SchemeError, SchemeNameError, SchemeSyntaxError,
                     SchemeTypeError)
from .types import (Macro, Pair, Procedure, Promise, Symbol, intern, nil,
                    pylist, scm_repr, slist)

# Interned symbols for fast identity dispatch.
S_QUOTE = intern("quote")
S_IF = intern("if")
S_DEFINE = intern("define")
S_SET = intern("set!")
S_LAMBDA = intern("lambda")
S_BEGIN = intern("begin")
S_LET = intern("let")
S_LETSTAR = intern("let*")
S_LETREC = intern("letrec")
S_COND = intern("cond")
S_CASE = intern("case")
S_ELSE = intern("else")
S_ARROW = intern("=>")
S_AND = intern("and")
S_OR = intern("or")
S_QUASIQUOTE = intern("quasiquote")
S_UNQUOTE = intern("unquote")
S_UNQUOTE_SPLICING = intern("unquote-splicing")
S_DEFINE_MACRO = intern("define-macro")
S_DELAY = intern("delay")
S_DEFINE_SYNTAX = intern("define-syntax")
S_SYNTAX_RULES = intern("syntax-rules")
S_ELLIPSIS = intern("...")
S_UNDERSCORE = intern("_")

_SPECIAL_FORMS = {
    S_QUOTE, S_IF, S_DEFINE, S_SET, S_LAMBDA, S_BEGIN, S_LET, S_LETSTAR,
    S_LETREC, S_COND, S_CASE, S_AND, S_OR, S_QUASIQUOTE, S_UNQUOTE,
    S_UNQUOTE_SPLICING, S_DEFINE_MACRO, S_DELAY, S_DEFINE_SYNTAX,
}


def is_true(x):
    """Scheme truthiness: everything except #f is true (including 0, '())."""
    return x is not False


class FuelExhausted(SchemeError):
    """Raised when an eval step budget (set via set_fuel) runs out."""


# Optional step budget: None = unlimited (normal operation). Test runners
# set a budget so a form that loops forever fails instead of hanging.
_fuel = [None]


def set_fuel(steps):
    """Set remaining eval steps (None disables). Returns previous value."""
    previous = _fuel[0]
    _fuel[0] = steps
    return previous


def _form_args(form, name, low, high=None):
    """Validate arity of a special form; return its argument forms."""
    args = pylist(form.cdr, f"{name} form")
    count = len(args)
    if count < low or (high is not None and count > high):
        raise SchemeSyntaxError(f"malformed {name}: {scm_repr(form)}")
    return args


def _parse_params(params, context):
    """Return (fixed_names, rest_name_or_None) from a lambda parameter spec."""
    if isinstance(params, Symbol):
        return [], params
    if params is nil:
        return [], None
    if not isinstance(params, Pair):
        raise SchemeSyntaxError(f"bad parameter list in {context}: {scm_repr(params)}")
    names = []
    cur = params
    while isinstance(cur, Pair):
        if not isinstance(cur.car, Symbol):
            raise SchemeSyntaxError(
                f"parameter is not a symbol in {context}: {scm_repr(cur.car)}")
        names.append(cur.car)
        cur = cur.cdr
    if cur is nil:
        return names, None
    if isinstance(cur, Symbol):
        return names, cur
    raise SchemeSyntaxError(f"bad parameter list in {context}: {scm_repr(params)}")


def _make_procedure(params_form, body_forms, env, name=None):
    if not body_forms:
        raise SchemeSyntaxError(f"empty body in lambda/define {name or ''}".strip())
    params, rest = _parse_params(params_form, name or "lambda")
    return Procedure(params, rest, body_forms, env, name)


def bind_params(proc, args):
    """Bind arguments into a fresh child of the closure environment."""
    params, rest = proc.params, proc.rest
    fixed = len(params)
    given = len(args)
    name = proc.name or "#<lambda>"
    if rest is None:
        if given != fixed:
            raise SchemeTypeError(
                f"{name}: expected {fixed} argument(s), got {given}")
    elif given < fixed:
        raise SchemeTypeError(
            f"{name}: expected at least {fixed} argument(s), got {given}")
    frame = dict(zip(params, args))
    if rest is not None:
        frame[rest] = slist(args[fixed:])
    return Env(outer=proc.env, vars=frame)


def apply_procedure(proc, args):
    """Apply a procedure to already-evaluated arguments (non-tail helper)."""
    if isinstance(proc, Procedure):
        env = bind_params(proc, args)
        result = None
        for form in proc.body:
            result = seval(form, env)
        return result
    if callable(proc):
        return proc(*args)
    raise SchemeTypeError(f"not a procedure: {scm_repr(proc)}")


def _eval_bindings_spec(bindings_form, name):
    """Validate ((sym expr) ...) binding lists for let and friends."""
    specs = []
    for binding in pylist(bindings_form, f"{name} bindings"):
        parts = pylist(binding, f"{name} binding")
        if len(parts) != 2 or not isinstance(parts[0], Symbol):
            raise SchemeSyntaxError(f"malformed {name} binding: {scm_repr(binding)}")
        specs.append((parts[0], parts[1]))
    return specs


def _quasi(template, env, depth):
    """Evaluate a quasiquote template."""
    if isinstance(template, Pair):
        head = template.car
        if head is S_UNQUOTE:
            arg = _form_args(template, "unquote", 1, 1)[0]
            if depth == 1:
                return seval(arg, env)
            return slist([S_UNQUOTE, _quasi(arg, env, depth - 1)])
        if head is S_UNQUOTE_SPLICING:
            raise SchemeSyntaxError("unquote-splicing (,@) outside of a list template")
        if head is S_QUASIQUOTE:
            arg = _form_args(template, "quasiquote", 1, 1)[0]
            return slist([S_QUASIQUOTE, _quasi(arg, env, depth + 1)])
        items = []
        tail = nil
        cur = template
        while isinstance(cur, Pair):
            if cur is not template and cur.car in (S_UNQUOTE, S_UNQUOTE_SPLICING):
                tail = _quasi(cur, env, depth)  # dotted (a . ,b)
                cur = nil
                break
            el = cur.car
            if isinstance(el, Pair) and el.car is S_UNQUOTE_SPLICING:
                arg = _form_args(el, "unquote-splicing", 1, 1)[0]
                if depth == 1:
                    spliced = seval(arg, env)
                    items.extend(pylist(spliced, "unquote-splicing result"))
                else:
                    items.append(slist(
                        [S_UNQUOTE_SPLICING, _quasi(arg, env, depth - 1)]))
            else:
                items.append(_quasi(el, env, depth))
            cur = cur.cdr
        if cur is not nil:
            tail = _quasi(cur, env, depth)
        return slist(items, tail)
    if isinstance(template, list):  # vector template
        return [_quasi(el, env, depth) for el in template]
    return template


def _sr_flatten(x):
    """Split a (possibly improper) list into (python_list_of_elements, tail)."""
    items = []
    cur = x
    while isinstance(cur, Pair):
        items.append(cur.car)
        cur = cur.cdr
    return items, cur


def _sr_equal(a, b):
    """Datum equality for matching self-evaluating literals in patterns."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, Symbol) or isinstance(b, Symbol):
        return a is b
    return a == b


def _sr_pattern_vars(pattern, literals, ellipsis, out):
    """Collect the set of pattern variables a (sub-)pattern binds."""
    if isinstance(pattern, Symbol):
        if pattern is not S_UNDERSCORE and pattern is not ellipsis and pattern not in literals:
            out.add(pattern)
        return
    if isinstance(pattern, Pair):
        items, tail = _sr_flatten(pattern)
        for item in items:
            _sr_pattern_vars(item, literals, ellipsis, out)
        _sr_pattern_vars(tail, literals, ellipsis, out)


def _sr_match(pattern, form, literals, ellipsis, bindings):
    """Match `pattern` against `form`, extending `bindings` in place.

    Pattern variables bound under an ellipsis are stored as
    ("...", [value, ...]) so `_sr_expand` knows to iterate them.
    """
    if isinstance(pattern, Symbol):
        if pattern is S_UNDERSCORE:
            return True
        if pattern in literals:
            return isinstance(form, Symbol) and form is pattern
        bindings[pattern] = form
        return True
    if isinstance(pattern, Pair):
        return _sr_match_list(pattern, form, literals, ellipsis, bindings)
    if pattern is nil:
        return form is nil
    return _sr_equal(pattern, form)


def _sr_match_list(pattern, form, literals, ellipsis, bindings):
    p_items, p_tail = _sr_flatten(pattern)
    f_items, f_tail = _sr_flatten(form)

    ellipsis_idx = None
    for i, p in enumerate(p_items):
        if p is ellipsis:
            ellipsis_idx = i
            break

    if ellipsis_idx is None:
        if len(p_items) != len(f_items):
            return False
        for p, f in zip(p_items, f_items):
            if not _sr_match(p, f, literals, ellipsis, bindings):
                return False
        return _sr_match(p_tail, f_tail, literals, ellipsis, bindings)

    head = p_items[:ellipsis_idx - 1]
    repeated = p_items[ellipsis_idx - 1]
    tail_patterns = p_items[ellipsis_idx + 1:]

    if len(f_items) < len(head) + len(tail_patterns):
        return False
    n_repeat = len(f_items) - len(head) - len(tail_patterns)

    for p, f in zip(head, f_items[:len(head)]):
        if not _sr_match(p, f, literals, ellipsis, bindings):
            return False

    repeated_forms = f_items[len(head):len(head) + n_repeat]
    var_names = set()
    _sr_pattern_vars(repeated, literals, ellipsis, var_names)
    collected = {name: [] for name in var_names}
    for f in repeated_forms:
        sub_bindings = {}
        if not _sr_match(repeated, f, literals, ellipsis, sub_bindings):
            return False
        for name in var_names:
            collected[name].append(sub_bindings.get(name))
    for name, values in collected.items():
        bindings[name] = ("...", values)

    for p, f in zip(tail_patterns, f_items[len(head) + n_repeat:]):
        if not _sr_match(p, f, literals, ellipsis, bindings):
            return False

    return _sr_match(p_tail, f_tail, literals, ellipsis, bindings)


def _sr_expand(template, bindings, ellipsis):
    """Instantiate a syntax-rules template against matched `bindings`."""
    if isinstance(template, Symbol):
        if template in bindings:
            value = bindings[template]
            if isinstance(value, tuple) and len(value) == 2 and value[0] == "...":
                raise SchemeSyntaxError(
                    f"pattern variable '{template}' used without ellipsis")
            return value
        return template
    if isinstance(template, Pair):
        items, tail = _sr_flatten(template)
        result = []
        i, n = 0, len(items)
        while i < n:
            item = items[i]
            if i + 1 < n and items[i + 1] is ellipsis:
                var_names = set()
                _sr_pattern_vars(item, set(), ellipsis, var_names)
                length = 0
                for name in var_names:
                    value = bindings.get(name)
                    if isinstance(value, tuple) and len(value) == 2 and value[0] == "...":
                        length = len(value[1])
                        break
                for k in range(length):
                    sub_bindings = dict(bindings)
                    for name in var_names:
                        value = bindings.get(name)
                        if isinstance(value, tuple) and len(value) == 2 and value[0] == "...":
                            sub_bindings[name] = value[1][k]
                    result.append(_sr_expand(item, sub_bindings, ellipsis))
                i += 2
            else:
                result.append(_sr_expand(item, bindings, ellipsis))
                i += 1
        return slist(result, _sr_expand(tail, bindings, ellipsis))
    return template  # self-evaluating literal (number, string, char, ...)


def _parse_syntax_rules(spec):
    """Parse a (syntax-rules [ellipsis] (literals...) (pattern template)...) form."""
    parts = pylist(spec, "syntax-rules form")
    if not parts or parts[0] is not S_SYNTAX_RULES:
        raise SchemeSyntaxError(f"define-syntax: expected syntax-rules, got {scm_repr(spec)}")
    rest = parts[1:]
    if not rest:
        raise SchemeSyntaxError("malformed syntax-rules")
    ellipsis = S_ELLIPSIS
    if isinstance(rest[0], Symbol):
        ellipsis = rest[0]
        rest = rest[1:]
    if not rest:
        raise SchemeSyntaxError("malformed syntax-rules")
    literals = set(pylist(rest[0], "syntax-rules literals"))
    rules = []
    for rule in rest[1:]:
        rule_parts = pylist(rule, "syntax-rules rule")
        if len(rule_parts) != 2:
            raise SchemeSyntaxError(f"malformed syntax-rules rule: {scm_repr(rule)}")
        rules.append((rule_parts[0], rule_parts[1]))
    return literals, rules, ellipsis


def _do_define(form, env):
    args = pylist(form.cdr, "define form")
    if not args:
        raise SchemeSyntaxError(f"malformed define: {scm_repr(form)}")
    target = args[0]
    if isinstance(target, Symbol):
        if len(args) != 2:
            raise SchemeSyntaxError(f"malformed define: {scm_repr(form)}")
        env.define(target, seval(args[1], env))
        return None
    if isinstance(target, Pair):
        # (define (name . params) body...) with curried nesting support:
        # (define ((f a) b) ...) == (define (f a) (lambda (b) ...))
        body = args[1:]
        if not body:
            raise SchemeSyntaxError(f"malformed define: {scm_repr(form)}")
        while isinstance(target, Pair):
            head, params = target.car, target.cdr
            if isinstance(head, Symbol):
                name = str(head)
                env.define(head, _make_procedure(params, body, env, name))
                return None
            body = [Pair(S_LAMBDA, Pair(params, slist(body)))]
            target = head
        raise SchemeSyntaxError(f"malformed define: {scm_repr(form)}")
    raise SchemeSyntaxError(
        f"define: cannot define {scm_repr(target)} (not a symbol)")


def seval(x, env, toplevel=False):
    """Evaluate `x` in `env`. `toplevel` gates define-macro."""
    while True:
        fuel = _fuel[0]
        if fuel is not None:
            if fuel <= 0:
                raise FuelExhausted("evaluation step budget exhausted")
            _fuel[0] = fuel - 1
        if isinstance(x, Symbol):
            return env.lookup(x)
        if not isinstance(x, Pair):
            if x is nil:
                raise SchemeSyntaxError("cannot evaluate the empty combination ()")
            return x  # numbers, strings, chars, booleans, vectors, ...

        op = x.car
        if isinstance(op, Symbol) and op in _SPECIAL_FORMS:
            if op is S_QUOTE:
                return _form_args(x, "quote", 1, 1)[0]

            if op is S_IF:
                args = _form_args(x, "if", 2, 3)
                if is_true(seval(args[0], env)):
                    x = args[1]
                elif len(args) == 3:
                    x = args[2]
                else:
                    return None
                toplevel = False
                continue

            if op is S_DEFINE:
                return _do_define(x, env)

            if op is S_SET:
                args = _form_args(x, "set!", 2, 2)
                if not isinstance(args[0], Symbol):
                    raise SchemeSyntaxError(f"malformed set!: {scm_repr(x)}")
                env.set(args[0], seval(args[1], env))
                return None

            if op is S_LAMBDA:
                args = pylist(x.cdr, "lambda form")
                if len(args) < 2:
                    raise SchemeSyntaxError(f"malformed lambda: {scm_repr(x)}")
                return _make_procedure(args[0], args[1:], env)

            if op is S_BEGIN:
                body = pylist(x.cdr, "begin form")
                if not body:
                    return None
                for form in body[:-1]:
                    seval(form, env, toplevel)
                x = body[-1]
                continue  # toplevel is preserved through begin

            if op is S_LET or op is S_LETSTAR or op is S_LETREC:
                args = pylist(x.cdr, "let form")
                name = None
                if op is S_LET and args and isinstance(args[0], Symbol):
                    name = args[0]  # named let
                    args = args[1:]
                if len(args) < 2:
                    raise SchemeSyntaxError(f"malformed let: {scm_repr(x)}")
                specs = _eval_bindings_spec(args[0], str(op))
                body = args[1:]
                if name is not None:
                    loop_proc = Procedure([s for s, _ in specs], None, body,
                                          env, str(name))
                    loop_env = Env(outer=env, vars={name: loop_proc})
                    loop_proc.env = loop_env
                    init = [seval(expr, env) for _, expr in specs]
                    env = bind_params(loop_proc, init)
                elif op is S_LET:
                    frame = {sym: seval(expr, env) for sym, expr in specs}
                    env = Env(outer=env, vars=frame)
                elif op is S_LETSTAR:
                    for sym, expr in specs:
                        env = Env(outer=env, vars={sym: seval(expr, env)})
                else:  # letrec
                    env = Env(outer=env,
                              vars={sym: None for sym, _ in specs})
                    for sym, expr in specs:
                        env.vars[sym] = seval(expr, env)
                for form in body[:-1]:
                    seval(form, env)
                x = body[-1]
                toplevel = False
                continue

            if op is S_COND:
                clauses = pylist(x.cdr, "cond form")
                x = None
                for clause in clauses:
                    parts = pylist(clause, "cond clause")
                    if not parts:
                        raise SchemeSyntaxError(f"malformed cond clause: {scm_repr(clause)}")
                    if parts[0] is S_ELSE:
                        x = Pair(S_BEGIN, clause.cdr)
                        break
                    test = seval(parts[0], env)
                    if is_true(test):
                        if len(parts) == 1:
                            return test
                        if parts[1] is S_ARROW:
                            return apply_procedure(seval(parts[2], env), [test])
                        x = Pair(S_BEGIN, clause.cdr)
                        break
                if x is None:
                    return None
                toplevel = False
                continue

            if op is S_CASE:
                args = pylist(x.cdr, "case form")
                if len(args) < 2:
                    raise SchemeSyntaxError(f"malformed case: {scm_repr(x)}")
                key = seval(args[0], env)
                x = None
                for clause in args[1:]:
                    parts = pylist(clause, "case clause")
                    if parts[0] is S_ELSE or key in pylist(parts[0], "case datums"):
                        x = Pair(S_BEGIN, clause.cdr)
                        break
                if x is None:
                    return None
                toplevel = False
                continue

            if op is S_AND:
                forms = pylist(x.cdr, "and form")
                if not forms:
                    return True
                for form in forms[:-1]:
                    if not is_true(seval(form, env)):
                        return False
                x = forms[-1]
                toplevel = False
                continue

            if op is S_OR:
                forms = pylist(x.cdr, "or form")
                if not forms:
                    return False
                for form in forms[:-1]:
                    value = seval(form, env)
                    if is_true(value):
                        return value
                x = forms[-1]
                toplevel = False
                continue

            if op is S_QUASIQUOTE:
                return _quasi(_form_args(x, "quasiquote", 1, 1)[0], env, 1)

            if op is S_UNQUOTE or op is S_UNQUOTE_SPLICING:
                raise SchemeSyntaxError(f"{op} outside of quasiquote")

            if op is S_DEFINE_MACRO:
                if not toplevel:
                    raise SchemeSyntaxError(
                        "define-macro is only allowed at the top level")
                args = pylist(x.cdr, "define-macro form")
                if len(args) < 2:
                    raise SchemeSyntaxError(f"malformed define-macro: {scm_repr(x)}")
                target = args[0]
                if isinstance(target, Pair):
                    # (define-macro (name . params) body...)
                    if not isinstance(target.car, Symbol):
                        raise SchemeSyntaxError(f"malformed define-macro: {scm_repr(x)}")
                    name = target.car
                    proc = _make_procedure(target.cdr, args[1:], env, str(name))
                elif isinstance(target, Symbol):
                    if len(args) != 2:
                        raise SchemeSyntaxError(f"malformed define-macro: {scm_repr(x)}")
                    name = target
                    proc = seval(args[1], env)
                    if not isinstance(proc, Procedure) and not callable(proc):
                        raise SchemeSyntaxError(
                            "define-macro: transformer must be a procedure")
                else:
                    raise SchemeSyntaxError(f"malformed define-macro: {scm_repr(x)}")
                env.define(name, Macro(proc))
                return None

            if op is S_DELAY:
                arg = _form_args(x, "delay", 1, 1)[0]
                return Promise(arg, env)

            if op is S_DEFINE_SYNTAX:
                if not toplevel:
                    raise SchemeSyntaxError(
                        "define-syntax is only allowed at the top level")
                args = _form_args(x, "define-syntax", 2, 2)
                name = args[0]
                if not isinstance(name, Symbol):
                    raise SchemeSyntaxError(f"malformed define-syntax: {scm_repr(x)}")
                literals, rules, ellipsis = _parse_syntax_rules(args[1])

                def transformer(*call_args, _rules=rules, _literals=literals,
                                 _ellipsis=ellipsis, _name=name):
                    call_form = Pair(_name, slist(call_args))
                    for pattern, template in _rules:
                        bindings = {}
                        if _sr_match(pattern, call_form, _literals, _ellipsis, bindings):
                            return _sr_expand(template, bindings, _ellipsis)
                    raise SchemeSyntaxError(
                        f"no matching syntax-rules clause for {scm_repr(call_form)}")

                env.define(name, Macro(transformer))
                return None

        # ---------------------------------------------------- application
        proc = seval(op, env) if not isinstance(op, Symbol) else env.lookup(op)

        if isinstance(proc, Macro):
            x = apply_procedure(proc.proc, pylist(x.cdr, "macro call"))
            continue  # re-evaluate the expansion (toplevel preserved)

        args = []
        cur = x.cdr
        while isinstance(cur, Pair):
            args.append(seval(cur.car, env))
            cur = cur.cdr
        if cur is not nil:
            raise SchemeSyntaxError(f"improper argument list: {scm_repr(x)}")

        if isinstance(proc, Procedure):
            env = bind_params(proc, args)
            body = proc.body
            for form in body[:-1]:
                seval(form, env)
            x = body[-1]
            toplevel = False
            continue  # tail call

        if callable(proc):
            return proc(*args)

        raise SchemeTypeError(
            f"not a procedure: {scm_repr(proc)} in {scm_repr(x)}")
