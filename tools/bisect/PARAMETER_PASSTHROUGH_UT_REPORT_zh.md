# AOP 二分参数透传专项 UT 报告

## 1. 被测功能与范围

本报告只验证 AOP 二分参数透传功能，不评价 good table、环境切换、候选提交算法、构建决策、verdict 或二分收敛逻辑。

被测链路：

```text
PR 评论 /nightly 或 /weekly
  -> pr_nightly_command.yml 从左到右解析 token
  -> 校验并生成 bisect_args_json
  -> schedule workflow 解包 JSON
  -> reusable workflow / Pod env / AOP Shell 逐层传递
  -> aop_process.sh 组装 auto_bisect argv
  -> tools.bisect.auto_bisect argparse 接收最终参数
```

用户可配置的 8 个参数：

| 评论参数 | JSON key | 最终 CLI |
|---|---|---|
| `--good-commit` | `good_commit` | `--good-commit` |
| `--bad-commit` | `bad_commit` | `--bad-commit` |
| `--fail-confirm-retries` | `fail_confirm_retries` | `--fail-confirm-retries` |
| `--trial-timeout` | `trial_timeout` | `--trial-timeout-s` |
| `--barrier-timeout` | `barrier_timeout` | `--barrier-timeout-s` |
| `--no-verify-good` | `no_verify_good` | `--no-verify-good` |
| `--no-verify-bad` | `no_verify_bad` | `--no-verify-bad` |
| `--force-initial-build` | `force_initial_build` | `--force-initial-build` |

系统内部管理且不允许用户在评论命令中配置：

- `--native-check`
- `--no-assume-built-head`
- `--config-base-path`

## 2. UT 设计思路

参数透传的主要风险不是计算错误，而是长链路中出现字段遗漏、重命名、默认值变化、字符串与 Boolean 类型变化、Shell 拆词，或者把内部参数错误暴露给用户。因此专项 UT 分为四层：

1. **评论解析层**：真实提取并执行 `pr_nightly_command.yml` 中的生产 Bash 解析脚本，检查完整输入、默认输入和非法输入。
2. **静态协议层**：逐字段检查 schedule、reusable workflow、LWS 模板、Shell 和 argparse，确认同一参数在所有传输层存在且映射一致。
3. **最终 CLI 层**：调用真实 `_parse_args`，确认 AOP 参数能转换为 `auto_bisect` 的最终字段和值。
4. **AOP Shell 执行层**：使用 Git for Windows Bash 真实运行 `aop_process.sh`，以 fake Python 捕获最终 argv，验证参数边界和值没有丢失。

## 3. 执行环境与命令

| 项目 | 值 |
|---|---|
| 执行日期 | 2026-08-03（Asia/Shanghai） |
| 仓库 | `C:\project\tmp\chendao\vllm-ascend` |
| 分支 | `codex/split-good-table-frequency_ut` |
| 被测 HEAD | `f4bcef6f` |
| 系统 | Windows 11（10.0.26200） |
| Python | 3.12.13 |
| pytest | 9.1.1 |

执行命令：

```powershell
python -m pytest -vv -p no:cacheprovider `
  --confcutdir=tests/ut/tools/bisect `
  --basetemp=.tmp-parameter-passthrough `
  tests/ut/tools/bisect/test_parameter_passthrough.py `
  tests/ut/tools/bisect/test_auto_bisect.py::test_parse_args_maps_extended_aop_parameters `
  tests/ut/tools/bisect/test_aop_shell_chain.py::test_aop_shell_forwards_complete_bisect_contract
