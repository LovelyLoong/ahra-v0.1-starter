from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml

from ahra import cli
from ahra.awkp_task_creator import AwkpTaskCreateRequest, AwkpTaskCreator
from ahra.ports import AwkpTaskCreatorPort


ROOT = Path(__file__).resolve().parents[1]


def _run_cli(argv: list[str]) -> tuple[int, dict, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv)
    payload = json.loads(stdout.getvalue() or stderr.getvalue())
    return code, payload, stderr.getvalue()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "initial",
    )
    return repo


def _write_request(root: Path, repo: Path, artifact_dir: Path) -> Path:
    request = {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "WorkflowRunRequest",
        "metadata": {"name": "cli-fixture-standard"},
        "spec": {
            "moduleId": "standard-harness",
            "input": {
                "task": {
                    "id": "set-value",
                    "title": "Set value",
                    "objective": "Set VALUE to 2",
                    "acceptance_criteria": ["VALUE equals 2"],
                    "checks": [
                        {
                            "name": "value check",
                            "argv": [
                                sys.executable,
                                "-c",
                                "import value; assert value.VALUE == 2",
                            ],
                        }
                    ],
                    "policy": {
                        "allowed_globs": ["value.py"],
                        "protected_globs": [],
                        "sensitive_globs": [],
                        "max_changed_files": 1,
                        "max_added_lines": 5,
                        "max_deleted_lines": 5,
                    },
                }
            },
            "workspaceRef": str(repo),
            "driverRef": "fake-reference",
            "storeRef": "local-file",
            "artifactDir": str(artifact_dir),
            "approvalMode": "manual",
        },
    }
    path = root / "request.yaml"
    path.write_text(yaml.safe_dump(request, sort_keys=False), encoding="utf-8")
    return path


def _write_codex_sdk_request(root: Path, repo: Path, artifact_dir: Path) -> Path:
    path = _write_request(root, repo, artifact_dir)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["spec"]["driverRef"] = "codex-python-sdk"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path

class FailingDriver:
    async def run(self, request):
        raise RuntimeError("driver broke")


def _failing_sdk_registry(*, enable_fixture_driver: bool = False):
    registry = cli.AgentDriverRegistry()
    registry.register("codex-python-sdk", FailingDriver())
    if enable_fixture_driver:
        registry.register("fake-reference", cli.FixtureDriver())
    return registry

