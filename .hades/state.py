"""Local HADES state and packet checks; no model calls or command execution."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from uuid import uuid4


HADES_DIR = Path(__file__).resolve().parent
RUNS_DIR = HADES_DIR / "runs"
TERMINAL = {"success", "partial", "blocked"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def fields(value: object, expected: set[str], path: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected an object")
    require(set(value) == expected, f"{path}: expected exactly {sorted(expected)}")
    return value


def text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}: expected nonempty text")
    return value


def items(value: object, path: str) -> list:
    if not isinstance(value, list):
        raise ContractError(f"{path}: expected an array")
    return value


def texts(value: object, path: str, *, nonempty: bool = False) -> list[str]:
    entries = items(value, path)
    require(not nonempty or bool(entries), f"{path}: expected at least one item")
    for index, entry in enumerate(entries):
        text(entry, f"{path}[{index}]")
    return entries


def choice(value: object, allowed: set[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{path}: expected one of {sorted(allowed)}")
    return value


def identifier(value: object, path: str) -> str:
    value = text(value, path)
    require(IDENTIFIER.fullmatch(value) is not None, f"{path}: expected a simple alphanumeric ID")
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"JSON: duplicate key {key!r}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ContractError(f"JSON: invalid constant {value}")


def read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=unique_object, parse_constant=reject_constant)


def validate_failure(value: object, path: str = "failure") -> None:
    packet = fields(value, {
        "failed_objective", "observed", "evidence", "attempted", "likely_cause", "needed",
    }, path)
    for key in ("failed_objective", "observed", "needed"):
        text(packet[key], f"{path}.{key}")
    for key in ("evidence", "attempted"):
        texts(packet[key], f"{path}.{key}", nonempty=True)
    if packet["likely_cause"] is not None:
        text(packet["likely_cause"], f"{path}.likely_cause")


def validate_result(value: object, path: str = "result") -> None:
    packet = fields(value, {"status", "result", "changes", "tests", "issues", "confidence"}, path)
    status = choice(packet["status"], TERMINAL, f"{path}.status")
    text(packet["result"], f"{path}.result")
    texts(packet["changes"], f"{path}.changes")
    issues = texts(packet["issues"], f"{path}.issues", nonempty=status != "success")
    confidence = choice(packet["confidence"], {"high", "medium", "low"}, f"{path}.confidence")
    checks = items(packet["tests"], f"{path}.tests")
    for index, check in enumerate(checks):
        location = f"{path}.tests[{index}]"
        check = fields(check, {"command", "outcome", "evidence"}, location)
        text(check["command"], f"{location}.command")
        choice(check["outcome"], {"passed", "failed", "not_run"}, f"{location}.outcome")
        text(check["evidence"], f"{location}.evidence")
    if status == "success":
        require(not issues, f"{path}: success cannot have unresolved issues")
        require(confidence != "low", f"{path}: low confidence cannot be success")
        require(all(check["outcome"] != "failed" for check in checks),
                f"{path}: success cannot contain failed checks")


def validate_capsule(value: object, path: str = "capsule") -> None:
    capsule = fields(value, {
        "task_id", "objective", "context", "files", "constraints", "success",
        "depth", "output_budget_tokens", "result_path", "failure",
    }, path)
    identifier(capsule["task_id"], f"{path}.task_id")
    text(capsule["objective"], f"{path}.objective")
    text(capsule["result_path"], f"{path}.result_path")
    for key in ("context", "files", "constraints"):
        texts(capsule[key], f"{path}.{key}")
    texts(capsule["success"], f"{path}.success", nonempty=True)
    depth = capsule["depth"]
    budget = capsule["output_budget_tokens"]
    require(type(depth) is int and 1 <= depth <= 2, f"{path}.depth: expected 1 or 2")
    require(type(budget) is int and budget > 0, f"{path}.output_budget_tokens: expected a positive integer")
    if capsule["failure"] is not None:
        validate_failure(capsule["failure"], f"{path}.failure")


def validate_task(value: object, path: str = "task") -> None:
    task = fields(value, {
        "id", "objective", "complexity", "risk", "tier", "depends_on", "status", "result",
    }, path)
    task_id = identifier(task["id"], f"{path}.id")
    text(task["objective"], f"{path}.objective")
    complexity = choice(task["complexity"], {"D0", "D1", "D2", "D3", "D4"}, f"{path}.complexity")
    choice(task["risk"], {"low", "medium", "high", "critical"}, f"{path}.risk")
    tier = choice(task["tier"], {"tool", "luna", "sol", "astra"}, f"{path}.tier")
    require((complexity == "D0") == (tier == "tool"), f"{path}: D0 and tool must be paired")
    dependencies = texts(task["depends_on"], f"{path}.depends_on")
    for dependency in dependencies:
        identifier(dependency, f"{path}.depends_on")
    require(len(set(dependencies)) == len(dependencies), f"{path}: duplicate dependency")
    require(task_id not in dependencies, f"{path}: self dependency")
    status = choice(task["status"], {"pending", "running"} | TERMINAL, f"{path}.status")
    if status in TERMINAL:
        validate_result(task["result"], f"{path}.result")
        require(task["result"]["status"] == status, f"{path}: task/result status mismatch")
    else:
        require(task["result"] is None, f"{path}: pending/running task cannot have a final result")


def validate_state(value: object, path: str = "state") -> None:
    state = fields(value, {
        "version", "run_id", "profile", "goal", "status", "success_criteria",
        "constraints", "architecture", "important_files", "confirmed_facts",
        "failed_approaches", "open_issues", "current_test_state", "tasks",
    }, path)
    choice(state["version"], {"2.0"}, f"{path}.version")
    identifier(state["run_id"], f"{path}.run_id")
    choice(state["profile"], {"eco", "balanced", "max"}, f"{path}.profile")
    text(state["goal"], f"{path}.goal")
    status = choice(state["status"], {"pending", "running", "success", "blocked"}, f"{path}.status")
    for key in ("constraints", "important_files", "confirmed_facts", "failed_approaches", "open_issues"):
        texts(state[key], f"{path}.{key}")
    test_state = choice(state["current_test_state"], {"not_run", "passed", "failed", "not_applicable"},
                        f"{path}.current_test_state")
    architecture = fields(state["architecture"], {"relevant_components"}, f"{path}.architecture")
    texts(architecture["relevant_components"], f"{path}.architecture.relevant_components")
    criteria = items(state["success_criteria"], f"{path}.success_criteria")
    require(bool(criteria), f"{path}.success_criteria: expected at least one criterion")
    for index, criterion in enumerate(criteria):
        location = f"{path}.success_criteria[{index}]"
        criterion = fields(criterion, {"criterion", "status", "evidence"}, location)
        text(criterion["criterion"], f"{location}.criterion")
        outcome = choice(criterion["status"], {"pending", "passed", "failed"}, f"{location}.status")
        texts(criterion["evidence"], f"{location}.evidence", nonempty=outcome != "pending")

    tasks = items(state["tasks"], f"{path}.tasks")
    by_id = {}
    for index, task in enumerate(tasks):
        validate_task(task, f"{path}.tasks[{index}]")
        require(task["id"] not in by_id, f"{path}: duplicate task ID {task['id']}")
        by_id[task["id"]] = task
    for task in tasks:
        for dependency in task["depends_on"]:
            require(dependency in by_id, f"{path}: unknown dependency {dependency}")
            if task["status"] != "pending":
                require(by_id[dependency]["status"] == "success",
                        f"{path}: started task {task['id']} has unfinished dependency {dependency}")

    # Kahn's algorithm checks cycles without recursion limits on large task graphs.
    remaining = {task["id"]: len(task["depends_on"]) for task in tasks}
    children = {task_id: [] for task_id in by_id}
    for task in tasks:
        for dependency in task["depends_on"]:
            children[dependency].append(task["id"])
    ready = [task_id for task_id, count in remaining.items() if count == 0]
    visited = 0
    while ready:
        visited += 1
        for child in children[ready.pop()]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    require(visited == len(tasks), f"{path}: dependency cycle")

    if status == "pending":
        require(all(task["status"] == "pending" for task in tasks),
                f"{path}: pending run contains started tasks")
    if status == "success":
        require(bool(tasks) and all(task["status"] == "success" for task in tasks),
                f"{path}: success requires successful tasks")
        require(all(criterion["status"] == "passed" for criterion in criteria),
                f"{path}: success requires all criteria to pass with evidence")
        require(not state["open_issues"], f"{path}: success cannot have open issues")
        require(test_state in {"passed", "not_applicable"},
                f"{path}: success requires passed or explicitly inapplicable verification")
        checks = [check for task in tasks for check in task["result"]["tests"]]
        if test_state == "passed":
            require(bool(checks) and all(check["outcome"] == "passed" for check in checks),
                    f"{path}: passed verification requires actual passed checks, with none skipped")
        else:
            require(not checks, f"{path}: inapplicable verification cannot contain test commands")


VALIDATORS = {
    "capsule": validate_capsule,
    "result": validate_result,
    "failure": validate_failure,
    "task": validate_task,
    "state": validate_state,
}


def initialize(goal: str, success: list[str], profile: str, constraints: list[str]) -> Path:
    state = read_json(HADES_DIR / "templates" / "state.json")
    if not isinstance(state, dict):
        raise ContractError("state template: expected an object")
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex}"
    state.update(
        run_id=run_id,
        goal=goal,
        profile=profile,
        constraints=constraints,
        success_criteria=[
            {"criterion": criterion, "status": "pending", "evidence": []}
            for criterion in success
        ],
    )
    validate_state(state)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(mode=0o700)
    state_path = run_dir / "state.json"
    with state_path.open("x", encoding="utf-8") as target:
        json.dump(state, target, ensure_ascii=True, indent=2, allow_nan=False)
        target.write("\n")
    return state_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a fresh isolated run; never overwrite another run")
    init.add_argument("--goal", required=True)
    init.add_argument("--success", action="append", required=True)
    init.add_argument("--constraint", action="append", default=[])
    init.add_argument("--profile", choices=("eco", "balanced", "max"))
    check = commands.add_parser("validate", help="Validate JSON without executing packet contents")
    check.add_argument("kind", choices=tuple(VALIDATORS))
    check.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            policy = read_json(HADES_DIR / "config.json")
            if not isinstance(policy, dict) or "default_profile" not in policy:
                raise ContractError("config: expected an object with default_profile")
            profile = args.profile if args.profile is not None else policy["default_profile"]
            print(initialize(args.goal, args.success, profile, args.constraint))
        else:
            VALIDATORS[args.kind](read_json(args.path))
            print(f"OK: {args.kind} {args.path}")
    except (ContractError, json.JSONDecodeError, UnicodeError, OSError) as error:
        print(f"HADES error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
