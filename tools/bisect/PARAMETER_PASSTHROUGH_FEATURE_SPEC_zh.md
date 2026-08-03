# AOP 二分参数透传功能特性与技术规格

## 1. 功能简介

AOP 自动二分原先只能按照固定默认值运行。出现大模型启动较慢、用例存在抖动、已知 good/bad 区间、跨 native 变更或多节点同步较慢时，使用者无法从 PR 评论调整二分策略，只能修改 workflow 或进入运行环境手工重跑。

参数透传功能允许授权用户直接在 `/nightly` 或 `/weekly` 评论命令中配置关键二分行为，并将配置安全、无损地传递到最终的 `tools.bisect.auto_bisect` 进程。

## 2. 用户价值

- 已知回归范围时可直接指定 good/bad，缩短搜索范围。
- 可按用例稳定性调整 FAIL 确认次数，降低 flaky 误判。
- 可为大模型或多节点场景调整 trial/barrier 超时。
- 可在可信场景跳过端点验证，减少额外运行轮次。
- 可按需强制首次构建；native 检测策略由 AOP 内部统一管理。
- 未提供参数时保持原行为，不影响现有命令。

## 3. 支持范围

命令格式：

```text
/<nightly|weekly> <case|all> --aop_enabled [bisect options]
```

示例：

```text
/nightly DeepSeek-R1 --aop_enabled \
  --good-commit 0123456 \
  --bad-commit 89abcde \
  --fail-confirm-retries 3 \
  --trial-timeout 14400
```

支持 nightly/weekly 的 A2、A3、A3-560T、310P 调度入口，以及下游支持 AOP 的普通单节点和多节点 reusable workflow。model accuracy 使用独立工作流，不属于本特性范围。

## 4. 功能列表

| 特性 | 评论参数 | 最终默认值/行为 | 指定参数后的效果 |
|---|---|---|---|
| 指定 good 端点 | `--good-commit SHA` | 空；从 good table 查询 | 跳过 good table 查询和 AOP commit-age gate |
| 指定 bad 端点 | `--bad-commit SHA\|HEAD` | `HEAD`（工具层可由 `VLLM_ASCEND_REF` 提供） | 使用指定提交替换默认失败端点 |
| FAIL 重试 | `--fail-confirm-retries N` | `1` | FAIL 后额外运行 N 次，出现非 FAIL 则按 flaky SKIP |
| 单轮超时 | `--trial-timeout SEC` | `7200` 秒 | 设置每个候选 pytest 的超时时间 |
| 多节点屏障超时 | `--barrier-timeout SEC` | `3600` 秒 | 设置 leader 等待各节点 ready 的时间 |
| 跳过 good 验证 | `--no-verify-good` | `false`；默认复跑 good 端点 | 跳过搜索前的 good 端点验证 |
| 跳过 bad 验证 | `--no-verify-bad` | `false`；默认复跑 bad 端点 | 跳过搜索前的 bad 端点验证 |
| 首轮强制构建 | `--force-initial-build` | `false`；默认复用容器初始 build baseline | 首轮不复用初始构建，执行 clean rebuild |

以下能力由系统内部管理，不作为评论命令参数暴露：

- AOP 单节点和多节点固定使用 `native-check=since-build`，避免二分跳跃复用过期 `.so`；
- AOP 默认信任 Nightly 容器 HEAD 已构建；用户需要重建时只使用 `--force-initial-build`；
- `config-base-path` 仅由普通 nightly/weekly 和多节点 Workflow 在内部传给 runner，不属于用户功能参数；runner 使用它选择与原失败任务一致的测试入口。

底层 `auto_bisect.py` CLI 仍保留这些选项，仅用于 Workflow 内部调用、本地执行和底层策略测试。

## 5. 使用约束

### 5.1 AOP 父开关

所有二分参数必须位于 `--aop_enabled` 之后：

```text
# 正确
/nightly case-a --aop_enabled --trial-timeout 14400

# 错误：未启用 AOP
/nightly case-a --trial-timeout 14400

# 错误：参数位于父开关之前
/nightly case-a --trial-timeout 14400 --aop_enabled
```

`--aop_enabled` 本身必须位于至少一个 case 之后。

