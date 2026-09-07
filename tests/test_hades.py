from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / ".hades"
spec = importlib.util.spec_from_file_location("hades_state", HADES / "state.py")
hades = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hades)


def template(name):
    return hades.read_json(HADES / "templates" / f"{name}.json")


def result(status="success"):
    return {
        "status": status,
        "result": "Completed the assigned change." if status == "success" else "Dependency is unavailable.",
        "changes": ["src/example.py"],
        "tests": [{"command": "python3 -m unittest", "outcome": "passed", "evidence": "3 tests passed"}],
        "issues": [] if status == "success" else ["Missing required dependency"],
        "confidence": "high" if status == "success" else "low",
    }


def task(task_id="implement", status="pending", dependencies=()):
    value = template("task")
    value.update(id=task_id, objective="Implement the requested change",
                 status=status, depends_on=list(dependencies))
    if status in hades.TERMINAL:
        value["result"] = result(status)
    return value


def state():
    value = template("state")
    value.update(run_id="test-run", goal="Implement a feature", tasks=[task()])
    value["success_criteria"] = [{"criterion": "Behavior verified", "status": "pending", "evidence": []}]
    return value


def capsule():
    value = template("context_capsule")
    value.update(task_id="implement", objective="Implement the requested change",
                 success=["Targeted tests pass"], result_path=".hades/runs/test-run/implement.json")
    return value


def failure():
    return {
        "failed_objective": "Implement the feature",
        "observed": "Dependency is unavailable",
        "evidence": ["ImportError from the targeted test"],
        "attempted": ["Ran the existing test command"],
        "likely_cause": None,
        "needed": "Decide whether to add the dependency",
    }