```

执行结果：

```text
collected 14 items
14 passed in 8.50s
```

原始控制台日志保存在
[`test_evidence/parameter_passthrough_ut_console_20260803.txt`](./test_evidence/parameter_passthrough_ut_console_20260803.txt)。两张截图均由本次 pytest 原始 stdout 同源生成：第一张保留执行时间、仓库、分支、HEAD、命令、退出码和汇总，第二张展示 14 个 pytest 展开项的逐项结果；截图内容可由原始日志复核。

### 3.1 实际执行步骤

1. 进入 `_ut` 分支仓库并确认被测 HEAD 为 `f4bcef6f`。
2. 使用 `--confcutdir=tests/ut/tools/bisect` 隔离与本专项无关的顶层 NPU/Torch fixture。
3. 显式选择 `test_parameter_passthrough.py`，只运行评论解析、默认值、异常校验和跨层协议检查。
4. 单独选择 `test_parse_args_maps_extended_aop_parameters`，验证透传结束后的真实 argparse 结果。
5. 单独选择 `test_aop_shell_forwards_complete_bisect_contract`，通过 Git Bash 执行生产 `aop_process.sh`；脚本内部调用 fake Python，记录并断言最终 argv。
6. pytest 收集 14 个参数化展开项，逐项执行，最终返回码为 0。

执行命令、Python/pytest版本、收集数量和最终结果截图：

![参数透传专项UT执行命令与汇总](./test_evidence/parameter_passthrough_ut_execution_20260803.png)

14个用例逐项执行结果截图：

![参数透传专项UT逐项结果](./test_evidence/parameter_passthrough_ut_cases_20260803.png)

## 4. 逐项过程与结果

以下 14 项是 pytest 参数化展开后的实际执行项。每一项均内嵌本次执行产生的独立截图；截图中的 pytest node ID、进度、被测 HEAD 和退出码可与原始控制台日志交叉核对。

| # | 测试项 | 测试过程 | 预期结果 | 实际结果与独立截图 |
|---:|---|---|---|---|
| 1 | 完整评论参数生成 JSON | 执行生产评论解析脚本，输入 good/bad、重试、两个超时、两个端点开关和首次构建开关 | 8 个字段全部进入 `bisect_args_json`，字符串和 Boolean 类型正确 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_01_20260803.png" alt="UT 01 执行截图" width="520"> |
| 2 | 无可选参数保持默认值 | 输入 `case-a --aop_enabled` | good 为空、bad 为 `HEAD`、可选数字为空、三个 flag 为 `false` | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_02_20260803.png" alt="UT 02 执行截图" width="520"> |
| 3 | 二分参数位于 AOP 开关前 | 输入 `case-a --trial-timeout 1 --aop_enabled` | 拒绝并报告参数必须位于 `--aop_enabled` 后 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_03_20260803.png" alt="UT 03 执行截图" width="520"> |
| 4 | 值参数缺值 | 输入 `case-a --aop_enabled --trial-timeout --no-verify-good` | 拒绝并报告 `--trial-timeout requires a value` | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_04_20260803.png" alt="UT 04 执行截图" width="520"> |
| 5 | good commit 格式非法 | 输入 `--good-commit xyz` | 拒绝非 7～40 位十六进制 SHA | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_05_20260803.png" alt="UT 05 执行截图" width="520"> |
| 6 | retry 为负数 | 输入 `--fail-confirm-retries -1` | 拒绝非负整数以外的值 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_06_20260803.png" alt="UT 06 执行截图" width="520"> |
| 7 | timeout 为零 | 输入 `--trial-timeout 0` | 拒绝非正数 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_07_20260803.png" alt="UT 07 执行截图" width="520"> |
| 8 | 用户传入 `--native-check` | 在评论命令中传内部参数 | 按未知参数拒绝，不进入 JSON | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_08_20260803.png" alt="UT 08 执行截图" width="520"> |
| 9 | 用户传入 `--no-assume-built-head` | 在评论命令中传内部参数 | 按未知参数拒绝，不进入 JSON | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_09_20260803.png" alt="UT 09 执行截图" width="520"> |
| 10 | 用户传入 `--config-base-path` | 在评论命令中传内部参数 | 按未知参数拒绝，不进入 JSON | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_10_20260803.png" alt="UT 10 执行截图" width="520"> |
| 11 | 跨传输层字段契约 | 对 6 个 schedule、5 个 reusable workflow、LWS、Shell 和 argparse 逐字段扫描 | 8 个用户参数在每层均存在，JSON/input/env/CLI 命名映射一致 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_11_20260803.png" alt="UT 11 执行截图" width="520"> |
| 12 | 系统管理参数隔离 | 检查评论协议、JSON、Workflow 和 AOP Shell | 三个内部参数不向用户暴露；native 策略固定，配置路径只由系统传递 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_12_20260803.png" alt="UT 12 执行截图" width="520"> |
| 13 | `auto_bisect` 最终解析 | 直接向真实 `_parse_args` 传递完整 AOP CLI 参数 | 最终 Namespace 中所有参数的值和类型正确 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_13_20260803.png" alt="UT 13 执行截图" width="520"> |
| 14 | AOP Shell 完整透传 | 使用 Git Bash 真实运行 `aop_process.sh`，fake Python 捕获 update-table 与 auto-bisect argv | 用户8参数、good/env table、内部配置路径和固定 native 策略无丢失、无拆词 | PASS<br><img src="./test_evidence/parameter_passthrough_ut_case_14_20260803.png" alt="UT 14 执行截图" width="520"> |

### 4.1 UT 实现代码与逻辑审查

本节展示实际执行的 UT 关键代码，而不是测试结果的二次描述。完整源码位于：

- `tests/ut/tools/bisect/test_parameter_passthrough.py`
- `tests/ut/tools/bisect/test_auto_bisect.py`
- `tests/ut/tools/bisect/test_aop_shell_chain.py`

#### 4.1.1 生产解析器调用方式（用例 1～10 的公共前置逻辑）

```python
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
    env.update({"ALL_ARGS": all_args, "GITHUB_OUTPUT": _shell_path(bash, output)})
    return subprocess.run(
        [str(bash), _shell_path(bash, script)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
```

逻辑审查：UT 从生产工作流文件提取实际评论解析代码，设置真实的 `ALL_ARGS` 和 `GITHUB_OUTPUT` 后交给 Bash 执行。测试侧没有重新实现 token 解析或 JSON 组装，因此生产解析逻辑发生错误时，UT 会直接失败。

#### 4.1.2 完整参数与默认值（用例 1～2）

```python
def test_comment_parser_emits_complete_json_contract(tmp_path: Path):
    result = _run_parser(
        tmp_path,
        "case-a --aop_enabled --good-commit abcdef1 --bad-commit 1234567 "
        "--fail-confirm-retries 3 --trial-timeout 120.5 --barrier-timeout 60 "
        "--no-verify-good --no-verify-bad --force-initial-build",
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
    }


def test_comment_parser_preserves_transport_defaults(tmp_path: Path):
    result = _run_parser(tmp_path, "case-a --aop_enabled")
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(_outputs(tmp_path)["bisect_args_json"]) == {
        "good_commit": "",
        "bad_commit": "HEAD",
        "fail_confirm_retries": "",
        "trial_timeout": "",
        "barrier_timeout": "",
        "no_verify_good": False,
        "no_verify_bad": False,
        "force_initial_build": False,
    }
```

逻辑审查：用例 1 同时断言 case、AOP 开关以及 JSON 中全部 8 个字段和值/类型；用例 2 在不传可选参数时断言完整默认对象，能够发现字段遗漏、默认值漂移以及 Boolean 被错误编码成字符串的问题。

#### 4.1.3 非法参数和内部参数隔离（用例 3～10）

```python
@pytest.mark.parametrize(
    ("all_args", "message"),
    [
        ("case-a --trial-timeout 1 --aop_enabled", "must appear after --aop_enabled"),
        ("case-a --aop_enabled --trial-timeout --no-verify-good", "requires a value"),
        ("case-a --aop_enabled --good-commit xyz", "7-40 character hexadecimal"),
        ("case-a --aop_enabled --fail-confirm-retries -1", "non-negative integer"),
        ("case-a --aop_enabled --trial-timeout 0", "positive numbers"),
        ("case-a --aop_enabled --native-check since-build", "unknown option"),
        ("case-a --aop_enabled --no-assume-built-head", "unknown option"),
        (
            "case-a --aop_enabled --config-base-path "
            "tests/e2e/nightly/single_node/configs",
            "unknown option",
        ),
    ],
)
def test_comment_parser_rejects_invalid_bisect_options(
    tmp_path: Path, all_args: str, message: str
):
    result = _run_parser(tmp_path, all_args)
    assert result.returncode != 0
    assert message in result.stdout
```

逻辑审查：每个参数化项不仅要求失败，还断言对应错误原因，避免“因为其他异常碰巧失败”造成假通过。用例 8～10 明确证明三个系统管理参数不能从用户评论入口传入。

#### 4.1.4 跨层字段契约（用例 11）

```python
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
    template = (REPO_ROOT / "tests/e2e/nightly/multi_node/scripts" / template_name).read_text()
    for input_name, env_name, _cli_name in PARAMETERS.values():
        assert template.count(env_name) >= 2
        assert template.count(input_name) >= 2
```

逻辑审查：该用例逐个遍历 8 个参数，覆盖 6 个 schedule workflow、5 个 reusable workflow、两份 LWS 模板、single-node Shell、multi-node Shell 和 `auto_bisect` CLI。任一层字段遗漏或命名不一致都会触发断言。

#### 4.1.5 系统管理参数不对用户暴露（用例 12）

```python
assert "native_check" not in command_text
assert "--native-check" not in command_text
assert "no_assume_built_head" not in command_text
assert "--no-assume-built-head" not in command_text
assert "config_base_path" not in command_text
assert "--config-base-path" not in command_text

for workflow_name in (*SCHEDULE_WORKFLOWS, *REUSABLE_WORKFLOWS):
    workflow = (workflows / workflow_name).read_text(encoding="utf-8")
    assert "bisect_native_check" not in workflow
    assert "BISECT_NATIVE_CHECK" not in workflow
    assert "bisect_no_assume_built_head" not in workflow
    assert "BISECT_NO_ASSUME_BUILT_HEAD" not in workflow

assert "BISECT_CMD+=(--native-check since-build)" in aop_shell
assert "BISECT_EXTRA_ARGS+=(--native-check since-build)" in multi_shell
assert "--no-assume-built-head" not in aop_shell
assert "--no-assume-built-head" not in multi_shell
assert "--config-base-path" in aop_shell
assert "--config-base-path" in multi_shell
```

逻辑审查：既检查用户入口和 workflow 不存在内部参数，也检查 Shell 中的系统固定策略仍然存在，避免简单删除全部相关代码也让测试通过。

#### 4.1.6 最终 argparse 映射（用例 13）

```python
args = _parse_args(
    [
        "--scene", "single_node", "--config-yaml", "case.yaml",
        "--good-commit", "good", "--bad-commit", "bad",
        "--fail-confirm-retries", "3", "--trial-timeout-s", "120",
        "--barrier-timeout-s", "60", "--no-verify-good", "--no-verify-bad",
        "--force-initial-build", "--no-assume-built-head",
        "--native-check", "since-build", "--config-base-path", "custom/configs",
        "--env-table", "custom/env.csv",
    ]
)
assert args.good_commit == "good"
assert args.bad_commit == "bad"
assert args.fail_confirm_retries == 3
assert args.trial_timeout_s == 120
assert args.barrier_timeout_s == 60
assert args.no_verify_good is True
assert args.no_verify_bad is True
assert args.force_initial_build is True
```

逻辑审查：直接调用生产 `tools.bisect.auto_bisect._parse_args`，验证传输末端的字段名、数值转换和 flag 类型，而不是只搜索源码字符串。

#### 4.1.7 真实 AOP Shell argv（用例 14）

```python
subprocess.run(
    [bash, "tests/e2e/nightly/scripts/aop_process.sh", *args],
    cwd=repo,
    env=env,
    check=True,
    capture_output=True,
    text=True,
)

calls = [
    block.splitlines()
    for block in capture.read_text(encoding="utf-8").split("CALL\n")
    if block
]
assert len(calls) == 2
assert [line.removeprefix("ARG=") for line in calls[1]] == [
    "-m", "tools.bisect.auto_bisect",
    "--scene", "single_node",
    "--bad-commit", "badbad1",
    "--good-table", shell_good_table,
    "--config-yaml", "case.yaml",
    "--name", "aop-case",
    "--soc", "a2",
    "--env-table", shell_env_table,
    "--good-commit", "good123",
    "--fail-confirm-retries", "3",
    "--trial-timeout-s", "120",
    "--barrier-timeout-s", "60",
    "--no-verify-good", "--no-verify-bad", "--force-initial-build",
    "--native-check", "since-build",
    "--config-base-path", "tests/e2e/nightly/single_node/configs",
]
```

逻辑审查：执行的是生产 `aop_process.sh`。fake Python 不参与参数组装，只把 Shell 最终调用的每个 argv 原样写入文件；UT 对完整 argv 列表做顺序和值的精确相等断言，因此可以发现参数丢失、多传、错序或 Shell 拆词。

## 5. 结论

本次参数透传专项 UT 共 14 项，14 项全部通过。仓库内可控链路已经验证：

- 评论层能正确解析、校验和拒绝非法参数；
- 不传新增参数时保持约定默认值；
- 8 个用户参数能进入 JSON 并在所有传输层保持字段一致；
- 3 个系统管理参数不会暴露给评论用户；
- AOP Shell 能把参数组装为 `auto_bisect` 最终 CLI；
- 底层 argparse 能接收正确的值与类型。

## 6. 尚未覆盖的边界

以下内容不应写成“UT 已验证”，需要 GitHub Actions 或 NPU 环境验证：

- GitHub 上真实 slash-command 事件到 `workflow_dispatch` 的网络调用；
- Actions 表达式 `fromJSON` 在真实 runner 中的求值；
- 参数进入真实 single-node Pod 和 multi-node LWS Pod 后的环境变量值；
- 真实 NPU case 失败后触发 AOP 并执行二分的物理闭环。

这些属于集成/E2E边界，不影响本报告对仓库内参数解析和透传协议的 UT 结论。