### 5.2 输入校验

评论解析阶段会拒绝：

- 参数缺值；
- 未知 `--option`；
- 非 7～40 位十六进制 good SHA；
- 既不是 `HEAD` 也不是合法 SHA 的 bad；
- 非负整数之外的 retry；
- 非正数 timeout；
- `per-commit`、`since-build` 之外的 native mode；
- config path 中不安全的字符。

校验失败时命令退出，不触发下游 workflow。

## 6. 默认与兼容行为

| 参数 | 评论层默认 | auto-bisect 生效默认 |
|---|---|---|
| good commit | 空 | 查询 good table |
| bad commit | `HEAD` | `VLLM_ASCEND_REF`，否则 `HEAD` |
| fail confirm retries | 空 | `1` |
| trial timeout | 空 | `7200` 秒 |
| barrier timeout | 空 | `3600` 秒 |
| 四个 Boolean flag | `false` | 不添加对应 CLI flag |

可选值在上游保持空值，避免 workflow 重复实现工具默认值；最终默认值由 `auto_bisect.py` 统一管理。`bad_commit` 是例外，评论命令明确使用 `HEAD` 作为 dispatch 默认值。

## 7. 参数传递路径

```text
PR comment tokens
  -> pr_nightly_command.yml
       parse + validate
       build bisect_args_json
  -> gh workflow run -f bisect_args_json=...
  -> schedule_*.yaml
       fromJSON(...)
       map to bisect_* reusable inputs
  -> single-node
       workflow inputs -> aop_process.sh $9/$14-$21
       -> BISECT_CMD array -> auto_bisect argv
  -> multi-node
       workflow inputs -> jinja2 -D
       -> Kubernetes BISECT_* env on leader and workers
       -> build_bisect_extra_args array -> auto_bisect argv
```

## 8. 可观察性

PR 命令解析步骤将各字段和 `bisect_args_json` 写入 job outputs。下游 workflow inputs、Pod 环境变量和 AOP 最终命令使用同一套 `bisect_*`/`BISECT_*` 命名，方便逐层定位参数丢失。

AOP Shell 会在执行前打印最终 `python -m tools.bisect.auto_bisect ...` 命令。二分报告中的 trial、超时、端点行为可用于确认参数实际生效。

## 9. 已知边界

- 评论命令按空白拆分 token，不支持带空格的参数值。
- good/bad 评论参数只接受 SHA 或 `HEAD`，不接受分支名和 PR 号；直接调用 `auto_bisect.py` 时可使用更宽泛的 Git ref。
- 参数透传不改变 AOP classify、good table 或环境回放语义。
- workflow 文件由默认分支执行，PR 中仅修改 workflow 时，需要合入默认分支后评论命令才能使用新逻辑。

## 10. 技术规格目标

参数协议必须满足：

1. 8 个用户控制参数可从 `/nightly`、`/weekly` 无损到达最终进程。
2. 评论层拒绝非法输入，未校验数据不得进入 workflow dispatch。
3. workflow dispatch 只占用一个可选二分 input。
4. 单节点和多节点使用相同语义与默认值。
5. Boolean 保持 Boolean 语义，字符串不发生 word splitting、glob 展开或 YAML 注入。
6. 未传可选值时，由最终 CLI 使用自身默认值。

## 11. 参数数据模型

| JSON key | 评论参数 | JSON 类型 | 空值 | 约束 |
|---|---|---|---|---|
| `good_commit` | `--good-commit` | string | `""` | `^[0-9a-fA-F]{7,40}$` |
| `bad_commit` | `--bad-commit` | string | 默认 `HEAD` | `HEAD` 或合法 SHA |
| `fail_confirm_retries` | `--fail-confirm-retries` | string | `""` | `^[0-9]+$` |
| `trial_timeout` | `--trial-timeout` | string | `""` | 正整数或正小数 |
| `barrier_timeout` | `--barrier-timeout` | string | `""` | 正整数或正小数 |
| `no_verify_good` | `--no-verify-good` | boolean | `false` | flag |
| `no_verify_bad` | `--no-verify-bad` | boolean | `false` | flag |
| `force_initial_build` | `--force-initial-build` | boolean | `false` | flag |

