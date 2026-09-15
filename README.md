# Prototype Flow Skills

Prototype Flow 的公开分发仓库，用于分享可直接安装的主 Skill 和依赖 Skill。主 Skill 把资料、PRD、需求、Demo、页面截图和版本历史连接到一个可编辑的本地工作台。

每个 `skills/<name>/` 都是完整的 Skill 目录。此仓库有独立的 Git 历史和发布流程，与开发仓库隔离。

| Skill | 用途 | 加载时机 |
| --- | --- | --- |
| [prototype-flow](skills/prototype-flow/SKILL.md) | 主入口：资料 → PRD → 需求 → Demo → 本地工作台与版本 | 单份需求入库、完整项目或继续更新 |
| [prd-doc-maintainer](skills/prd-doc-maintainer/SKILL.md) | PRD 文档库、索引、关联和 dashboard | 独立文档库维护；主 Skill 不再依赖它 |
| [demo-design](skills/demo-design/SKILL.md) | HTML 高保真 Demo 与交互验证 | 生成或更新 Demo |
| [use-feishu-cli](skills/use-feishu-cli/SKILL.md) | 飞书官方 CLI 操作指导 | 飞书相关任务 |

## 安装主 Skill

主 Skill 使用通用 `SKILL.md` 入口和 Python CLI，可由 Codex、Claude Code、Cursor，或能读取本地文件并执行命令的 Agent 使用。`agents/openai.yaml` 仅提供可选的 Codex 展示元数据。

### Claude Code、Cursor 和通用 Agent

先取得完整仓库：

```bash
git clone https://github.com/lomenory/prototype-flow-skills.git
cd prototype-flow-skills
```

选择一个目标安装主 Skill：

```bash
# Claude Code：个人目录
python3 -B skills/prototype-flow/scripts/install.py --dest ~/.claude/skills
# Cursor：个人目录
python3 -B skills/prototype-flow/scripts/install.py --dest ~/.cursor/skills
# Codex 或使用共享目录的 Agent：个人目录
python3 -B skills/prototype-flow/scripts/install.py --dest ~/.agents/skills
```

仅在某个项目使用时，把目标换成该项目的 `.claude/skills`、`.cursor/skills` 或 `.agents/skills`。其他位置用 `--dest <skills-root>`。安装脚本只复制主 Skill；相同副本复用，不同的同名目录保留并报冲突，`--check` 只读比较。也可让 Agent 直接读取克隆仓库内的入口。

安装后按返回的实际路径发起任务，无需依赖选择器语法：

> 读取 `<已安装的主-Skill-目录>/SKILL.md`，将我提供的资料整理到 projects/my-prototype，建立 PRD 和需求关联，再打开本地工作台；本次先不生成 Demo。

目录、宿主工具映射和支持边界见 [Agent 兼容说明](skills/prototype-flow/references/agent-compatibility.md)。自动发现取决于宿主；CLI 能找到文件不代表每个宿主都会在选择器中列出它。

### Codex 已有安装入口

Codex 用户也可以继续发送：

> 使用 skill-installer 安装 https://github.com/lomenory/prototype-flow-skills/tree/main/skills/prototype-flow

安装后可用 `$prototype-flow` 发起任务。主 Skill 可以单独安装，无需克隆整个仓库。

### 按阶段准备依赖

PRD 整理、入库和本地工作台使用内建运行时，无需外部 Skill。主 Skill 进入 Demo 阶段时使用 `demo-design`，飞书阶段使用 `use-feishu-cli`。下载固定到 Git 提交，逐文件校验后安装；已有 Skill 会被复用，不会被自动覆盖或升级。只查看已有工作台和历史无需下载依赖。

新 Skill 在本轮按返回的文件路径读取使用。依赖中的 Codex/Browser 工具名通过主 Skill 的能力映射接入当前宿主，验收与权限要求保持不变；独立使用依赖 Skill 时，应检查其自身说明。

## 运行条件

- macOS 或 Linux，Python 3.9+。
- 自动下载依赖需要 Git 和 GitHub 网络访问；本仓库公开可读，无需 GitHub 登录。
- 现代浏览器；预构建工作台已包含在主 Skill 中，日常使用无需 Node、npm 或前端构建。
- 飞书功能另需 `lark-cli` 和使用者自己的登录身份，按需配置。

安装器只安装 Skill 文件，不会安装外部工具或配置账号；宿主的网络和目录权限仍适用。缺失依赖优先安装到主 Skill 所在的标准宿主目录，自定义位置可使用 `--dest` 或 `PROTOTYPE_FLOW_SKILLS_DIR`。继续兼容 `CODEX_HOME` 与历史 Codex 目录；具体优先级见 [依赖安装说明](skills/prototype-flow/references/dependencies.md)。

## 从仓库直接试用

也可以在克隆仓库后，通过 CLI 初始化独立项目并启动工作台：

```bash
git clone https://github.com/lomenory/prototype-flow-skills.git
cd prototype-flow-skills
python3 -B skills/prototype-flow/scripts/flow.py init ../my-prototype --name "我的原型项目"
python3 -B skills/prototype-flow/scripts/flow.py serve ../my-prototype
```

打开命令返回的本机 URL，使用 `Ctrl+C` 停止服务。CLI 负责初始化、保存、关联和版本；资料分析、PRD 写作与 Demo 生成由当前 Agent 按主 Skill 说明完成。本机工作台地址仅当前电脑可用。

## 轻量需求入库

新项目可以使用 `init <project-dir> --name "项目名称" --empty` 建立空项目，再执行 `intake <project-dir> --file <payload.json>`，一次保存来源、完整 PRD 和需求块，统一维护导航并进行 PRD 检查。输入格式见 [需求与资料](skills/prototype-flow/references/requirements.md#一次入库)。

CLI 默认返回摘要，`document` 读取单份正文；需要完整状态时使用 `state <project-dir> --full`。普通文档补检用 `validate <project-dir> --stage prd`。入库不自动生成 Demo、启动工作台或保存项目快照。

内建维护生成一份 `DOC_MAP.md` 导航，保留旧项目的文档身份、关联块和历史兼容；不再自动生成独立 dashboard 或回写全库关联。

## 分发内容

主 Skill 包含 `SKILL.md`、界面元数据、依赖锁文件、Python 运行时、阶段参考、数据 schema，以及预构建工作台和第三方许可证。

公开仓库不包含开发工作台的 React 源码、`node_modules`、开发测试、业务项目、订单示例、演练截图、开发日志、缓存或账号配置。依赖 Skill 内用于运行和理解规范的模板与小型 JSON 示例保留。

## 兼容验证范围

已验证主 Skill 的标准及自定义目录解析、完整包安装、依赖校验、PRD 初始化与索引维护、结构检查和版本保存；工作台沿用已通过测试的构建。Claude Code/Cursor 的原生发现、实际对话决策和 Demo 浏览器操作仍需对应宿主的实测，CLI 演练不替代这些证据。

## 快照维护

首批分发快照整理于 2026-09-15：

- `prd-doc-maintainer` 和 `use-feishu-cli`：保留作者维护的现有 Skill 文件。
- `demo-design`：仅分发经过 Core 验证的 Runtime/Contract v9，契约哈希 `e0a96def6e9c`；文件哈希和原始来源提交记录在 `runtime-manifest.json` 中。

维护时只发布已经验证的 Skill 运行目录；不把开发仓库的 Git 历史或工作目录整体同步到这里。更新依赖时先验证新的完整快照，再更新主 Skill 的 `dependencies.lock.json` 中的提交与文件哈希。仅更新主 Skill 时保留依赖锁；已安装版本不会自动追踪分支最新内容。
