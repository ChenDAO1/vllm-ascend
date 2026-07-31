import json
import os
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.ut.tools.bisect.test_aop_shell_chain import _find_bash, _shell_path

REPO_ROOT = Path(__file__).resolve().parents[4]
COMMAND_WORKFLOW = REPO_ROOT / ".github/workflows/pr_nightly_command.yml"

PARAMETERS = {
    "good_commit": ("bisect_good_commit", "BISECT_GOOD_COMMIT", "--good-commit"),
    "bad_commit": ("bisect_bad_commit", "BISECT_BAD_COMMIT", "--bad-commit"),
    "fail_confirm_retries": (
        "bisect_fail_confirm_retries",
        "BISECT_FAIL_CONFIRM_RETRIES",
        "--fail-confirm-retries",
    ),
    "trial_timeout": ("bisect_trial_timeout", "BISECT_TRIAL_TIMEOUT", "--trial-timeout-s"),
    "barrier_timeout": ("bisect_barrier_timeout", "BISECT_BARRIER_TIMEOUT", "--barrier-timeout-s"),
    "no_verify_good": ("bisect_no_verify_good", "BISECT_NO_VERIFY_GOOD", "--no-verify-good"),
    "no_verify_bad": ("bisect_no_verify_bad", "BISECT_NO_VERIFY_BAD", "--no-verify-bad"),
    "force_initial_build": (
        "bisect_force_initial_build",
        "BISECT_FORCE_INITIAL_BUILD",
        "--force-initial-build",
    ),
    "no_assume_built_head": (
        "bisect_no_assume_built_head",
        "BISECT_NO_ASSUME_BUILT_HEAD",
        "--no-assume-built-head",
    ),
    "native_check": ("bisect_native_check", "BISECT_NATIVE_CHECK", "--native-check"),
    "config_base_path": ("bisect_config_base_path", "BISECT_CONFIG_BASE_PATH", "--config-base-path"),
}

SCHEDULE_WORKFLOWS = (
    "schedule_nightly_test_a2.yaml",
    "schedule_nightly_test_a3.yaml",
    "schedule_nightly_test_a3_560t.yaml",
    "schedule_weekly_test_a2.yaml",
    "schedule_weekly_test_a3.yaml",
    "schedule_weekly_test_310p.yaml",
)

REUSABLE_WORKFLOWS = (
    "_e2e_nightly_single_node.yaml",
    "_e2e_nightly_single_node_560t.yaml",
    "_e2e_nightly_single_node_models.yaml",
    "_e2e_nightly_multi_node.yaml",
    "_e2e_nightly_multi_node_560t.yaml",
)


def _parser_script() -> str:
    """Extract the production comment-parser block instead of reimplementing it."""
    workflow = COMMAND_WORKFLOW.read_text(encoding="utf-8")
    start = workflow.index('          BRANCH="main"')
    end = workflow.index("          PR_SHA=$(gh api", start)
    return "#!/usr/bin/env bash\nset -euo pipefail\n" + dedent(workflow[start:end])