数值有意编码为 string，因为 workflow inputs 和 Shell 环境变量均以字符串传递；最终由 argparse 转成 `int` 或 `float`。三个 flag 必须编码成未加引号的 JSON Boolean。

## 12. JSON 协议

默认 payload：

```json
{
  "good_commit": "",
  "bad_commit": "HEAD",
  "fail_confirm_retries": "",
  "trial_timeout": "",
  "barrier_timeout": "",
  "no_verify_good": false,
  "no_verify_bad": false,
  "force_initial_build": false
}
```

该对象整体作为唯一 workflow dispatch input：

```text
bisect_args_json
```

调度层读取示例：

```yaml
${{ fromJSON(inputs.bisect_args_json || '{}').good_commit || '' }}
${{ fromJSON(inputs.bisect_args_json || '{}').bad_commit || 'HEAD' }}
${{ fromJSON(inputs.bisect_args_json || '{}').no_verify_good || false }}
```

使用单个 JSON input，可以避免新增参数线性消耗 `workflow_dispatch.inputs` 数量。

## 13. 评论解析状态机

解析器从左到右处理 token，并关闭 pathname expansion：

```bash
set -f
for WORD in $ALL_ARGS; do ...; done
```

值参数进入 pending 状态。下一 token 以 `--` 开头或输入结束时，报告 `<option> requires a value`；flag 直接设置 Boolean；未知 `--option` 必须失败。

顺序不变量：

- 至少一个 case 先于 `--aop_enabled`；
- 任一 bisect option 后于 `--aop_enabled`；
- 普通非 option token 累加到逗号分隔的 `TEST_CASES`。

## 14. 分层字段映射

| JSON key | reusable input | Pod/Shell 名称 | auto-bisect argv |
|---|---|---|---|
| `good_commit` | `bisect_good_commit` | `BISECT_GOOD_COMMIT` / `$14` | `--good-commit` |
| `bad_commit` | `bisect_bad_commit` | `BISECT_BAD_COMMIT` / `$9` | `--bad-commit` |
| `fail_confirm_retries` | `bisect_fail_confirm_retries` | `BISECT_FAIL_CONFIRM_RETRIES` / `$15` | `--fail-confirm-retries` |
| `trial_timeout` | `bisect_trial_timeout` | `BISECT_TRIAL_TIMEOUT` / `$16` | `--trial-timeout-s` |
| `barrier_timeout` | `bisect_barrier_timeout` | `BISECT_BARRIER_TIMEOUT` / `$17` | `--barrier-timeout-s` |
| `no_verify_good` | `bisect_no_verify_good` | `BISECT_NO_VERIFY_GOOD` / `$18` | `--no-verify-good` |
| `no_verify_bad` | `bisect_no_verify_bad` | `BISECT_NO_VERIFY_BAD` / `$19` | `--no-verify-bad` |
| `force_initial_build` | `bisect_force_initial_build` | `BISECT_FORCE_INITIAL_BUILD` / `$20` | `--force-initial-build` |

用户参数的 `$N` 仅适用于单节点 `aop_process.sh`；多节点全部使用 `BISECT_*` 环境变量。内部 `config-base-path` 不属于 JSON 协议，由 schedule workflow 直接设置 reusable input，单节点使用 `$21`，多节点使用 `BISECT_CONFIG_BASE_PATH`。

## 15. 调度入口矩阵

相同 JSON payload 必须传给：

| 命令/平台 | schedule workflow |
|---|---|
| nightly A2 | `schedule_nightly_test_a2.yaml` |
| nightly A3 | `schedule_nightly_test_a3.yaml` |
| nightly A3-560T | `schedule_nightly_test_a3_560t.yaml` |
| weekly A2 | `schedule_weekly_test_a2.yaml` |
| weekly A3 | `schedule_weekly_test_a3.yaml` |
| weekly 310P | `schedule_weekly_test_310p.yaml` |

每个 schedule workflow 只接收 `bisect_args_json`，解包后转发给它调用的 `_e2e_nightly_*` workflow。所有 matrix/job 分支使用相同字段表达式。

## 16. 单节点协议

`aop_process.sh` 固定位置参数：

