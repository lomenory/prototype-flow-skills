# Strict Regression

只有用户明确要求以下任一证据时才进入本节：自动化回归、可重复测试报告、完整 `TEST-*`、Console/Page Error、请求失败、硬规则测量、像素 Diff、CI 或无人值守执行。

Strict Regression 使用 `scripts/verify.py` 和 Python Playwright。脚本在生命周期内启动受限的随机端口 loopback HTTP 服务，与默认 Interactive Demo 使用相同 transport；`file://` 只保留给人工打开和独立可携带性检查。脚本不安装依赖，不访问网络准备运行时；环境不可用时写 `verificationProfile: strict_regression` 与 `verificationProfileStatus: unavailable`，同时保留兼容的顶层 `status: degraded` 和退出码 `2`，且不覆盖已经存在的 Interactive Demo 结果。退出码 `2` 不表示静态契约或 Interactive Demo 失败。

Strict Regression 必须把实际 `consoleErrors`、`consoleWarnings`、`pageErrors`、`requestFailures`、导航 transport、Hard Rule 状态和截图路径写入 `validation-report.json`。Console Error、Page Error、请求失败及任何适用且必需的 Hard Rule `not_run` 都阻断完整通过；Console Warning 单独记录，默认不阻断。

### Environment and warm session

```bash
python3 scripts/verify.py --check-env --report-json verification-env.json
```

预计运行两次或更多 Strict Regression 时，Codex 桌面持久终端以前台方式启动，任务结束时发送 Ctrl-C：

```bash
python3 scripts/browser-session.py serve
```

普通终端可显式管理后台会话：

```bash
python3 scripts/browser-session.py start
python3 scripts/browser-session.py status
python3 scripts/browser-session.py stop
```

Tier 1/2 默认 `--browser-session reuse`；Tier 3 默认 `off`。`--browser-session auto` 可自动创建后台会话，`--show` 始终使用独立可见浏览器。会话复用只证明浏览器进程被复用，不证明页面验证通过。

### Commands

项目级 DESIGN.md：

```bash
python3 scripts/validate-design-systems.py DESIGN.md --report-json design-system-report.json
```

Product Contract：

```bash
python3 scripts/validate-product-contract.py prototype-contract.json --html prototype.html --report-json product-contract-report.json
python3 scripts/verify.py prototype.html --profile product-contract --contract prototype-contract.json --report-json validation-report.json
```

非 Product Contract 的多步交互：

```bash
python3 scripts/validate-experience-checks.py experience-checks.json --html prototype.html --report-json experience-checks-report.json
python3 scripts/verify.py prototype.html \
  --tier tier_2_layout_or_interaction \
  --changed-aspects interaction \
  --experience-checks experience-checks.json \
  --report-json validation-report.json
```

Design Guidance：

```bash
python3 scripts/validate-design-guidance.py design-guidance.json --report-json design-guidance-report.json
python3 scripts/verify.py prototype.html --tier tier_3_full_delivery --guidance design-guidance.json --report-json validation-report.json
```

与 Product Contract 组合时，同时传入 `--profile product-contract --contract prototype-contract.json --guidance design-guidance.json`。`--experience-checks` 与 Product Contract 互斥，避免两套交互真相源漂移。

外部设计像素 Diff：

```bash
python3 scripts/validate-design-reference.py design-reference.json --html prototype.html --report-json design-reference-report.json
python3 scripts/verify.py prototype.html \
  --tier tier_3_full_delivery \
  --design-reference design-reference.json \
  --visual-diff-channel-threshold 16 \
  --visual-diff-max-mismatch-ratio 0.01 \
  --report-json validation-report.json
```

默认文件夹资源与分享预检（入口放在 Demo 根目录）：

```bash
python3 scripts/validate-portability.py demo/prototype.html --report-json portability-report.json
python3 scripts/verify.py demo/prototype.html --tier tier_3_full_delivery --portability --report-json validation-report.json
```

Tier 1 严格回归：

```bash
python3 scripts/verify.py prototype.html \
  --tier tier_1_local_ui_patch \
  --changed-aspects spacing,local-layout \
  --target-selector '#settings-card' \
  --viewports 1440x900 \
  --previous-report validation-report.json \
  --report-json validation-report.json
```

Product Contract 静态文案 follow-up 仍可只运行依赖无关检查：

```bash
python3 scripts/verify.py prototype.html \
  --profile product-contract \
  --contract prototype-contract.json \
  --tier tier_0_text_copy_only \
  --changed-aspects copy \
  --semantic-impact none \
  --expected-copy '更新后的文案' \
  --report-json validation-report.json
```

Tier 1/2 Strict Regression 默认 `--browser-policy fast`；Tier 3 默认 `full`。可用 `--browser-executable` 指定浏览器，并用 `--launch-timeout-ms`、`--navigation-timeout-ms` 和 `--wall-timeout-ms` 控制截止时间。报告必须写 `verificationProfile: strict_regression`，并分别记录静态、启动/连接、导航、稳定、检查、截图、清理和总耗时。
