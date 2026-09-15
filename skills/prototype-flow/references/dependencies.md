# 依赖安装

PRD 整理、保存、导航和本地工作台由内建运行时完成，无需外部 Skill。进入 Demo 或飞书阶段时调用 `flow.py dependencies`，按需补齐缺失 Skill；Python 数据操作和 HTTP 服务不会自行联网安装。

## 阶段

| `--stage` | 需要的 Skill |
| --- | --- |
| `core`（默认） | `demo-design` |
| `prd` | 无；保留此阶段供已有调用兼容 |
| `demo` | `demo-design` |
| `feishu` | `use-feishu-cli` |
| `all` | `demo-design`、`use-feishu-cli` |

```bash
python3 -B <skill-dir>/scripts/flow.py dependencies --stage core --project <project-dir>
python3 -B <skill-dir>/scripts/flow.py dependencies --stage feishu --project <project-dir>
python3 -B <skill-dir>/scripts/flow.py dependencies --stage all --check
```

`--check` 只读取本地文件，不联网、不创建目录；有缺失或不完整的依赖时退出码为 1。安装命令全部满足时退出码为 0，JSON 的 `dependencies` 给出 `available`（复用）、`installed`（本次安装）、`missing` 或 `invalid`，以及实际路径。`available` 表示入口名称与必备文件检查通过，不表示用户版本与发布快照逐字相同。

## 来源和安装目录

- 来源：[lomenory/prototype-flow-skills](https://github.com/lomenory/prototype-flow-skills)。公开仓库包含可独立安装的主 Skill 和依赖 Skill，与开发仓库分开维护；不包含前端开发工程、开发测试或业务项目数据。
- `dependencies.lock.json` 固定完整 Git commit SHA、仓库子目录和每个文件的 SHA-256；不追踪 `main` 或自动升级依赖。
- 支持 `.agents/skills`、`.claude/skills`、`.cursor/skills`、`.codex/skills`。默认从项目向上查到 Git 根，优先当前主 Skill 所在宿主的目录，再查其余目录；之后查主 Skill 同级、默认安装目录、`$CODEX_HOME/skills`（若设置）、用户目录及历史 `/etc/codex/skills`。已有 Skill 目录可为符号链接。此顺序是本 CLI 的依赖解析规则，不替代各宿主自身的发现规则。
- 缺失项的安装目录优先级：`--dest` → `PROTOTYPE_FLOW_SKILLS_DIR` → 位于上述标准目录内的主 Skill 同级目录 → `$CODEX_HOME/skills`（历史兼容）→ `~/.agents/skills`。主 Skill 在 `.claude/skills` 或 `.cursor/skills` 时，不会被残留的 `CODEX_HOME` 改变安装位置。从开发仓库或其他非标准位置运行时，可显式指定目标。
- `--dest <skills-root>` 或环境变量 `PROTOTYPE_FLOW_SKILLS_DIR` 指定唯一查找与安装目录，不再混用其他位置；后续依赖命令保持相同目录。CLI 参数优先于环境变量。

拉取需要 Python 3.9+、Git 和可访问 GitHub 的网络，运行环境沿用主项目的 macOS/Linux 支持范围。公开仓库下载无需 GitHub 登录；Git 仍遵守使用者现有的代理和凭据配置。下载的脚本不会在安装中执行，子模块和 Git hooks 不会运行。所有缺失项先在临时目录校验，再安装到目标目录；已有同名目录不会被覆盖或自动修复。

## 在当前任务中使用

成功后直接读取返回的 `<path>/SKILL.md`，本轮即可继续对应工作。自动发现与刷新方式取决于当前宿主，不依赖 Codex 的选择器或 `skill-installer`。安装入口、官方目录依据和依赖工具名的映射见 [Agent 兼容](agent-compatibility.md)。

若被宿主沙箱拦截，说明实际受阻的网络或目标目录并请求对应权限；不得更换工具绕过限制。网络失败可修复网络后重跑；已有同名目录不完整时先说明缺失文件，保留原目录，按用户明确选择修复或换安装目录。已成功安装的完整依赖会被复用。

这套依赖安装不包含 `lark-cli`、浏览器插件、Node 包、账号登录或云端写入授权。飞书 Skill 安装完成后，仍按其指引检查 CLI 和身份。