| 位置 | 含义 |
|---|---|
| `$1`～`$8` | failure metadata、tests/config、scene |
| `$9` | bad commit |
| `$10`～`$13` | num nodes、coord dir、case name、SoC |
| `$14`～`$20` | good commit 及其余 6 个用户可选控制值 |
| `$21` | Workflow 内部配置根目录 |

Shell 必须使用数组：

```bash
BISECT_CMD=(python -m tools.bisect.auto_bisect ...)
[ -n "$VALUE" ] && BISECT_CMD+=(--option "$VALUE")
[ "$FLAG" = "true" ] && BISECT_CMD+=(--flag)
"${BISECT_CMD[@]}"
```

禁止将字符串拼接后交给 `eval`，禁止依赖未引用变量展开。

## 17. 多节点协议

```text
reusable inputs
  -> workflow job env
  -> jinja2 -D bisect_*=...
  -> lws.yaml.jinja2 tojson
  -> leader/worker BISECT_* env
  -> build_bisect_extra_args()
  -> auto_bisect argv
```

要求：

- leader 和所有 worker 的 8 个用户参数一致；
- Jinja2 值使用 `tojson`，保证 YAML 字符串安全；
- worker 使用与 leader 相同的 `build_bisect_extra_args()`；
- Boolean 仅在字符串严格等于 `true` 时生成 flag；
- 空字符串不生成对应 CLI option。

## 18. 默认值归属

上游只提供 transport default：bad 为 `HEAD`，Boolean 为 `false`，其他可选字段为空。最终行为默认值由 argparse 定义：

```text
fail_confirm_retries = 1
trial_timeout_s      = 7200.0
barrier_timeout_s    = 3600.0
verify_good          = true
verify_bad           = true
force_initial_build  = false
```

AOP 的内部 native rebuild 策略不属于 transport payload，单节点 `aop_process.sh` 和多节点 `run.sh` 均固定向底层 CLI 添加：

```text
--native-check since-build
```

修改默认值时优先修改 `auto_bisect.py` 并同步本文档，不在多个 schedule workflow 中复制非必要默认值。

## 19. 安全与错误行为

安全要求：

- commit 只允许十六进制 SHA，bad 额外允许 `HEAD`；
- config path 使用白名单字符，禁止空格、引号、反引号、变量替换和 Shell 控制符；
- dispatch 通过环境变量向 `gh workflow run` 传 JSON；
- Jinja2 到 Kubernetes YAML 使用 JSON quoting；
- Bash 数组保持参数边界，评论解析关闭 glob；
- 未知 option 必须 fail closed。

| 场景 | 预期结果 |
|---|---|
| option 位于 `--aop_enabled` 前 | 解析失败，不 dispatch |
| 值参数缺值 | 解析失败并指出 option |
| 非法 SHA、数字、mode 或 path | 解析失败，不 dispatch |
| JSON 字段缺失 | 使用空值、false 或 HEAD transport default |
| 空可选字符串 | 不生成 CLI option |
| Boolean false | 不生成 flag |
| Boolean true | 生成一次对应 flag |

## 20. 验收标准

功能验收：

- 默认命令与改动前行为一致；
- 每个值参数可单独透传并被 argparse 解析；
- 每个 flag 可单独启用，未启用时不出现；
- 8 个用户参数组合可通过 single-node 和 multi-node 路径，3 个系统管理参数保持内部控制；
- 显式 good 能跳过 good table age gate；
- bad 不会被下游硬编码 `HEAD` 覆盖。

自动化验收：

- `test_parse_args_maps_extended_aop_parameters`：最终 argparse 映射；
- `test_aop_shell_forwards_complete_bisect_contract`：真实执行 AOP Shell 并断言完整 argv；
- `test_aop_cli_to_first_bad_report_full_chain`：最终 CLI、真实 Git/CSV 到 first-bad report；
- workflow smoke：comment JSON、schedule `fromJSON` 和 multi-node Pod env，由 GitHub Actions 集成测试承担。

## 21. 变更控制

新增参数必须同步修改：

