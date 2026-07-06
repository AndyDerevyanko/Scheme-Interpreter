"""Run the chibi-scheme R7RS test suite (tests/vendor/r7rs-tests.scm)
against pyscheme and report a compatibility score.

This is a *metric*, not a gate: the suite exercises the full R7RS-small
language (syntax-rules, ports, values, dynamic-wind, ...) and a small
foundation is not expected to pass all of it. The score should only go up.

Usage: python tests/run_r7rs.py [-v]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pyscheme import Interpreter, Pair, Symbol, intern, scm_repr  # noqa: E402
from pyscheme.builtins import scheme_equal  # noqa: E402
from pyscheme.evaluator import set_fuel  # noqa: E402
from pyscheme.reader import Reader  # noqa: E402

FUEL_PER_FORM = 3_000_000  # eval steps before a form is declared runaway

IGNORED_HEADS = {
    "import", "test-begin", "test-end", "include",
}
SKIPPED_TEST_HEADS = {
    "test-values", "test-error", "test-assert", "test-not",
}


def run(verbose=False):
    source = (ROOT / "tests" / "vendor" / "r7rs-tests.scm").read_text(
        encoding="utf-8")
    try:
        forms = Reader(source, "r7rs-tests.scm").read_all()
    except Exception as exc:
        print(f"READER FAILED on r7rs-tests.scm: {type(exc).__name__}: {exc}")
        return 1

    interp = Interpreter()
    passed = failed = errored = skipped = setup_errors = 0
    sym_test = intern("test")

    for form in forms:
        head = form.car if isinstance(form, Pair) else None
        name = str(head) if isinstance(head, Symbol) else None
        if name in IGNORED_HEADS:
            continue
        if name in SKIPPED_TEST_HEADS:
            skipped += 1
            continue
        if head is sym_test:
            try:
                expected_form = form.cdr.car
                expr_form = form.cdr.cdr.car
            except AttributeError:
                skipped += 1
                continue
            try:
                set_fuel(FUEL_PER_FORM)
                expected = interp.eval(expected_form)
                actual = interp.eval(expr_form)
            except Exception as exc:
                errored += 1
                if verbose:
                    print(f"ERROR {scm_repr(form)[:100]}"
                          f"\n      {type(exc).__name__}: {exc}")
                continue
            if scheme_equal(expected, actual):
                passed += 1
            else:
                failed += 1
                if verbose:
                    print(f"FAIL  {scm_repr(expr_form)[:100]}"
                          f"\n      got {scm_repr(actual)[:80]},"
                          f" want {scm_repr(expected)[:80]}")
        else:
            # Support code (defines, define-syntax, ...): best effort.
            try:
                set_fuel(FUEL_PER_FORM)
                interp.eval(form)
            except Exception as exc:
                setup_errors += 1
                if verbose:
                    print(f"setup error in {scm_repr(form)[:80]}: "
                          f"{type(exc).__name__}: {exc}")

    set_fuel(None)
    total = passed + failed + errored
    print(f"\nR7RS suite: {passed}/{total} test forms pass "
          f"({failed} wrong, {errored} raised, {skipped} skipped, "
          f"{setup_errors} setup forms failed)")
    return 0


if __name__ == "__main__":
    sys.exit(run(verbose="-v" in sys.argv))
