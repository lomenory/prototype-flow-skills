# Prototype Flow Skills

Prototype Flow 的公开分发仓库，用于分享可直接安装的主 Skill 和依赖 Skill。主 Skill 把资料、PRD、需求、Demo、页面截图和版本历史连接到一个可编辑的本地工作台。

每个 `skills/<name>/` 都是完整的 Skill 目录。此仓库有独立的 Git 历史和发布流程，与开发仓库隔离。

| Skill | 用途 | 加载时机 |
| --- | --- | --- |
| [prototype-flow](skills/prototype-flow/SKILL.md) | 主入口：资料 → PRD → 需求 → Demo → 本地工作台与版本 | 完整项目或继续更新 |
| [prd-doc-maintainer](skills/prd-doc-maintainer/SKILL.md) | PRD 文档库、索引、关联和 dashboard | PRD 及完整项目 |
| [demo-design](skills/demo-design/SKILL.md) | HTML 高保真 Demo 与交互验证 | 生成或更新 Demo |
| [use-feishu-cli](skills/use-feishu-cli/SKILL.md) | 飞书官方 CLI 操作指导 | 飞书相关任务 |

## 安装主 Skill

把以下内容发给 Codex：

> 使用 skill-installer 安装 https://github.com/lomenory/prototype-flow-skills/tree/main/skills/prototype-flow

安装后发起实际任务，例如：

> 使用 $prototype-flow，将我提供的资料整理到 projects/my-prototype，建立 PRD 和需求关联，再打开本地工作台；本次先不生成 Demo。

主 Skill 在进入相应阶段时自动补齐缺失 Skill：PRD 阶段使用 `prd-doc-maintainer`，Demo 阶段追加 `demo-design`，飞书阶段按需使用 `use-feishu-cli`。下载固定到 Git 提交，逐文件校验后安装；已有 Skill 会被复用，不会被自动覆盖或升级。只查看已有工作台和历史无需下载依赖。

新 Skill 在本轮可按返回的文件路径读取使用；若下一轮仍未出现在选择器，再刷新或重启 Codex。主 Skill 可以单独安装，使用者无需克隆整个仓库。也可以用 Skill Installer 单独安装表格中的其他 Skill。

## 运行条件

- macOS 或 Linux，Python 3.9+。
- 自动下载依赖需要 Git 和 GitHub 网络访问；本仓库公开可读，无需 GitHub 登录。
- 现代浏览器；预构建工作台已包含在主 Skill 中，日常使用无需 Node、npm 或前端构建。
- 飞书功能另需 `lark-cli` 和使用者自己的登录身份，按需配置。

安装器只安装 Skill 文件，不会安装外部工具或配置账号；宿主的网络和目录权限仍适用。依赖默认安装到 `~/.agents/skills`；设置 `CODEX_HOME` 时使用 `$CODEX_HOME/skills`，兼容已有 `~/.codex/skills`。更多选项见 [依赖安装说明](skills/prototype-flow/references/dependencies.md)。

## 从仓库直接试用

也可以在克隆仓库后，通过 CLI 初始化独立项目并启动工作台：

```bash
git clone https://github.com/lomenory/prototype-flow-skills.git
cd prototype-flow-skills
python3 -B skills/prototype-flow/scripts/flow.py dependencies --stage core
python3 -B skills/prototype-flow/scripts/flow.py init ../my-prototype --name "我的原型项目"
python3 -B skills/prototype-flow/scripts/flow.py serve ../my-prototype
```

打开命令返回的本机 URL，使用 `Ctrl+C` 停止服务。CLI 负责初始化、保存、关联和版本；资料分析、PRD 写作与 Demo 生成通过 Codex 中的主 Skill 完成。本机工作台地址仅当前电脑可用。

## 分发内容

主 Skill 包含 `SKILL.md`、界面元数据、依赖锁文件、Python 运行时、阶段参考、数据 schema，以及预构建工作台和第三方许可证。

公开仓库不包含开发工作台的 React 源码、`node_modules`、开发测试、业务项目、订单示例、演练截图、开发日志、缓存或账号配置。依赖 Skill 内用于运行和理解规范的模板与小型 JSON 示例保留。

## 快照维护

首批分发快照整理于 2026-09-15：

- `prd-doc-maintainer` 和 `use-feishu-cli`：保留作者维护的现有 Skill 文件。
- `demo-design`：仅分发经过 Core 验证的 Runtime/Contract v9，契约哈希 `e0a96def6e9c`；文件哈希和原始来源提交记录在 `runtime-manifest.json` 中。

维护时只发布已经验证的 Skill 运行目录；不把开发仓库的 Git 历史或工作目录整体同步到这里。更新依赖时先验证新的完整快照，再更新主 Skill 的 `dependencies.lock.json` 中的提交与文件哈希。仅更新主 Skill 时保留依赖锁；已安装版本不会自动追踪分支最新内容。