def _write_task(root: Path) -> Path:
    task_dir = root / "work" / "tasks" / "TASK-CLI"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(
        """---
type: WorkItem
id: TASK-CLI
schema_version: awkp/0.1
title: CLI inspect task
description: Temporary test task.
context_id: CTX-cli-test
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T00:00:00Z
depends_on: []
input_refs: []
output_contract: []
---

# Goal

Exercise task inspect.

# Acceptance criteria

- [ ] CLI returns criteria.
""",
        encoding="utf-8",
    )
    (task_dir / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "awkp/0.1",
                "task_id": "TASK-CLI",
                "context_id": "CTX-cli-test",
                "state": "working",
                "state_version": 1,
                "owner": "agent:test",
                "attempt": 1,
                "lease": None,
                "next_action": "Inspect.",
                "pause_reason": None,
                "blockers": [],
                "artifact_refs": [],
                "evidence_refs": [],
                "updated_at": "2026-06-23T00:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


def _lint_generated_awkp_root(root: Path) -> tuple[list[str], list[str]]:
    spec = importlib.util.spec_from_file_location("lint_awkp_generated_test", ROOT / "scripts" / "lint_awkp.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = root
    module.ERRORS = []
    module.WARNINGS = []
    module.lint_docs()
    module.lint_tasks()
    return module.ERRORS, module.WARNINGS


class CliTests(unittest.TestCase):
    def test_default_help_hides_legacy_workflow_group(self) -> None:
        help_text = cli._build_parser().format_help()

        self.assertIn("create", help_text)
        self.assertIn("claim", help_text)
        self.assertIn("orchestrate-review", help_text)
        self.assertIn("goal", help_text)
        self.assertIn("fixture", help_text)
        self.assertIn("evidence-gate", help_text)
        self.assertIn("workflow-sequence", help_text)
        self.assertNotIn("Legacy workflow compatibility commands", help_text)

    def test_goal_start_allow_development_agent_injects_codex_driver(self) -> None:
        with mock.patch("ahra.cli.GoalOperationService") as service_cls, mock.patch(
            "ahra.adapters.codex_sdk.CodexSDKDriver"
        ) as driver_cls:
            service = service_cls.return_value
            service.start.return_value = {"profileRef": "profile/development-bounded"}

            code, payload, _ = _run_cli(["goal", "start", "request.yaml", "--allow-development-agent"])

            self.assertEqual(code, 0)
            self.assertEqual(payload["result"]["profileRef"], "profile/development-bounded")
            driver_cls.assert_called_once_with()
            service_cls.assert_called_once_with(real_executor_driver=driver_cls.return_value)
            service.start.assert_called_once_with(Path("request.yaml"), run_once=False)

    def test_task_creator_implements_port(self) -> None:
        creator = AwkpTaskCreator()

        self.assertIsInstance(creator, AwkpTaskCreatorPort)
        self.assertIsNotNone(AwkpTaskCreateRequest)

    def test_task_create_writes_lint_clean_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code, payload, _ = _run_cli(
                [
                    "task",
                    "create",
                    "TASK-CLI-CREATE",
                    "--work-root",
                    str(root / "work"),
                    "--title",
                    "Created task",
                    "--description",
                    "Create a governed task skeleton.",
                    "--context-id",
                    "CTX-cli-test",
                    "--acceptance",
                    "Skeleton has the required task files.",
                    "--acceptance",
                    "The generated task is ready at version 0.",
                    "--output-contract",
                    "verification_summary",
                    "--actor",
                    "agent:cli-test",
                ]
            )

            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            task_dir = root / "work" / "tasks" / "TASK-CLI-CREATE"
            self.assertEqual(Path(payload["result"]["task_dir"]), task_dir)
            self.assertTrue((task_dir / "task.md").exists())
            self.assertTrue((task_dir / "state.json").exists())
            self.assertTrue((task_dir / "events.jsonl").exists())
            self.assertTrue((task_dir / "artifact-manifest.json").exists())
            self.assertTrue((task_dir / "evidence-manifest.json").exists())
            self.assertTrue((task_dir / "evidence").is_dir())
            self.assertTrue((task_dir / "handoffs").is_dir())

            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "ready")
            self.assertEqual(state["state_version"], 0)
            self.assertIsNone(state["lease"])
            task_md = (task_dir / "task.md").read_text(encoding="utf-8")
            self.assertIn("# Acceptance criteria", task_md)
            self.assertIn("- [ ] Skeleton has the required task files.", task_md)
            events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[0]["event_type"], "task_created")
            self.assertEqual(events[0]["actor"], "agent:cli-test")
            self.assertEqual(
                json.loads((task_dir / "artifact-manifest.json").read_text(encoding="utf-8"))["artifacts"],
                [],
            )
            self.assertEqual(
                json.loads((task_dir / "evidence-manifest.json").read_text(encoding="utf-8"))["evidence"],
                [],
            )
            errors, warnings = _lint_generated_awkp_root(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_task_claim_uses_governed_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            create_code, _, _ = _run_cli(
                [
                    "task",
                    "create",
                    "TASK-CLI-CLAIM",
                    "--work-root",
                    str(root / "work"),
                    "--title",
                    "Claim task",
                    "--description",
                    "Claim a generated task.",
                    "--context-id",
                    "CTX-cli-test",
                    "--acceptance",
                    "Task can be claimed.",
                ]
            )
            self.assertEqual(create_code, 0)

            code, payload, _ = _run_cli(
                [
                    "task",
                    "claim",
                    "TASK-CLI-CLAIM",
                    "--work-root",
                    str(root / "work"),
                    "--expected-version",
                    "0",
                    "--actor",
                    "agent:cli-test",
                    "--idempotency-key",
                    "TASK-CLI-CLAIM:claim:test",
                ]
            )

            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["result"]["from_state"], "ready")
            self.assertEqual(payload["result"]["to_state"], "working")
            self.assertEqual(payload["result"]["state_version"], 1)
            self.assertTrue(str(payload["result"]["fencing_token"]).startswith("FENCE-"))
            task_dir = root / "work" / "tasks" / "TASK-CLI-CLAIM"
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "working")
            self.assertEqual(state["owner"], "agent:cli-test")
            self.assertEqual(state["lease"]["holder"], "agent:cli-test")
            self.assertEqual(state["lease"]["fencing_token"], payload["result"]["fencing_token"])
            events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[-1]["event_type"], "lease_acquired")
            self.assertEqual(events[-1]["idempotency_key"], "TASK-CLI-CLAIM:claim:test")
            self.assertEqual(events[-1]["lease_fencing_token"], payload["result"]["fencing_token"])

    def test_task_orchestrate_review_rejects_same_producer_and_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            code, payload, _ = _run_cli(
                [
                    "task",
                    "orchestrate-review",
                    "TASK-CLI-MISSING",
                    "--work-root",
                    str(root / "work"),
                    "--expected-version",
                    "1",
                    "--producer-actor",
                    "agent:same",
                    "--verifier-actor",
                    "agent:same",
                    "--fencing-token",
                    "FENCE-1",
                    "--report",
                    str(root / "missing-report.json"),
                ]
            )

            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertIn("verifier_actor must differ from producer_actor", payload["error"])

    def test_goal_bridge_awkp_task_rejects_same_producer_and_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            code, payload, _ = _run_cli(
                [
                    "goal",
                    "bridge-awkp-task",
                    "GEXEC-missing",
                    "--task",
                    "TASK-CLI-MISSING",
                    "--work-root",
                    str(root / "work"),
                    "--db",
                    str(root / "missing.sqlite3"),
                    "--artifact-dir",
                    str(root / "artifacts"),
                    "--expected-task-version",
                    "1",
                    "--producer-actor",
                    "agent:same",
                    "--verifier-actor",
                    "agent:same",
                    "--fencing-token",
                    "FENCE-1",
                    "--report",
                    str(root / "missing-report.json"),
                ]
            )

            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["code"], "producer_verifier_identity_conflict")

    def test_task_create_rejects_malformed_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad_id_code, bad_id_payload, _ = _run_cli(
                [
                    "task",
                    "create",
                    "BAD-ID",
                    "--work-root",
                    str(root / "work"),
                    "--title",
                    "Bad task",
                    "--description",
                    "Bad task.",
                    "--context-id",
                    "CTX-cli-test",
                    "--acceptance",
                    "Criterion.",
                ]
            )
            self.assertEqual(bad_id_code, 2)
            self.assertFalse(bad_id_payload["ok"])
            self.assertIn("invalid task id", bad_id_payload["error"])

            missing_criteria_code, missing_criteria_payload, _ = _run_cli(
                [
                    "task",
                    "create",
                    "TASK-CLI-BAD",
                    "--work-root",
                    str(root / "work"),
                    "--title",
                    "Bad task",
                    "--description",
                    "Bad task.",
                    "--context-id",
                    "CTX-cli-test",
                ]
            )
            self.assertEqual(missing_criteria_code, 2)
            self.assertFalse(missing_criteria_payload["ok"])
            self.assertIn("at least one --acceptance", missing_criteria_payload["error"])

    def test_workflow_validate_reports_request_summary(self) -> None:
        code, payload, _ = _run_cli(
            ["workflow", "validate", str(ROOT / "examples/workflow_runs/fixtures/standard-task.yaml")]
        )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["module_id"], "standard-harness")
        self.assertEqual(payload["result"]["driver_ref"], "fake-reference")

    def test_workflow_start_fails_closed_without_fixture_driver(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            request = _write_request(root, repo, root / "artifacts")

            code, payload, _ = _run_cli(["workflow", "start", str(request)])

            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertIn("unknown agent driver ref", payload["error"])

    def test_workflow_start_failure_state_is_cli_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            request = _write_codex_sdk_request(root, repo, root / "artifacts")

            with mock.patch.object(cli, "_driver_registry", _failing_sdk_registry):
                code, payload, _ = _run_cli(["workflow", "start", str(request)])

            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertIn("workflow finished in a failure state", payload["error"])

    def test_workflow_start_can_use_explicit_fixture_driver(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            artifact_dir = root / "artifacts"
            request = _write_request(root, repo, artifact_dir)

            code, payload, _ = _run_cli(
                ["workflow", "start", str(request), "--enable-fixture-driver"]
            )

            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["result"]["status"], "accepted")
            self.assertTrue((artifact_dir / "workflow-run-result.json").exists())
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")

    def test_workflow_inspect_reads_artifact_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            artifact_dir = root / "artifacts"
            request = _write_request(root, repo, artifact_dir)
            start_code, _, _ = _run_cli(
                ["workflow", "start", str(request), "--enable-fixture-driver"]
            )
            self.assertEqual(start_code, 0)

            code, payload, _ = _run_cli(["workflow", "inspect", str(artifact_dir)])

            self.assertEqual(code, 0)
            self.assertEqual(payload["result"]["workflow-run-result.json"]["status"], "accepted")
            self.assertIsNotNone(payload["result"]["artifact-manifest.json"])

    def test_task_inspect_wraps_evidence_gate_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _write_task(root)

            code, payload, _ = _run_cli(
                ["task", "inspect", "TASK-CLI", "--work-root", str(root / "work")]
            )

            self.assertEqual(code, 0)
            self.assertEqual(payload["result"]["state.json"]["state"], "working")
            self.assertEqual(len(payload["result"]["acceptance_criteria"]), 1)

    def test_doctor_dry_run_lists_default_checks(self) -> None:
        code, payload, _ = _run_cli(["doctor", "--dry-run"])

        self.assertEqual(code, 0)
        commands = payload["result"]["commands"]
        self.assertEqual(len(commands), 3)
        self.assertIn("scripts/check.py", commands[0])
        self.assertEqual(commands[-1], ["git", "diff", "--check"])


if __name__ == "__main__":
    unittest.main()