class PacketTests(unittest.TestCase):
    def test_all_packet_contracts_accept_filled_examples(self):
        for kind, value in (("result", result()), ("capsule", capsule()),
                            ("failure", failure()), ("task", task()), ("state", state())):
            with self.subTest(kind=kind):
                hades.VALIDATORS[kind](value)

    def test_blank_templates_are_not_successful_packets(self):
        for kind, filename in (("result", "result_packet"), ("capsule", "context_capsule"),
                               ("failure", "failure_packet"), ("task", "task"), ("state", "state")):
            with self.subTest(kind=kind), self.assertRaises(hades.ContractError):
                hades.VALIDATORS[kind](template(filename))

    def test_exact_fields_reject_missing_and_unknown_keys(self):
        for kind, value in (("result", result()), ("capsule", capsule()),
                            ("failure", failure()), ("task", task()), ("state", state())):
            for mutation in ("missing", "unknown"):
                changed = deepcopy(value)
                if mutation == "missing":
                    changed.pop(next(iter(changed)))
                else:
                    changed["conversation_history"] = "not allowed"
                with self.subTest(kind=kind, mutation=mutation), self.assertRaises(hades.ContractError):
                    hades.VALIDATORS[kind](changed)

    def test_malformed_value_types_raise_contract_errors(self):
        for kind, value in (("result", result()), ("capsule", capsule()),
                            ("failure", failure()), ("task", task()), ("state", state())):
            for key in value:
                changed = deepcopy(value)
                changed[key] = 42
                with self.subTest(kind=kind, key=key):
                    if kind == "capsule" and key == "output_budget_tokens":
                        hades.validate_capsule(changed)
                    else:
                        with self.assertRaises(hades.ContractError):
                            hades.VALIDATORS[kind](changed)

    def test_success_rejects_issues_failed_checks_and_low_confidence(self):
        for field, value in (("issues", ["Unresolved failure"]), ("confidence", "low"),
                             ("tests", [{"command": "test", "outcome": "failed", "evidence": "Failure"}])):
            packet = result()
            packet[field] = value
            with self.subTest(field=field), self.assertRaises(hades.ContractError):
                hades.validate_result(packet)

    def test_partial_and_blocked_need_explanations(self):
        for status in ("partial", "blocked"):
            packet = result(status)
            hades.validate_result(packet)
            packet["issues"] = []
            with self.subTest(status=status), self.assertRaises(hades.ContractError):
                hades.validate_result(packet)

    def test_not_run_requires_reason_and_is_not_rewritten(self):
        packet = result("blocked")
        packet["tests"] = [{"command": "test", "outcome": "not_run", "evidence": "Runner unavailable"}]
        hades.validate_result(packet)
        self.assertEqual(packet["tests"][0]["outcome"], "not_run")
        packet["tests"][0]["evidence"] = ""
        with self.assertRaises(hades.ContractError):
            hades.validate_result(packet)

    def test_capsule_budget_and_depth_limits(self):
        for key, values in (("depth", [0, 3, True, 1.0]),
                            ("output_budget_tokens", [0, -1, True, 1.5])):
            for value in values:
                packet = capsule()
                packet[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(hades.ContractError):
                    hades.validate_capsule(packet)
        packet = capsule()
        packet["depth"] = 2
        packet["failure"] = failure()
        hades.validate_capsule(packet)

    def test_failure_evidence_and_attempts_required(self):
        for key in ("evidence", "attempted", "needed"):
            packet = failure()
            packet[key] = [] if key != "needed" else ""
            with self.subTest(key=key), self.assertRaises(hades.ContractError):
                hades.validate_failure(packet)

    def test_json_rejects_duplicate_keys_nonfinite_values_and_invalid_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            for source in ('{"status": "success", "status": "blocked"}', '{"budget": NaN}',
                           '{"budget": Infinity}', '{"budget": -Infinity}', '{"broken":'):
                path.write_text(source, encoding="utf-8")
                with self.subTest(source=source), self.assertRaises((hades.ContractError, json.JSONDecodeError)):
                    hades.read_json(path)


class GraphTests(unittest.TestCase):
    def test_parallel_and_dependent_nodes(self):
        value = state()
        value.update(status="running", tasks=[
            task("discover", "success"), task("backend", "running", ["discover"]),
            task("frontend", "running", ["discover"]),
            task("integrate", dependencies=["backend", "frontend"]),
        ])
        hades.validate_state(value)

    def test_unknown_duplicate_self_and_cyclic_dependencies(self):
        variants = [
            [task("a", dependencies=["missing"])],
            [task("a"), task("a")],
            [task("a", dependencies=["a"])],
            [task("a"), task("b", dependencies=["a", "a"])],
            [task("a", dependencies=["b"]), task("b", dependencies=["a"])],
        ]
        for tasks in variants:
            value = state()
            value["tasks"] = tasks
            with self.subTest(tasks=tasks), self.assertRaises(hades.ContractError):
                hades.validate_state(value)

    def test_started_node_cannot_bypass_dependencies(self):
        for status in ("running", "success", "blocked", "partial"):
            value = state()
            value.update(status="running", tasks=[task("a"), task("b", status, ["a"])])
            with self.subTest(status=status), self.assertRaisesRegex(hades.ContractError, "unfinished dependency"):
                hades.validate_state(value)

    def test_failed_branch_preserves_independent_completed_work(self):
        value = state()
        value.update(status="blocked", tasks=[
            task("a", "blocked"), task("b", "success"), task("c", dependencies=["a"]),
        ])
        hades.validate_state(value)

    def test_task_status_must_match_result(self):
        value = task(status="success")
        value["result"] = result("blocked")
        with self.assertRaisesRegex(hades.ContractError, "status mismatch"):
            hades.validate_task(value)
        value = task()
        value["result"] = result()
        with self.assertRaises(hades.ContractError):
            hades.validate_task(value)

    def test_tool_only_routing(self):
        value = task()
        value.update(complexity="D0", tier="tool")
        hades.validate_task(value)
        value["tier"] = "luna"
        with self.assertRaises(hades.ContractError):
            hades.validate_task(value)
        value.update(complexity="D3", tier="tool")
        with self.assertRaises(hades.ContractError):
            hades.validate_task(value)

    def test_success_requires_completed_graph_and_evidenced_criteria(self):
        complete = state()
        complete.update(status="success", current_test_state="passed", tasks=[task(status="success")])
        complete["success_criteria"][0].update(status="passed", evidence=["Targeted tests passed"])
        hades.validate_state(complete)
        variants = []
        for key, value in (("tasks", []), ("tasks", [task()]), ("open_issues", ["Unresolved"]),
                           ("current_test_state", "failed"), ("current_test_state", "not_run")):
            changed = deepcopy(complete)
            changed[key] = value
            variants.append(changed)
        for outcome, evidence in (("pending", []), ("failed", ["Test failed"]), ("passed", [])):
            changed = deepcopy(complete)
            changed["success_criteria"][0].update(status=outcome, evidence=evidence)
            variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaises(hades.ContractError):
                hades.validate_state(changed)

    def test_passed_verification_cannot_be_empty_or_skipped(self):
        value = state()
        value.update(status="success", current_test_state="passed", tasks=[task(status="success")])
        value["success_criteria"][0].update(status="passed", evidence=["Result inspected"])
        for checks in ([], [{"command": "test", "outcome": "not_run", "evidence": "Runner unavailable"}]):
            value["tasks"][0]["result"]["tests"] = checks
            with self.subTest(checks=checks), self.assertRaises(hades.ContractError):
                hades.validate_state(value)
        value["current_test_state"] = "not_applicable"
        value["tasks"][0]["result"]["tests"] = []
        hades.validate_state(value)
        value["tasks"][0]["result"]["tests"] = result()["tests"]
        with self.assertRaises(hades.ContractError):
            hades.validate_state(value)

    def test_large_dag_does_not_hit_recursion_limit(self):
        value = state()
        value["tasks"] = [task(str(i), dependencies=[str(i - 1)] if i else []) for i in range(1500)]
        hades.validate_state(value)


class StateCliTests(unittest.TestCase):
    def test_isolated_runs_persist_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(hades, "RUNS_DIR", Path(directory) / "runs"):
            first = hades.initialize("First goal", ["First criterion"], "balanced", ["No new dependencies"])
            first_bytes = first.read_bytes()
            second = hades.initialize("Second goal", ["Second criterion"], "eco", [])
            self.assertNotEqual(first.parent, second.parent)
            self.assertEqual(first.read_bytes(), first_bytes)
            hades.validate_state(hades.read_json(first))
            hades.validate_state(hades.read_json(second))
            self.assertEqual(hades.read_json(first)["constraints"], ["No new dependencies"])

    def test_invalid_init_does_not_create_run(self):
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory) / "runs"
            with patch.object(hades, "RUNS_DIR", runs), self.assertRaises(hades.ContractError):
                hades.initialize(" ", ["Criterion"], "balanced", [])
            self.assertFalse(runs.exists())

    def test_cli_init_default_and_explicit_profiles(self):
        for profile in (None, "eco", "max"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                stdout = io.StringIO()
                args = ["init", "--goal", "Goal", "--success", "One", "--success", "Two", "--constraint", "No API"]
                if profile:
                    args.extend(["--profile", profile])
                with patch.object(hades, "RUNS_DIR", Path(directory)), redirect_stdout(stdout):
                    self.assertEqual(hades.main(args), 0)
                saved = hades.read_json(Path(stdout.getvalue().strip()))
                self.assertEqual(saved["profile"], profile or "balanced")
                self.assertEqual(len(saved["success_criteria"]), 2)

    def test_invalid_state_template_and_policy_surface_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "templates").mkdir()
            (base / "templates" / "state.json").write_text("[]", encoding="utf-8")
            (base / "config.json").write_text("{}", encoding="utf-8")
            with patch.object(hades, "HADES_DIR", base):
                with self.assertRaisesRegex(hades.ContractError, "state template"):
                    hades.initialize("Goal", ["Criterion"], "balanced", [])
                errors = io.StringIO()
                with redirect_stderr(errors):
                    self.assertEqual(hades.main(["init", "--goal", "Goal", "--success", "Criterion"]), 1)
                self.assertIn("default_profile", errors.getvalue())

    def test_cli_validation_exit_codes_and_read_only_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps(result()), encoding="utf-8")
            before = path.read_bytes()
            completed = subprocess.run(
                [sys.executable, str(HADES / "state.py"), "validate", "result", str(path)],
                capture_output=True, text=True, check=False, cwd=directory,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout.startswith("OK: result"))
            self.assertEqual(path.read_bytes(), before)
            path.write_text("{}", encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                self.assertEqual(hades.main(["validate", "result", str(path)]), 1)
                self.assertEqual(hades.main(["validate", "result", str(path.parent / "missing.json")]), 1)
            self.assertIn("HADES error:", errors.getvalue())


class NativeConfigurationTests(unittest.TestCase):
    def test_subscription_config_preserves_main_model_and_permissions(self):
        with (ROOT / ".codex" / "config.toml").open("rb") as source:
            config = tomllib.load(source)
        self.assertEqual(config["forced_login_method"], "chatgpt")
        self.assertEqual(config["agents"]["max_concurrent_threads_per_session"], 9)
        self.assertEqual(config["agents"]["max_depth"], 2)
        self.assertTrue(config["agents"]["enabled"])
        for key in ("model", "model_provider", "model_providers", "sandbox_mode", "approval_policy"):
            self.assertNotIn(key, config)

    def test_native_roles_and_models(self):
        expected = {
            "hades_astra": ("gpt-6-astra", "high"),
            "hades_sol": ("gpt-5.6-sol", "medium"),
            "hades_luna": ("gpt-5.6-luna", "low"),
        }
        roles = sorted((ROOT / ".codex" / "agents").glob("*.toml"))
        self.assertEqual(len(roles), 3)
        for path in roles:
            with path.open("rb") as source:
                role = tomllib.load(source)
            self.assertEqual(role["name"], path.stem)
            self.assertEqual((role["model"], role["model_reasoning_effort"]), expected[role["name"]])
            self.assertTrue(role["description"].strip())
            self.assertIn(".hades/templates/result_packet.json", role["developer_instructions"])
            self.assertNotIn("model_instructions_file", role)
            self.assertNotIn("sandbox_mode", role)

    def test_profiles_retain_quality_floor_and_tool_first_routing(self):
        policy = hades.read_json(HADES / "config.json")
        self.assertEqual(policy["default_profile"], "balanced")
        self.assertEqual(set(policy["profiles"]), {"eco", "balanced", "max"})
        self.assertEqual(policy["retry"]["same_tier_corrected_retries"], 1)
        self.assertEqual(policy["delegation"]["max_depth"], 2)
        self.assertIn("Sol", policy["verification"]["high"])
        self.assertIn("Astra", policy["verification"]["critical"])
        for profile in policy["profiles"].values():
            self.assertEqual(profile["initial_tier"]["D0"], "tool")
            self.assertEqual(profile["initial_tier"]["D4"], "astra")
            self.assertEqual(set(profile["initial_tier"]), {"D0", "D1", "D2", "D3", "D4"})
            self.assertTrue(all(type(budget) is int and budget > 0
                                for budget in profile["output_budget_tokens"].values()))

    def test_skill_is_discoverable_and_implicitly_enabled(self):
        skill = ROOT / ".agents" / "skills" / "hades"
        contents = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(contents.startswith("---\nname: hades\ndescription: "))
        self.assertIn("\n---\n", contents)
        self.assertIn(".hades/HADES_ORCHESTRATOR.md", contents)
        metadata = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$hades", metadata)
        self.assertIn(".agents/skills/hades/SKILL.md", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))

    def test_context_handoff_explicitly_disables_default_full_history_forks(self):
        skill = (ROOT / ".agents" / "skills" / "hades" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('fork_turns="none"', skill)
        with (ROOT / ".codex" / "agents" / "hades_sol.toml").open("rb") as source:
            role = tomllib.load(source)
        self.assertIn('fork_turns="none"', role["developer_instructions"])


if __name__ == "__main__":
    unittest.main()