def _run_parser(tmp_path: Path, all_args: str) -> subprocess.CompletedProcess[str]:
    bash = _find_bash()
    if bash is None:
        pytest.skip("bash is required to exercise the slash-command parser")
    script = tmp_path / "parse-command.sh"
    script.write_text(_parser_script(), encoding="utf-8", newline="\n")
    output = tmp_path / "github-output.txt"
    env = dict(os.environ)
    env.update(
        {
            "ALL_ARGS": all_args,
            "GITHUB_OUTPUT": _shell_path(bash, output),
        }
    )
    return subprocess.run(
        [str(bash), _shell_path(bash, script)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _outputs(tmp_path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (tmp_path / "github-output.txt").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def test_comment_parser_emits_complete_json_contract(tmp_path: Path):
    result = _run_parser(
        tmp_path,
        "case-a --aop_enabled --good-commit abcdef1 --bad-commit 1234567 "
        "--fail-confirm-retries 3 --trial-timeout 120.5 --barrier-timeout 60 "
        "--no-verify-good --no-verify-bad --force-initial-build "
        "--no-assume-built-head --native-check since-build "
        "--config-base-path tests/e2e/models/configs",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    outputs = _outputs(tmp_path)
    assert outputs["test_cases"] == "case-a"
    assert outputs["aop_enabled"] == "true"
    assert json.loads(outputs["bisect_args_json"]) == {
        "good_commit": "abcdef1",
        "bad_commit": "1234567",
        "fail_confirm_retries": "3",
        "trial_timeout": "120.5",
        "barrier_timeout": "60",
        "no_verify_good": True,
        "no_verify_bad": True,
        "force_initial_build": True,
        "no_assume_built_head": True,
        "native_check": "since-build",
        "config_base_path": "tests/e2e/models/configs",
    }


def test_comment_parser_preserves_transport_defaults(tmp_path: Path):
    result = _run_parser(tmp_path, "case-a --aop_enabled")

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(_outputs(tmp_path)["bisect_args_json"])
    assert payload == {
        "good_commit": "",
        "bad_commit": "HEAD",
        "fail_confirm_retries": "",
        "trial_timeout": "",
        "barrier_timeout": "",
        "no_verify_good": False,
        "no_verify_bad": False,
        "force_initial_build": False,
        "no_assume_built_head": False,
        "native_check": "",
        "config_base_path": "",
    }


@pytest.mark.parametrize(
    ("all_args", "message"),
    [
        ("case-a --trial-timeout 1 --aop_enabled", "must appear after --aop_enabled"),
        ("case-a --aop_enabled --trial-timeout --no-verify-good", "requires a value"),
        ("case-a --aop_enabled --good-commit xyz", "7-40 character hexadecimal"),
        ("case-a --aop_enabled --fail-confirm-retries -1", "non-negative integer"),
        ("case-a --aop_enabled --trial-timeout 0", "positive numbers"),
        ("case-a --aop_enabled --native-check unsafe", "per-commit or since-build"),
        ("case-a --aop_enabled --config-base-path bad;path", "unsupported characters"),
    ],
)
def test_comment_parser_rejects_invalid_bisect_options(tmp_path: Path, all_args: str, message: str):
    result = _run_parser(tmp_path, all_args)

    assert result.returncode != 0
    assert message in result.stdout


def test_parameter_contract_is_present_at_every_transport_layer():
    workflows = REPO_ROOT / ".github/workflows"
    command_text = COMMAND_WORKFLOW.read_text(encoding="utf-8")
    aop_shell = (REPO_ROOT / "tests/e2e/nightly/scripts/aop_process.sh").read_text(encoding="utf-8")
    multi_shell = (REPO_ROOT / "tests/e2e/nightly/multi_node/scripts/run.sh").read_text(encoding="utf-8")
    auto_bisect = (REPO_ROOT / "tools/bisect/auto_bisect.py").read_text(encoding="utf-8")

    for json_key, (input_name, env_name, cli_name) in PARAMETERS.items():
        assert f'"{json_key}"' in command_text
        for workflow_name in SCHEDULE_WORKFLOWS:
            schedule = (workflows / workflow_name).read_text(encoding="utf-8")
            assert "bisect_args_json:" in schedule
            assert f".{json_key}" in schedule
            assert input_name in schedule
        for workflow_name in REUSABLE_WORKFLOWS:
            reusable = (workflows / workflow_name).read_text(encoding="utf-8")
            assert f"{input_name}:" in reusable
        assert env_name in aop_shell or json_key == "bad_commit"
        assert env_name in multi_shell
        assert cli_name in aop_shell
        assert cli_name in multi_shell
        assert f'"{cli_name}"' in auto_bisect

    for template_name in ("lws.yaml.jinja2", "lws_560t.yaml.jinja2"):
        template = (REPO_ROOT / "tests/e2e/nightly/multi_node/scripts" / template_name).read_text(encoding="utf-8")
        for input_name, env_name, _cli_name in PARAMETERS.values():
            assert template.count(env_name) >= 2
            assert template.count(input_name) >= 2