1. 评论解析、校验和 JSON schema；
2. 六个 schedule workflow 的解包表达式；
3. 相关 reusable workflow inputs；
4. 单节点 AOP 位置参数和数组；
5. multi-node workflow Jinja2 参数；
6. 两份 LWS 模板的 leader/worker env；
7. `run.sh` 的 `build_bisect_extra_args()`；
8. `auto_bisect.py` argparse；
9. 参数 UT 和 AOP Shell 全链路 UT；
10. 本文档。

任一层遗漏均视为协议不兼容。

## 22. UT 设计、过程与结果

### 22.1 测试思路

参数透传的主要风险不是单个函数计算错误，而是长链路中某一层字段遗漏、改名、类型变化或 Shell 参数边界丢失。因此测试分为三层：

1. **源解析行为层**：不重新实现解析器，直接从 `pr_nightly_command.yml` 提取生产 Bash 代码并执行，验证 JSON 和错误行为。
2. **静态协议一致性层**：使用唯一参数映射表，逐项检查 comment、schedule、reusable workflow、Jinja2、Pod env、Shell 和 argparse。
3. **下游全链路层**：复用已有 AOP Shell 与 first-bad 全链路 UT，验证最终 argv 和二分报告。

这种组合既覆盖真实行为，也能在新增平台或复制 workflow 时快速发现漏传字段。

### 22.2 行为测试过程

`test_parameter_passthrough.py` 会：

1. 读取 `.github/workflows/pr_nightly_command.yml`。
2. 从 `BRANCH="main"` 到获取 PR SHA 之前提取生产解析代码。
3. 使用 Git Bash（Windows）或 Bash（Linux）执行该代码。
4. 通过 `ALL_ARGS` 注入评论 token，通过临时 `GITHUB_OUTPUT` 读取真实 outputs。
5. 将 `bisect_args_json` 反序列化，断言字符串、数字字符串和 Boolean 类型。

完整参数场景同时传入 8 个用户参数，期望 JSON 为：

```json
{
  "good_commit": "abcdef1",
  "bad_commit": "1234567",
  "fail_confirm_retries": "3",
  "trial_timeout": "120.5",
  "barrier_timeout": "60",
  "no_verify_good": true,
  "no_verify_bad": true,
  "force_initial_build": true
}
```

默认场景只传 `case-a --aop_enabled`，验证 bad 为 `HEAD`、三个 flag 为 `false`、其他可选字段为空。

非法输入采用参数化测试，覆盖：父开关顺序错误、缺值、非法 SHA、负数 retry、零 timeout，以及用户传入系统管理的 `--native-check`、`--no-assume-built-head`、`--config-base-path` 时按未知参数拒绝。

### 22.3 协议一致性过程

`test_parameter_contract_is_present_at_every_transport_layer` 对每个参数检查：

- comment JSON key 存在；
- 6 个 schedule workflow 接收 `bisect_args_json`，读取对应 key 并转发 reusable input；
- 5 个 reusable workflow 声明对应 input；
- `aop_process.sh` 和 `multi_node/scripts/run.sh` 包含环境变量及最终 CLI；
- `auto_bisect.py` 声明最终 argparse option；
- 两份 LWS 模板在 leader 和 worker 中均包含相同 Jinja2 字段和 `BISECT_*` 环境变量。

### 22.4 与已有全链路测试的衔接

- `test_aop_shell_forwards_complete_bisect_contract`：真实执行完整 `aop_process.sh`，使用 fake Python 捕获最终 argv，验证参数没有拆词或丢失。
- `test_aop_cli_to_first_bad_report_full_chain`：创建真实临时 Git 历史、good/env CSV，从最终 CLI 执行到 first-bad `report.json`。
- `test_parse_args_maps_extended_aop_parameters`：验证最终 argparse 类型转换和 flag。

### 22.5 执行命令

```powershell
python -m pytest -q `
  --confcutdir=tests/ut/tools/bisect `
  --basetemp .tmp-pytest `
  tests/ut/tools/bisect
