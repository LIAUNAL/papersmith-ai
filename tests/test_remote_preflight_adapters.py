"""The two shipped backends answer `preflight`'s optional hooks
(remote-preflight S1b, S1f, S1g) without submitting anything and without
reading a credential: `interpreter_check`, `account_check`,
`accelerator_request`. Every child process here is a fake script; nothing
reaches a network.

Run with: python3 -m unittest tests.test_remote_preflight_adapters
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "skills/remote-execution/scripts"


def _load_or_reuse(module_name: str, script: Path):
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_or_reuse("remote_execution_adapter", SCRIPTS / "adapter.py")
KAGGLE = _load_or_reuse("remote_execution_kaggle_adapter", SCRIPTS / "adapters" / "kaggle.py")
COLAB = _load_or_reuse("remote_execution_colab_adapter", SCRIPTS / "adapters" / "colab.py")

FAKE_ACCOUNTS = r'''import json, sys
args = sys.argv[1:]
LOG = {log!r}
with open(LOG, "a") as handle:
    handle.write(json.dumps(args) + "\n")
if args[:1] == ["list"]:
    print(json.dumps({{"accounts": [{{"username": "acct-a"}}, {{"username": "acct-b"}}]}}))
elif args[:1] == ["validate"]:
    name = args[args.index("--account") + 1]
    ok = name == "acct-a"
    print(json.dumps({{"accounts": [{{"username": name, "ok": ok,
                                      "detail": "ok" if ok else "rejected (HTTP 401)"}}]}}))
    sys.exit(0 if ok else 1)
'''


class KaggleHooksTests(unittest.TestCase):
    def setUp(self) -> None:
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.root = Path(box.name)
        self.log = self.root / "accounts.log"
        self.accounts_cli = self.root / "accounts_cli.py"
        self.accounts_cli.write_text(FAKE_ACCOUNTS.format(log=str(self.log)), encoding="utf-8")
        self.registry = self.root / "absent" / "team.json"

    def adapter(self, **extra):
        return KAGGLE.KaggleAdapter(accounts_cli=self.accounts_cli,
                                    team_registry=self.registry, **extra)

    def _driver(self, payload: dict, code: int = 0) -> Path:
        driver = self.root / "driver.py"
        driver.write_text(f"import json, sys\nprint(json.dumps({payload!r}))\nsys.exit({code})\n",
                          encoding="utf-8")
        return driver

    def test_interpreter_check_runs_the_driver_selftest(self) -> None:
        ok = self.adapter(driver_script=self._driver({"ok": True, "interpreter": "x"}))
        self.assertTrue(ok.interpreter_check()["ok"])
        bad = self.adapter(driver_script=self._driver(
            {"ok": False, "error": "kagglesdk is not importable: No module named kagglesdk"}, 1))
        result = bad.interpreter_check()
        self.assertFalse(result["ok"])
        self.assertIn("not importable", result["evidence"])

    def test_account_check_validates_only_that_stored_account(self) -> None:
        result = self.adapter().account_check("acct-a")
        self.assertTrue(result["ok"], result)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertIn(["validate", "--account", "acct-a", "--json"], calls)
        rejected = self.adapter().account_check("acct-b")
        self.assertFalse(rejected["ok"])
        self.assertIn("401", rejected["evidence"])

    def test_account_check_refuses_a_worker_the_service_does_not_list(self) -> None:
        result = self.adapter().account_check("acct-z")
        self.assertFalse(result["ok"])
        self.assertIn("acct-z", result["evidence"])
        self.assertIn("--attest", result["fix"])

    def test_accelerator_request_names_the_pushed_machine(self) -> None:
        request = self.adapter().accelerator_request(
            {"accelerator": {"kind": "cuda", "architectures": ["sm_75"]}})
        self.assertEqual(request["name"], KAGGLE.KAGGLE_MACHINE_SHAPE)
        self.assertEqual(request["architectures"], ["sm_75"])
        self.assertIsNone(request["problem"])

    def test_accelerator_request_flags_an_architecture_the_machine_lacks(self) -> None:
        request = self.adapter().accelerator_request(
            {"accelerator": {"kind": "cuda", "architectures": ["sm_80"]}})
        self.assertIn("sm_80", request["problem"])


class ColabHooksTests(unittest.TestCase):
    def setUp(self) -> None:
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.root = Path(box.name)
        self.registry = self.root / "team.json"
        self.signed = self.root / "ana-state"
        (self.signed / ".config" / "colab-cli").mkdir(parents=True)
        (self.signed / ".config" / "colab-cli" / "token.json").write_text("{}", encoding="utf-8")
        members = [
            {"owner": "ana", "accounts": {"colab": {"tier": "pro", "configDir": str(self.signed)}}},
            {"owner": "luis", "accounts": {"colab": {"tier": "pro",
                                                      "configDir": str(self.root / "nobody")}}},
        ]
        self.registry.write_text(json.dumps({"schema": 1, "members": members}), encoding="utf-8")

    def adapter(self, **extra):
        return COLAB.ColabAdapter(team_registry=self.registry, **extra)

    def test_account_check_reads_sign_in_from_the_state_directory_only(self) -> None:
        self.assertTrue(self.adapter().account_check("colab:ana")["ok"])
        missing = self.adapter().account_check("colab:luis")
        self.assertFalse(missing["ok"])
        self.assertIn("sign", missing["fix"])

    def test_account_check_refuses_an_undeclared_worker(self) -> None:
        self.assertFalse(self.adapter().account_check("colab:eva")["ok"])

    def test_interpreter_check_finds_the_cli_on_path(self) -> None:
        self.assertFalse(self.adapter(colab_executable=str(self.root / "no-cli"))
                         .interpreter_check()["ok"])
        self.assertTrue(self.adapter(colab_executable=sys.executable).interpreter_check()["ok"])

    def test_accelerator_request_maps_the_declared_architecture(self) -> None:
        request = self.adapter().accelerator_request(
            {"accelerator": {"kind": "cuda", "architectures": ["sm_80"]}})
        self.assertEqual(request["name"], "A100")
        self.assertIsNone(request["problem"])
        self.assertEqual(self.adapter().accelerator_request({})["name"], "cpu")


class HooksStayOptionalTests(unittest.TestCase):
    def test_the_abc_still_holds_six_operations(self) -> None:
        self.assertEqual(len(ADAPTER.Adapter.__abstractmethods__), 6)


if __name__ == "__main__":
    unittest.main()
