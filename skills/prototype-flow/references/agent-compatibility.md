# Agent 兼容

核心入口使用 Agent Skills 的 `SKILL.md`、`name`、`description` 和相对资源路径。宿主负责读取说明并选择工具，Python CLI 负责文件状态；无需调用 Codex API。`agents/openai.yaml` 可保留，其他宿主不需要解释它。

## 安装与调用

先取得本包的完整目录。在仓库根运行以下命令之一，安装当前源码副本：

```bash
# Claude Code，当前项目
python3 -B skills/prototype-flow/scripts/install.py --dest .claude/skills
# Cursor，当前项目
python3 -B skills/prototype-flow/scripts/install.py --dest .cursor/skills
# Codex 或使用共享目录的 Agent，当前项目
python3 -B skills/prototype-flow/scripts/install.py --dest .agents/skills
```

个人安装可将目标改为 `~/.claude/skills`、`~/.cursor/skills` 或 `~/.agents/skills`。其他目录使用 `--dest <skills-root>`。命令只复制主 Skill，保留完整的 scripts、references、schemas 和预构建工作台，不下载依赖、不改宿主配置。同名副本完全相同时复用，不同时返回冲突并保留原目录；`--check` 只读比较，不创建目录。

安装后读取返回的 `<path>/SKILL.md`，可直接向 Agent 提供：

> 读取 `<path>/SKILL.md`，按其中流程将 `<project-dir>` 的现有 PRD 接入工作台并拆分需求，保存第一版；本次先不生成 Demo。

原生 Skill 自动发现由宿主实现。Claude Code 支持 `.claude/skills`，Cursor 支持 `.cursor/skills` 和 `.agents/skills`，Codex 使用 `.agents/skills`。通用 Agent 可直接按绝对路径读取入口与引用，不要求斜杠命令、选择器或插件。目录依据：[Claude Code](https://code.claude.com/docs/en/skills)、[Cursor](https://cursor.com/docs/skills)、[OpenAI Docs](https://learn.chatgpt.com/docs/build-skills)；格式依据：[Agent Skills](https://agentskills.io/specification)。

依赖会按 [依赖安装](dependencies.md) 在相应阶段准备。自定义目录需要在后续命令中保持 `PROTOTYPE_FLOW_SKILLS_DIR=<skills-root>`，或用 `init --maintainer-path <skills-root>/prd-doc-maintainer` 固定 PRD 维护器位置。运行时能查到文件不代表宿主选择器会自动列出它；本轮仍应读取命令返回的实际路径。

## 能力与依赖适配

| 任务 | 当前宿主需要提供 | 不可用时 |
| --- | --- | --- |
| PRD、需求与版本 | 本地文件读写、Shell、Python 3.9+；现有 macOS/Linux 文件锁 | 仅可讨论或阅读可访问材料，不能宣称已保存 |
| 安装缺失 Skill | Git、GitHub 网络访问、目标目录写权限 | 复用已有完整依赖，报告缺失项 |
| 查看本地工作台 | 本机 HTTP 服务、可访问对应 loopback 地址的浏览器 | 给出文件与命令，说明服务或访问未验证 |
| Demo 交互与截图 | 获准使用的浏览器工具，能打开本机 HTTP、操作页面并保存截图 | 保留静态检查，标记交互证据 degraded |
| 飞书同步 | 已配置的 `lark-cli`、身份和本次写入授权 | 完成本地 PRD，保留待同步状态 |

当前锁定的依赖版本仍有宿主名称。本主 Skill 编排它们时按以下规则适配，不改写安装文件或锁文件：

- `prd-doc-maintainer` 中的 Codex 表示当前 Agent。使用返回目录内的 `scripts/prd_library.py`，Python 命令采用本机可用的 Python 3；CLI 已通过 `sys.executable` 复用当前解释器。
- `demo-design` 中的 Codex 内置 Browser、`codex_builtin_browser` 是浏览器能力角色。在 Claude Code/Cursor/其他宿主中选择现有且获准使用的浏览器工具；只有当前会话实际提供 `browser:control-in-app-browser` 时才读取该 Skill。保持 loopback HTTP、目标视口、命名交互、关键截图和证据要求，报告中写真实工具名称。不能因为换宿主绕过 URL/沙箱策略，也不能将静态检查当作交互验证。
- `demo-design` 的桌面持久终端对应能维持服务并在结束时停止它的终端；若宿主不支持，报告相应限制。默认交互验证与显式请求的 `strict_regression` 继续分开，不为兼容自动安装浏览器或扩大回归范围。
- `use-feishu-cli` 中的重启与沙箱提示作用于当前宿主。按实际文件/网络权限处理，身份、同步范围与读回要求保持原义。

该映射只约束通过 Prototype Flow 编排的任务；独立使用依赖 Skill 时应检查其自身说明。依赖仍保持固定提交和校验值，兼容接入不等于依赖升级。

## 支持边界

原生自动发现、Agent 对任务的理解、浏览器能力是三个独立层次。目录解析和 CLI 测试不能证明每个宿主的完整任务表现。交付时说明实际运行过的宿主、命令和交互证据。

当前运行时面向本地 macOS/Linux。纯聊天工具只有能读取目录并执行命令时才可运行；原生 Windows 文件锁、远端 Agent 到用户电脑的 loopback 访问和云端宿主安装不在本次兼容范围内。
