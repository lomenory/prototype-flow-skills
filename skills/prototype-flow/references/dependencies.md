# 依赖安装

主 Skill 的入口在进入对应阶段时调用 `flow.py dependencies`，自动补齐缺失 Skill。Python 数据操作和 HTTP 服务不会自行联网安装；仅查看已有项目不需要下载依赖。

## 阶段

| `--stage` | 需要的 Skill |
| --- | --- |
| `core`（默认） | `prd-doc-maintainer`、`demo-design` |
| `prd` | `prd-doc-maintainer` |
| `demo` | `prd-doc-maintainer`、`demo-design` |
| `feishu` | `prd-doc-maintainer`、`use-feishu-cli` |
| `all` | 以上全部 |

```bash
python3 -B <skill-dir>/scripts/flow.py dependencies --stage core --project <project-dir>
python3 -B <skill-dir>/scripts/flow.py dependencies --stage feishu --project <project-dir>
python3 -B <skill-dir>/scripts/flow.py dependencies --stage all --check
```

`--check` 只读取本地文件，不联网、不创建目录；有缺失或不完整的依赖时退出码为 1。安装命令全部满足时退出码为 0，JSON 的 `dependencies` 给出 `available`（复用）、`installed`（本次安装）、`missing` 或 `invalid`，以及实际路径。`available` 表示入口名称与必备文件检查通过，不表示用户版本与发布快照逐字相同。

## 来源和安装目录

- 来源：[lomenory/prototype-flow-skills](https://github.com/lomenory/prototype-flow-skills)。公开仓库包含可独立安装的主 Skill 和依赖 Skill，与开发仓库分开维护；不包含前端开发工程、开发测试或业务项目数据。
- `dependencies.lock.json` 固定完整 Git commit SHA、仓库子目录和每个文件的 SHA-256；不追踪 `main` 或自动升级依赖。
- 按项目向上至 Git 根目录查找 `.agents/skills`、`.codex/skills`，再查主 Skill 的同级目录、用户目录和 `/etc/codex/skills`。支持已有 Skill 目录的符号链接。
- 缺失项默认安装到 `~/.agents/skills`；设置 `CODEX_HOME` 时安装到 `$CODEX_HOME/skills`。继续识别历史 `~/.codex/skills`。
- `--dest <skills-root>` 指定唯一查找与安装目录，适合隔离演练或自定义位置。后续使用自定义目录里的 PRD Skill 时，通过 `init --maintainer-path <skills-root>/prd-doc-maintainer` 保存路径。

拉取需要 Python 3.9+、Git 和可访问 GitHub 的网络，运行环境沿用主项目的 macOS/Linux 支持范围。公开仓库下载无需 GitHub 登录；Git 仍遵守使用者现有的代理和凭据配置。下载的脚本不会在安装中执行，子模块和 Git hooks 不会运行。所有缺失项先在临时目录校验，再安装到目标目录；已有同名目录不会被覆盖或自动修复。

## 在当前任务中使用

成功后直接读取返回的 `<path>/SKILL.md`，本轮即可继续对应工作。宿主通常会自动发现新 Skill；若下一轮选择器仍未显示，再刷新或重启 Codex。目录与发现规则依据 [OpenAI Docs](https://learn.chatgpt.com/docs/build-skills)。

若被宿主沙箱拦截，说明实际受阻的网络或目标目录并请求对应权限；不得更换工具绕过限制。网络失败可修复网络后重跑；已有同名目录不完整时先说明缺失文件，保留原目录，按用户明确选择修复或换安装目录。已成功安装的完整依赖会被复用。

这套依赖安装不包含 `lark-cli`、浏览器插件、Node 包、账号登录或云端写入授权。飞书 Skill 安装完成后，仍按其指引检查 CLI 和身份。
