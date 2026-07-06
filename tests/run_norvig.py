"""Run Peter Norvig's lispy test cases (tests/vendor/lispytest.py)
against pyscheme.

Usage: python tests/run_norvig.py [-v]
Exit code 0 iff every case passes.

Also collectible by pytest (test_norvig_suite).
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pyscheme import Interpreter, to_python, scm_repr  # noqa: E402


def load_cases():
    spec = importlib.util.spec_from_file_location(
        "lispytest", ROOT / "tests" / "vendor" / "lispytest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.lis_tests + module.lispy_tests


def run(verbose=False):
    interp = Interpreter()
    cases = load_cases()
    failures = []
    for source, expected in cases:
        try:
            result = interp.eval_string(source)
        except Exception as exc:
            ok = (isinstance(expected, type)
                  and issubclass(expected, Exception)
                  and isinstance(exc, expected))
            shown = f"raises {type(exc).__name__}: {exc}"
        else:
            converted = to_python(result)
            ok = converted == expected and not isinstance(expected, type)
            shown = scm_repr(result)
        if verbose or not ok:
            status = "ok  " if ok else "FAIL"
            print(f"{status}  {source!r}\n      => {shown}")
            if not ok:
                print(f"      expected: {expected!r}")
        if not ok:
            failures.append(source)
    print(f"\n{len(cases) - len(failures)}/{len(cases)} Norvig lispy tests pass.")
    return failures


def test_norvig_suite():
    assert run() == []


if __name__ == "__main__":
    sys.exit(1 if run(verbose="-v" in sys.argv) else 0)
