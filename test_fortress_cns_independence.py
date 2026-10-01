"""fortress-kernel is independent of CNS, and these tests hold whether or not
CNS is installed. Each one that needs CNS absent runs in a fresh interpreter in
which ``cns`` is blocked outright (``sys.modules['cns'] = None`` makes any
import of it fail), so the result does not depend on what the test
environment happens to contain. None of them ever skips.
"""

import ast
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BLOCK = "import sys; sys.modules['cns'] = None; sys.modules['cns.gate'] = None\n"

PIN = "3b465dbcc1a6a4ab6f1040f93d44483196abd737"

SOURCES = ("fortress_unified.py", "fortress_cns_connector.py", "__init__.py")


def _run(code, block=True, extra_path=None):
    path = os.pathsep.join([str(ROOT)] + ([str(extra_path)] if extra_path else []))
    return subprocess.run(
        [sys.executable, "-c", (BLOCK if block else "") + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": path, "PATH": ""},
        timeout=120,
    )


def _stub_cns(into, gate_source):
    """A ``cns`` package that can be imported, whatever the environment holds.

    It lets a test exercise "CNS is present" where the real one is absent, so
    what the kernel does about a present CNS is checked in both environments.
    ``gate_source`` is the text of ``cns/gate.py``, or None for a release that
    has no ``cns.gate`` at all.
    """
    package = Path(into) / "cns"
    package.mkdir()
    (package / "__init__.py").write_text("")
    if gate_source is not None:
        (package / "gate.py").write_text(gate_source)
    return into


def _dynamic_imports(name):
    """``(scope, first argument)`` of every call that imports a module by name at run time."""
    tree = ast.parse((ROOT / name).read_text(), filename=name)
    found = []

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            if isinstance(child, ast.Call):
                func = child.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if called in ("import_module", "__import__"):
                    first = child.args[0] if child.args else None
                    found.append((scope, first.value if isinstance(first, ast.Constant) else None))
            visit(child, inner)

    visit(tree, None)
    return found


def _pyproject():
    return (ROOT / "pyproject.toml").read_text()


class TestKernelWithCnsBlocked(unittest.TestCase):
    def test_kernel_and_connector_import_with_cns_blocked(self):
        done = _run("import fortress_unified, fortress_cns_connector; print('ok')")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "ok")

    def test_kernel_still_decides_with_cns_blocked(self):
        done = _run(
            """
            from fortress_unified import (
                FortressConfig, FortressUnified, ImmutableAuditLedger,
                InvariantMonitor, MandateLayer, Payload,
            )
            for mode in ("sage", "lyapunov", "energy"):
                fortress = FortressUnified(FortressConfig(controller_mode=mode))
                signed = Payload("Test", {"source_id": "s", "signature": "g"})
                out = fortress.process(signed, 5.0, 100.0)
                assert "output" in out and fortress.audit.verify_integrity()
            try:
                FortressUnified(FortressConfig()).process(Payload("Test", {}), float("nan"), 100.0)
            except ValueError:
                pass
            else:
                raise AssertionError("NaN error was not refused")
            assert InvariantMonitor.check(300.0, 0.5, 5.0, 2.0) == ["STATE_DIVERGENCE"]
            assert MandateLayer.enforce({"delta": 100.0}, 50.0, 100.0, 2.0)["delta"] <= 30.0
            print('ok')
            """
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "ok")

    def test_connector_says_what_is_missing_when_cns_is_blocked(self):
        done = _run(
            """
            from fortress_cns_connector import (
                INSTALL_HINT, CnsNotInstalled, NumericSafetyGate, cns_available, cns_chain,
            )
            assert cns_available() is False
            for call in (NumericSafetyGate, cns_chain):
                try:
                    call()
                except CnsNotInstalled as exc:
                    assert INSTALL_HINT in str(exc), str(exc)
                    assert isinstance(exc, ImportError)
                else:
                    raise AssertionError("no CnsNotInstalled from " + call.__name__)
            print('ok')
            """
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "ok")

    def test_every_gate_fails_at_construction_not_first_use(self):
        done = _run(
            """
            import fortress_cns_connector as c
            for cls in (c.NumericSafetyGate, c.MandateGate, c.InvariantGate, c.AuditChainGate):
                try:
                    cls()
                except c.CnsNotInstalled:
                    continue
                raise AssertionError(cls.__name__ + " was constructed without cns")
            try:
                c.to_cns_result("invariants", passed=True, content={})
            except c.CnsNotInstalled:
                print('ok')
            """
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "ok")


