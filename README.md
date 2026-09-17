# Prototype Flow

将新资料整理成 PRD 并存入项目，也可以继续推进需求拆分、高保真 Demo、页面截图关联和版本管理。按本次请求执行所需阶段，单份需求入库可以独立完成。

**PRD 维护已内建。** 项目初始化、资料入库、需求索引、文档导航和本地工作台只需安装 `prototype-flow`；生成 Demo 或同步飞书时再使用相应的外部 Skill。

这是可直接安装的公开分发仓库，每个 `skills/<name>/` 都是完整的 Skill 目录。开发源码、测试和业务示例由独立开发仓库维护。

## 能做什么

| 任务 | 完成内容 | 所需 Skill |
| --- | --- | --- |
| 初始化项目 | 项目身份、PRD 目录、索引与导航，可接入已有文档库 | [prototype-flow](skills/prototype-flow/SKILL.md) |
| 新资料整理入库 | 来源记录、PRD Markdown、稳定需求 ID 和 PRD 检查 | prototype-flow |
| 持续整理需求 | Agent 通过 CLI 编辑正文、拆分或合并需求、维护显式依赖和模块阶段 | prototype-flow |
| 浏览项目 | 只读本地工作台、跨模块流程画布、已有页面和截图关联，复制需求名称与编号 | prototype-flow |
| 下载已确认需求 | 按模块打包关联 Demo 的完整目录与运行资源、PRD 和本地引用；支持历史版本 | prototype-flow |
| 保存和恢复版本 | 冻结当前 PRD、关系、Demo 与证据，查看历史或恢复工作副本 | prototype-flow |
| 制作高保真 Demo | 设计、交互实现、浏览器验证及页面状态与截图交付 | prototype-flow + [demo-design](skills/demo-design/SKILL.md) |
| 同步飞书展示 | 本地 PRD 单向同步到已授权的飞书目标 | prototype-flow + [use-feishu-cli](skills/use-feishu-cli/SKILL.md) |