```

### 22.6 结果

参数透传专项包含 12 个用例：

- 完整 JSON：1 个；
- 默认 JSON：1 个；
- 非法输入：8 个；
- 全层协议一致性：1 个；
- 系统管理参数不对用户暴露、AOP 固定 native 策略且配置路径仅内部传递：1 个。

完整 bisect UT 执行结果：

```text
........................................................................ [ 71%]
.............................                                            [100%]
101 passed in 10.93s
```

专项文件 Ruff 检查通过，Ruff format 确认已格式化，`git diff --check` 无空白错误。全部测试无 skip。

### 22.7 未覆盖边界

- GitHub 服务端真实 `repository_dispatch/workflow_dispatch` 行为；
- GitHub expression 在服务端的最终求值；
- Kubernetes API 接收渲染 YAML 后的真实 Pod 环境；
- 多节点 NPU 集群的并发时序。

这些场景属于集成测试或 NPU E2E；UT 通过源码行为执行和跨层契约检查覆盖仓库内可确定的参数透传逻辑。

## 23. pytest-driven 单节点二分重放

### 23.1 适用场景

nightly/weekly 单节点矩阵允许两种用例定义：

```yaml
# YAML-driven
- name: qwen3-32b-int8
  config_file_path: Qwen3-32B-Int8.yaml

# pytest-driven
- name: qwen3-30b-acc
  tests: tests/e2e/weekly/single_node/models/test_qwen3_30b_acc.py
```

重放模式由 Workflow 已解析出的用例字段自动决定，不增加用户评论参数，也不进入 `bisect_args_json`：

```text
config_file_path 非空、tests 为空 -> --config-yaml，YAML-driven
tests 非空、config_file_path 为空 -> --test-path，pytest-driven
两者均空或同时非空               -> AOP Shell 明确失败
```

用户命令保持不变：

```text
/nightly qwen3-30b-acc --aop_enabled
```

用户不能在评论中传入 `--test-path`。该选项与 `--config-base-path`、`--native-check` 一样，仅用于 Workflow/AOP 到底层二分工具的内部调用。

### 23.2 内部传递链路

```text
nightly/weekly test_config.tests
  -> reusable single-node workflow inputs.tests
  -> aop_process.sh 的 $4 TESTS
  -> auto_bisect --test-path
  -> BisectInput.test_path
  -> SingleNodeRunner._test_command
  -> python -m pytest -sv <原始 tests 路径>
```

YAML-driven 链路保持原样：

```text
test_config.config_file_path
  -> aop_process.sh 的 $5 CONFIG
  -> auto_bisect --config-yaml
  -> CONFIG_YAML_PATH / 原 YAML 测试入口
```

### 23.3 约束与安全检查

- `--config-yaml` 与 `--test-path` 在 argparse 中互斥且必须恰好提供一个；
- `--test-path` 仅允许 single-node，multi-node 仍必须使用 YAML；
- 路径必须是仓库相对路径，解析后位于 `tests/e2e/`；允许 `.py` 文件、测试目录和 pytest node ID；
- `SingleNodeRunner` 在 pytest-driven 模式不设置 `CONFIG_YAML_PATH`，并恢复原工作流的 `spawn`、ModelScope、`LD_LIBRARY_PATH` 和 `test_fused_moe.py` ignore 规则；
- `aop_process.sh` 从工作流已有的 runner 输入设置 `VLLM_CI_RUNNER`，不增加用户参数；
- AOP Shell 对两种来源同时存在或同时为空均立即报错，避免重放错误入口；
- pytest-driven 路径是系统从用例矩阵取得的，不属于 8 个用户参数。

### 23.4 UT 验证点

- argparse 接受合法内部 `--test-path`；
- argparse 拒绝无重放来源及同时提供两个来源；
- 接受 `tests/e2e/` 下的 `.py` 文件、测试目录和 pytest node ID；拒绝父目录穿越、绝对路径、非 `tests/e2e/` 路径和非测试目标；
- multi-node 拒绝 pytest-driven 重放；
- `SingleNodeRunner` 精确生成原始 pytest 命令、环境和 ignore 规则，且不设置 `CONFIG_YAML_PATH`；
- 真实执行 `aop_process.sh`，确认最终 argv 包含 `--test-path`、不包含 `--config-yaml`，并继承 `VLLM_CI_RUNNER`；
- 评论解析器和 `bisect_args_json` 中不存在 `test_path`，证明用户接口未扩大。
