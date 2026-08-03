import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _find_bash() -> Path | None:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
            if git_bash.is_file():
                return git_bash
        return None
    bash = shutil.which("bash")
    return Path(bash) if bash else None


def _shell_path(bash: Path, path: Path) -> str:
    if os.name != "nt":
        return str(path)
    return subprocess.check_output(
        [str(bash), "-lc", 'cygpath -u "$1"', "_", str(path)],
        text=True,
    ).strip()


def test_aop_shell_forwards_complete_bisect_contract(tmp_path: Path):
    """Run the real AOP shell entry and inspect its two Python invocations."""
    bash = _find_bash()
    if bash is None:
        pytest.skip("bash is required to exercise aop_process.sh")
    repo = Path(__file__).resolve().parents[4]
    capture = tmp_path / "python-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "printf 'CALL\\n' >> \"$AOP_CAPTURE\"\n"
        "printf 'ENV=%s|%s|%s\\n' \"$VLLM_WORKER_MULTIPROC_METHOD\" "
        '"$VLLM_USE_MODELSCOPE" "$VLLM_CI_RUNNER" >> "$AOP_CAPTURE"\n'
        'for arg in "$@"; do printf \'ARG=%s\\n\' "$arg" >> "$AOP_CAPTURE"; done\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    good_table = tmp_path / "nightly" / "good_table.csv"
    env_table = good_table.with_name("env_table.csv")
    good_table.parent.mkdir()
    good_table.write_text("placeholder\n", encoding="utf-8")
    shell_fake_bin = _shell_path(bash, fake_bin)
    shell_capture = _shell_path(bash, capture)
    shell_good_table = _shell_path(bash, good_table)
    shell_env_table = _shell_path(bash, env_table)
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{shell_fake_bin}:/usr/bin:/bin" if os.name == "nt" else f"{fake_bin}{os.pathsep}{env['PATH']}",
            "AOP_CAPTURE": shell_capture,
            "GOOD_TABLE": shell_good_table,
            "ENV_TABLE": shell_env_table,
        }
    )
    args = [
        "application",
        "1",
        "runner-a2",
        "",
        "case.yaml",
        "1 failed",
        "yaml failed",
        "single_node",
        "badbad1",
        "",
        "",
        "aop-case",
        "a2",
        "good123",
        "3",
        "120",
        "60",
        "true",
        "true",
        "true",
        "tests/e2e/nightly/single_node/configs",
    ]

    subprocess.run(
        [str(bash), "tests/e2e/nightly/scripts/aop_process.sh", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    calls = [block.splitlines() for block in capture.read_text(encoding="utf-8").split("CALL\n") if block]
    assert len(calls) == 2
    assert [line.removeprefix("ARG=") for line in calls[1] if line.startswith("ARG=")] == [
        "-m",
        "tools.bisect.auto_bisect",
        "--scene",
        "single_node",
        "--bad-commit",
        "badbad1",
        "--good-table",
        shell_good_table,
        "--config-yaml",
        "case.yaml",
        "--name",
        "aop-case",
        "--soc",
        "a2",
        "--env-table",
        shell_env_table,
        "--good-commit",
        "good123",
        "--fail-confirm-retries",
        "3",
        "--trial-timeout-s",
        "120",
        "--barrier-timeout-s",
        "60",
        "--no-verify-good",
        "--no-verify-bad",
        "--force-initial-build",
        "--native-check",
        "since-build",
        "--config-base-path",
        "tests/e2e/nightly/single_node/configs",
    ]


def test_aop_shell_selects_pytest_driven_replay_from_tests_path(tmp_path: Path):
    bash = _find_bash()
    if bash is None:
        pytest.skip("bash is required to exercise aop_process.sh")
    repo = Path(__file__).resolve().parents[4]
    capture = tmp_path / "python-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "printf 'CALL\\n' >> \"$AOP_CAPTURE\"\n"
        "printf 'ENV=%s|%s|%s\\n' \"$VLLM_WORKER_MULTIPROC_METHOD\" "
        '"$VLLM_USE_MODELSCOPE" "$VLLM_CI_RUNNER" >> "$AOP_CAPTURE"\n'
        'for arg in "$@"; do printf \'ARG=%s\\n\' "$arg" >> "$AOP_CAPTURE"; done\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = dict(os.environ)
    shell_fake_bin = _shell_path(bash, fake_bin)
    env.update(
        {
            "PATH": f"{shell_fake_bin}:/usr/bin:/bin" if os.name == "nt" else f"{fake_bin}{os.pathsep}{env['PATH']}",
            "AOP_CAPTURE": _shell_path(bash, capture),
            "GOOD_TABLE": "",
        }
    )
    test_path = "tests/e2e/weekly/single_node/models/test_qwen3_30b_acc.py"
    args = [
        "application",
        "1",
        "runner-a3",
        test_path,
        "",
        "1 failed",
        "",
        "single_node",
        "badbad1",
        "",
        "",
        "qwen3-30b-acc",
        "good123",
        "",
        "",
        "",
        "false",
        "false",
        "false",
        "",
    ]

    subprocess.run(
        [str(bash), "tests/e2e/nightly/scripts/aop_process.sh", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    calls = [block.splitlines() for block in capture.read_text(encoding="utf-8").split("CALL\n") if block]
    auto_bisect_args = [line.removeprefix("ARG=") for line in calls[-1] if line.startswith("ARG=")]
    assert "ENV=spawn|True|runner-a3" in calls[-1]
    assert auto_bisect_args[:2] == ["-m", "tools.bisect.auto_bisect"]
    assert auto_bisect_args[auto_bisect_args.index("--test-path") + 1] == test_path
    assert "--config-yaml" not in auto_bisect_args
    assert auto_bisect_args[auto_bisect_args.index("--name") + 1] == "qwen3-30b-acc"