2026-09-15 更新：内建文档维护、一次入库 `intake`、默认摘要输出及 `validate --stage prd` 已发布。详见[实现提交 df8d8e7](https://github.com/lomenory/prototype-flow-skills/commit/df8d8e79961bb5f74d9830cea0c07056649817ba)。

2026-09-16 更新：查询保持只读；局部 Demo 按实际依赖判断过期；流程引用与截图指纹可校验；损坏 Demo 支持保留备份后恢复；快照保存中断任务，并通过 `run-resume` 独立续作；飞书含图部分失败可继续同一计划。Demo 成功交付须记录 `run-finish --status completed`。

2026-09-16 工作台更新：工作台仅提供浏览，新增模块、新增需求、需求编辑与其他写入操作统一交给 Agent 通过 CLI 执行；PRD 与流程画布中的需求点均可复制名称和稳定编号。确认模块后清除对应的待分析状态，之后有新变更时重新提示。

此前打包下载发布包通过 115 项 Python 回归测试、10 项前端测试和前端构建；Chromium 已验证打包下载、解压后 Demo 的下单与支付状态交互，此前已验证浏览、需求复制、历史查看与刷新。飞书恢复验证使用模拟传输，未执行真实云端写入。旧截图证据缺少指纹时显示待复核，旧快照未保存的任务记录不会自动补造。详见[运行时说明](skills/prototype-flow/references/runtime.md)与[场景验收](skills/prototype-flow/references/acceptance.md)。

2026-09-16 打包下载更新：已确认模块可在总览卡片顶部右侧、PRD 页面和画布详情下载 ZIP。卡片中的下载按钮替换原箭头，点击下载不会打开卡片详情。按需求关联选择 Demo，多套 Demo 保留各自目录，共享 Demo 保持完整，不裁剪其他模块的页面。包内包含 PRD Markdown、本地引用与运行说明；缺少资源、Demo 损坏或依据旧稿时明确提示。外部在线资源仍需联网。

2026-09-16 工作台布局更新：默认进入用户流程，侧栏精简为用户流程、PRD 与需求、项目总览三个图标入口。顶部保留项目名称和版本选择，提供流程图 / Demo 演示切换。当前节点搜索高亮匹配项，卡片采用图标与标题、两行 12px 描述、状态与类型标签，并在需求卡片右下角提供复制图标。

Demo 直接嵌入工作区，右上角可收起的需求列表切换登记页面状态；模式切换保留已加载页面，历史版本使用对应快照。PRD 三栏铺满页面且标题高度对齐；需求抽屉精简信息，在底部固定 PRD 跳转。项目总览合并进度、版本历史与资料依据，版本摘要并入顶部统计面板。

本次布局更新通过 117 项 Python 测试、15 项前端测试和构建；浏览器已核对模式切换、状态导航、搜索高亮、复制不误触、抽屉固定底栏、PRD 定位及三栏对齐。发布包另做文件哈希、HTTP 资源、只读接口和 ZIP 资源检查。

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

## 初始化项目

安装后可直接让 Agent 执行：

> 读取 `<已安装的主-Skill-目录>/SKILL.md`，在 projects/my-prototype 初始化“我的原型项目”。先建立空项目，后续我会提供资料。

也可以通过 CLI 初始化。以下命令从克隆仓库的根目录执行：

```bash
python3 -B skills/prototype-flow/scripts/flow.py init ../my-prototype --name "我的原型项目" --empty
```

新建空项目包含：

```text
my-prototype/
├── .prototype-flow/          项目身份、需求索引、来源、关系与产物登记
└── prd-library/
    ├── 00-ai-context/
    │   └── DOC_MAP.md        自动维护的文档导航
    ├── 01-active/            当前 PRD
    ├── 03-research/          来源资料
    └── 05-prototypes/        文档引用的图片与设计导出
```

- 去掉 `--empty` 时，在没有接入模块的情况下建立“项目总览”占位 PRD；其业务内容由后续资料补齐。
- 接入项目内已有文档库时指定 `--library-root <相对目录>`，先检查文档，再补齐稳定身份和索引。重复 `init` 返回已有项目状态，保留现有内容。
- 初始化完成后即可保存 PRD；Demo 产物、项目快照和飞书绑定在对应阶段建立。项目规则文件由使用者按需配置。

CLI 负责保存和一致性；资料理解、PRD 撰写和 Demo 设计由当前 Agent 按技能说明完成。更多参数见 [运行时说明](skills/prototype-flow/references/runtime.md#接入项目)。

## 轻量需求入库

新项目可以使用 `init <project-dir> --name "项目名称" --empty` 建立空项目，再执行 `intake <project-dir> --file <payload.json>`，一次保存来源、完整 PRD 和需求块，统一维护导航并进行 PRD 检查。输入格式见 [需求与资料](skills/prototype-flow/references/requirements.md#一次入库)。

CLI 默认返回摘要，`document` 读取单份正文；需要完整状态时使用 `state <project-dir> --full`。普通文档补检用 `validate <project-dir> --stage prd`。Agent 在需求整理拆分保存并检查通过后，自动启动工作台并打开本机地址；同一项目已有可用服务时复用。入库不自动生成 Demo 或保存项目快照。

内建维护生成一份 `DOC_MAP.md` 导航，保留旧项目的文档身份、关联块和历史兼容；不再自动生成独立 dashboard 或回写全库关联。

## 打开本地工作台

需要查看项目时执行：

```bash
python3 -B skills/prototype-flow/scripts/flow.py serve ../my-prototype
```

打开命令返回的本机 URL，使用 `Ctrl+C` 停止服务。预构建工作台只读展示 PRD、模块阶段、已有 Demo 与页面截图、跨模块流程和版本历史。需求点的复制按钮会复制明确的需求名称与编号，方便交给 Agent 修改。编辑、阶段确认、保存或恢复版本等写入操作由 Agent 通过 CLI 执行，工作台 HTTP 写入请求返回 405。本机地址仅当前电脑可用；生成 Demo 或同步飞书仍按具体任务执行。

## 分发内容

本仓库仅分发 `prototype-flow` 主 Skill，以及 Demo 和飞书阶段按需使用的 `demo-design`、`use-feishu-cli`。

主 Skill 包含 `SKILL.md`、界面元数据、依赖锁文件、Python 运行时、阶段参考、数据 schema，以及预构建工作台和第三方许可证。

公开仓库不包含开发工作台的 React 源码、`node_modules`、开发测试、业务项目、订单示例、演练截图、开发日志、缓存或账号配置。依赖 Skill 内用于运行和理解规范的模板与小型 JSON 示例保留。

## 兼容验证范围

已验证主 Skill 的标准及自定义目录解析、完整包安装、依赖校验、PRD 初始化与索引维护、结构检查和版本保存；工作台沿用已通过测试的构建。Claude Code/Cursor 的原生发现、实际对话决策和 Demo 浏览器操作仍需对应宿主的实测，CLI 演练不替代这些证据。

## 快照维护

首批分发快照整理于 2026-09-15：

- `use-feishu-cli`：保留作者维护的现有 Skill 文件。
- `demo-design`：仅分发经过 Core 验证的 Runtime/Contract v9，契约哈希 `e0a96def6e9c`；文件哈希和原始来源提交记录在 `runtime-manifest.json` 中。

维护时只发布已经验证的 Skill 运行目录；不把开发仓库的 Git 历史或工作目录整体同步到这里。更新依赖时先验证新的完整快照，再更新主 Skill 的 `dependencies.lock.json` 中的提交与文件哈希。仅更新主 Skill 时保留依赖锁；已安装版本不会自动追踪分支最新内容。