class TestNothingLoadsCnsEarly(unittest.TestCase):
    def test_importing_loads_nothing_from_cns_even_when_it_is_installed(self):
        # No block here: in an environment where cns is installed, this is what
        # shows the import is lazy. Where it is absent it holds trivially.
        done = _run(
            """
            import sys
            import fortress_unified, fortress_cns_connector
            loaded = sorted(m for m in sys.modules if m == 'cns' or m.startswith('cns.'))
            assert loaded == [], loaded
            print('ok')
            """,
            block=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "ok")

    def test_no_source_file_imports_cns_by_name(self):
        # The only way in is importlib.import_module("cns.gate") inside a function.
        for name in SOURCES:
            tree = ast.parse((ROOT / name).read_text(), filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    roots = [(node.module or "").split(".")[0]] if node.level == 0 else []
                else:
                    continue
                self.assertNotIn("cns", roots, f"{name} line {node.lineno} imports cns directly")


class TestAPresentCnsIsNotLoadedEarly(unittest.TestCase):
    """Import-time regressions that a try/except would hide where CNS is absent.

    A stub ``cns`` is put on the path, so the answer does not depend on whether
    the real one is installed: if anything imports it while the kernel or the
    connector loads, it shows up in ``sys.modules``, wrapped in a try or not.
    """

    def test_loading_the_kernel_the_connector_and_the_root_package_imports_nothing(self):
        with tempfile.TemporaryDirectory() as stub:
            _stub_cns(stub, "MARKER = True\n")
            done = _run(
                f"""
                import importlib.util, sys
                assert importlib.util.find_spec("cns") is not None, "stub cns is not on the path"
                import fortress_unified, fortress_cns_connector
                spec = importlib.util.spec_from_file_location(
                    "fortress_root_package", {str(ROOT / "__init__.py")!r}
                )
                root = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(root)
                loaded = sorted(m for m in sys.modules if m == "cns" or m.startswith("cns."))
                assert loaded == [], loaded
                # The stub really is importable, so the check above was not vacuous.
                import cns.gate
                assert cns.gate.MARKER is True
                assert fortress_cns_connector.cns_available() is True
                print("ok")
                """,
                block=False,
                extra_path=stub,
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "ok")

    def test_the_kernel_and_the_root_package_cannot_import_a_module_by_name(self):
        for name in ("fortress_unified.py", "__init__.py"):
            text = (ROOT / name).read_text()
            for word in ("importlib", "__import__", "import_module"):
                self.assertNotIn(word, text, f"{name} can import modules by name")

    def test_the_connector_imports_cns_gate_in_one_function_and_nowhere_else(self):
        # Not at module level, not in a try at module level, not in a second place.
        self.assertEqual(_dynamic_imports("fortress_cns_connector.py"), [("_cns_gate", "cns.gate")])


class TestACnsThatIsPresentButUnusable(unittest.TestCase):
    """cns_available() and the gates say CNS is missing; they never leak its failure."""

    CASES = (
        ("a gate module that raises RuntimeError", "raise RuntimeError('boom')\n", "RuntimeError"),
        (
            "a Python too old for it",
            "raise TypeError(\"dataclass() got an unexpected keyword argument 'slots'\")\n",
            "TypeError",
        ),
        ("a release without cns.gate", None, "ModuleNotFoundError"),
    )

    def test_it_is_reported_as_not_installed_with_the_underlying_error_named(self):
        for label, gate_source, error in self.CASES:
            with self.subTest(cns=label), tempfile.TemporaryDirectory() as stub:
                _stub_cns(stub, gate_source)
                done = _run(
                    f"""
                    import fortress_unified, fortress_cns_connector as c
                    assert c.cns_available() is False
                    for call in (c.NumericSafetyGate, c.MandateGate, c.InvariantGate,
                                 c.AuditChainGate, c.cns_chain):
                        try:
                            call()
                        except c.CnsNotInstalled as exc:
                            assert isinstance(exc, ImportError)
                            assert c.INSTALL_HINT in str(exc), str(exc)
                            assert {error!r} in str(exc), str(exc)
                        else:
                            raise AssertionError(call.__name__ + " was built on an unusable cns")
                    try:
                        c.to_cns_result("invariants", passed=True, content={{}})
                    except c.CnsNotInstalled:
                        pass
                    else:
                        raise AssertionError("to_cns_result ran on an unusable cns")
                    # The kernel is untouched by any of it.
                    fortress = fortress_unified.FortressUnified(fortress_unified.FortressConfig())
                    out = fortress.process(fortress_unified.Payload("t", {{}}), 5.0, 100.0)
                    assert "output" in out and fortress.audit.verify_integrity()
                    print("ok")
                    """,
                    block=False,
                    extra_path=stub,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.strip(), "ok")


class TestTheInstallCommandResolves(unittest.TestCase):
    def test_the_hint_is_a_direct_reference_not_a_bare_index_name(self):
        # fortress-kernel is on no package index. A bare name does not resolve,
        # and installing one from an index is a dependency-confusion exposure.
        done = _run("import fortress_cns_connector as c; print(c.INSTALL_HINT)")
        self.assertEqual(done.returncode, 0, done.stderr)
        hint = done.stdout.strip()
        self.assertTrue(hint.startswith("pip install 'fortress-kernel[cns] @ git+https://"), hint)
        self.assertIn("github.com/wking53214/fortress-kernel", hint)

    def test_the_readme_tells_the_reader_the_same_command(self):
        done = _run("import fortress_cns_connector as c; print(c.INSTALL_HINT)")
        self.assertIn(done.stdout.strip(), (ROOT / "README.md").read_text())


class TestPackagingDeclaresNoRuntimeDependency(unittest.TestCase):
    def test_numpy_stays_the_only_runtime_dependency(self):
        found = re.search(r"^dependencies\s*=\s*\[(.*?)\]", _pyproject(), re.M | re.S)
        self.assertIsNotNone(found)
        self.assertEqual(re.findall(r'"([^"]+)"', found.group(1)), ["numpy>=1.24.0"])

    def test_cns_is_an_optional_extra_pinned_to_the_sha(self):
        text = _pyproject()
        section = text.split("[project.optional-dependencies]", 1)[1].split("\n[", 1)[0]
        found = re.search(r"^cns\s*=\s*\[(.*?)\]", section, re.M | re.S)
        self.assertIsNotNone(found, "no cns extra")
        self.assertIn(f"cns.git@{PIN}", found.group(1))

    def test_the_connector_ships_in_the_wheel(self):
        # A module left out of py-modules is silently left out of the wheel.
        found = re.search(r"^py-modules\s*=\s*\[(.*?)\]", _pyproject(), re.M | re.S)
        self.assertIsNotNone(found)
        self.assertEqual(
            re.findall(r'"([^"]+)"', found.group(1)),
            ["fortress_unified", "fortress_cns_connector"],
        )


if __name__ == "__main__":
    unittest.main()
