# Prototype Flow

将新资料整理成 PRD 并存入项目，也可以继续推进需求拆分、高保真 Demo 和版本管理。日常生成和修改 Demo 采用轻量流程，工作台与需求图按需查看，完整覆盖核对和截图整理集中在评审或交接时。按本次请求执行所需阶段，单份需求入库可以独立完成。

**PRD 维护已内建。** 项目初始化、资料入库、需求索引、文档导航和本地工作台只需安装 `prototype-flow`；生成 Demo 或同步飞书时再使用相应的外部 Skill。

这是可直接安装的公开分发仓库，每个 `skills/<name>/` 都是完整的 Skill 目录。开发源码、测试和业务示例由独立开发仓库维护。

## 能做什么

2026-10-27 demo-design 设计指导与显式依赖升级：补充文案、语义配色、光学对齐、组件几何及动效规则，保留品牌、平台和可读性例外。更新主 Skill 后，可运行 `python3 -B <skill-dir>/scripts/flow.py dependencies --stage demo --upgrade --dest <skills-root>`，按固定依赖锁获取新版；追加 `--check` 先离线查看差异。升级前完整备份旧依赖，回执返回 `backupPath`，重复升级不重复下载或备份；日常依赖检查不自动覆盖已有版本。详见[依赖升级](skills/prototype-flow/references/dependencies.md#显式升级已有依赖)。

2026-10-16 单 HTML 演示版导出：保留原工程 ZIP（Demo 与 PRD），新增“导出演示版”，将运行脚本、样式、图像、本地数据及多个 HTML 入口收进一个文件，不附带 PRD 或归档材料。动态头像、文件图标、主题与激活状态继续可用，管理台可在文件内切换；仅转换完整且依据有效的已确认冻结版本。CLI 使用 `export-module <project-dir> <module-id> --format single_html --output <absolute-html-path>`，默认仍为工程 ZIP。尚不支持的运行依赖会明确报错；静态、HTTP 与实际双击结果分别记录。

2026-10-15 工作台打包下载修复：内容读取与存储缓存覆盖整个 ZIP 收集过程；前端对响应与文件读取设置统一 60 秒期限，超时会恢复按钮并反馈，迟到的响应不再触发下载。下载包保留完整 Demo 资源并默认解压后双击入口，实际双击验收与静态检查分别记录。主包同时更新配套交付说明，依赖锁继续固定已发布的新版 demo-design。

2026-10-15 Demo 交付与分级更新：默认保留完整资源目录，解压后双击入口 HTML（通常为 `index.html`）即可演示。demo-design 的静态检查新增本地 CSS mask 和本地模块加载风险识别，静态、HTTP 预览与人工双击确认分别记录。现有业务模型内的有界规则、状态及需求映射修改可按 Tier 2 定向验证；显式严格回归使用 `--contract-change-scope bounded`，模型与权限边界变化仍要求 Tier 3。当前 Core 契约哈希为 `4bbf2a253c88`。

2026-10-15 内容存储缓存修复：修正存储组索引的缓存键被遍历变量覆盖的问题，同一次操作复用已验证索引，避免每读取一个未展开文件都重新检查整份清单。跨操作和清单变化仍重新校验，完整性与并发修改检查继续生效。

源码通过 526 项 Python 回归；本次分发副本另通过 31 项专项检查，涵盖缓存复用与失效、原生读取、恢复、完整导出、CLI 和 HTTP。大清单项目的隔离副本验证已通过，未新增浏览器业务验收。依赖与工作台资源保持不变。

2026-10-15 内容存储更新：新项目默认以完整清单复用按 SHA-256 去重的内容库，冻结 Demo 不再复制整套目录。当前工作稿源码继续直接编辑，验证资料和固定任务输入可按需读取或恢复；预览、截图、校验、导出、继续编辑及历史恢复使用同一读取机制，未展开的证据不会被下一次保存当作删除。每次修订、观察范围、验证结论与原始字节分别保留。

没有存储模式标记的旧项目保持原行为，`storage --action migrate` 先只读生成计划，`--apply` 才启用新存储；首次迁移先保全现有 `local_tasks`，不改写旧快照、修订或冻结哈希，不删除原文件，也不取消已有 Git 追踪。`storage --action status` 检查内容与本地副本，`materialize` 按组恢复，`export` 生成含运行文件和存档资料的独立完整文件夹；模块 ZIP 继续遵循既有运行资源边界。只读查询不自动展开文件或迁移项目。

源码通过 522 项 Python 回归；发布副本另验证实际模块来源、CLI、HTTP、旧版兼容、未展开内容、恢复及失败保护。两个仓库外完整合成包已在真实浏览器中核对相对资源、数据加载、页面跳转及按钮交互，不能替代实际产品验收。操作及兼容说明见[内容存储与兼容迁移](skills/prototype-flow/references/runtime.md#内容存储与兼容迁移)。

2026-10-14 Demo 导出与存档资源更新：新 Demo 维护版本化 `resourceManifest`，导出保留全部页面及运行依赖、模块 PRD 与其引用附件；版本存档另保留设计依据、产品契约、验证证据和修订恢复对象。缓存、日志、临时备份和已声明的辅助文件不进入新正式存档，当前工作文件不会自动删除。正式收尾、冻结和精简导出前需要解决未分类文件与动态资源依赖。

已有 ZIP、冻结版和项目快照保持原样；无清单的旧 Demo 默认继续完整导出，也可用 `--resource-manifest` 只读派生精简包，不改原版本及哈希。恢复前原始备份仍保全未登记和已排除文件。源码通过 471 项 Python 测试；分发副本另验证导出、存档、旧版兼容与恢复保护。真实 Chrome 合成 Demo 验证涵盖解压后的多页面跳转、动态数据和 Worker，不能替代实际业务验收。资源声明及兼容边界见[运行时说明](skills/prototype-flow/references/runtime.md#demo-资源边界)。

2026-10-14 轻量流程更新：日常 Demo 只定位相关需求、修改页面、检查受影响范围、保存修订并交付独立预览。保存模板仅预填标题与摘要，关联、证据及模块阶段按实际变化补充；业务规则变化先同步 PRD，修订、恢复和必要检查继续保留。旧证据允许待复核，不把保存成功当作验证通过。完整覆盖与截图整理在评审或交接时按约定范围完成，查看工作台本身不触发补图或验收。

相关写命令默认不启动需求图服务；显式 `--requirement-map` 或独立 `requirement-map` 命令才准备服务，旧 `--no-requirement-map` 参数继续兼容。已打开的图仍读取后续保存结果；停止后普通保存不会重启服务。项目内局部修改按影响选择 Tier，浏览器验证与交付复用独立预览，避免重复启动服务。源码通过 441 项 Python 测试及 Skill 结构检查；本次未新增浏览器视觉验收。

同时包含此前六项优化：写入回执不重复展开整张图、外部变化按需检查、工作稿恢复数据按内容复用、现有证据可用 `demo-assemble` 汇总、待复核原因可定位，以及 `demo-entry --current` 与服务版本查询/显式重启。详见[日常轻量流程与评审交接](skills/prototype-flow/references/demo-and-change.md)和[运行时说明](skills/prototype-flow/references/runtime.md)。

以下日期条目记录旧版本当时的行为；当前默认流程以上述内容存储、资源规则、轻量流程和后面的命令说明为准。

2026-10-13 滚动保留与产物标题修复：卡片暂时没有布局尺寸时保留最近的阅读位置，恢复显示后再按锚点恢复；用户已在当前卡片选择、输入或滚动后，迟到的宿主状态回传不再覆盖当前视图。需求变更涉及产物名称时，Agent 在 `demo-edit --title` 声明本轮目标标题，保存模板回显名称；`demo-save` 即使省略标题，也随成果成功保存同步应用。保存失败保持原标题，旧冻结版本与历史修订保留原名称。

本轮通过 54 项前端状态检查、47 项 Python 标题与工作稿检查及 32 项 Python 需求图检查。实际新项目用 30 条需求和长说明跑完拆解、Demo 生成、14 天改 7 天及工作稿保存；4 条需求的 5 个页面状态重新操作验证，其余 26 条保留未生成。首次进入工作稿时左右滚动保持 187 / 508.5px，选中、展开、筛选与页签保留；需求修改和保存后的阅读锚点偏差小于 0.11px。过期宿主状态覆盖在旧版浏览器中可复现，修复版保持阅读位置；历史单次归零没有事件日志，本轮不将其唯一归因于该路径。

2026-10-13 顶部与详情区精简：桌面顶部合为两行，项目摘要一行，搜索、筛选与视图切换一行；展开、收起、定位及完整覆盖统计集中到“更多”菜单。右侧固定头只保留两行需求标题与关闭按钮，模块、编号、确认状态和完整标题归入“需求”页签，生成覆盖状态归入“Demo 覆盖”页签。筛选隐藏当前需求时保留详情与阅读位置，并在正文和底栏提示。

本次实现通过 121 项前端及 40 项相关 Python 检查；实际浏览器核对 30 / 100 条需求、长标题、左右独立滚动、菜单键盘操作和 390px 窄屏。在同一 1066×853 窗口中，顶部由约 203px 降到 91px，详情阅读区由约 391px 增至 582px；离线对话卡片保持 600px 高度边界。沿用稳定 ID、筛选、页签、展开与阅读状态的更新机制。操作说明见[布局与阅读操作](skills/prototype-flow/references/conversation-ui.md#布局与阅读操作)。

2026-10-13 需求卡片布局重建：对话卡片在可用高度内展示，本地实时页填满窗口，左右阅读区独立滚动。默认关系图只展开当前模块，支持名称与 ID 搜索、模块及 Demo 状态组合筛选，也可切换紧凑列表；详情按“需求 / Demo 覆盖 / 依据”分区。正常数据更新保留选中、模块及覆盖目标展开、筛选、页签和阅读位置。当前需求因状态变化退出筛选时继续保留详情并提示；窄屏在结构与详情之间切换。

此前布局重建通过 112 项前端及 70 项相关 Python 检查，并在 Codex In-app Browser 用 30 / 100 条真实验收项目、约 3000 字说明及 30 个覆盖目标实际核对高度、滚动、生成与需求变更更新。卡片未被内容撑高，阅读锚点偏移小于 1px；单份快照减少重复数据，仍保留 256 KiB 大小限制。全局或仓库文件更新不替换已运行服务的代码；旧服务需重新启动，已加载页面需重新加载，才能使用新版布局。

2026-10-13 默认需求图更新：需求拆解、Demo 生成和需求变更默认接入同一张本地实时需求图，点击节点在右侧核对需求说明、验收条件、来源与逐项页面覆盖。成功的相关 CLI 写命令自动准备或复用服务，回执附 `requirementMap`；对话呈现同款阶段快照，旧消息不会后台刷新。需求图更新保留仍有效的选中需求、模块展开与焦点；完整管理工作台仍按需查看，Demo 预览独立运行。

新增 `requirement-map` 接入、定向及历史快照、停止与恢复入口；`--no-requirement-map` 用于单次纯命令操作，不关闭已有图。服务准备失败不撤销业务保存，使用快照和文字回退。覆盖分母来自显式 `demoCoverage`，未声明范围保持未知；只有当前输入与实际验证证据匹配时显示已验证，生成完成不代表用户确认。详见[默认需求图与对话呈现](skills/prototype-flow/references/conversation-ui.md)。

上一轮默认需求图通过 393 项 Python 测试、94 项前端测试、Skill 结构与安装闭包检查；独立新项目在实际 Codex In-app Browser 中验证空图新增需求、生成中、已验证、需求变更待更新及复验后再次已验证，全程未刷新图页且选中、展开状态保留。分发包另检查准确文件闭包、CLI 和只读 HTTP 资源；仅更新主 Skill，保留两个按需依赖及锁文件。

2026-10-12 对话执行与独立 Demo 更新：任务默认在普通对话中推进，卡片按需使用，PRD 入库后直接交付真实回执与文件入口；工作台按需用于项目管理，默认进入项目总览，需求结构按需查看。工作台移除 iframe、演示需求/页面状态选择器及预览专用刷新，需求和页面链接在新窗口独立打开。

新增只读 `review-state`、固定卡片渲染器、独立 `preview` / `demo-entry` 和 `export-module`；支持 `primaryRequirementIds` 默认入口、冻结/工作稿/历史命名空间，以及 `demo-edit --expected-file` 在任何写入前核对真实基线。预览与工作台分别复用和停止，已有 Demo 窗口首期手动刷新。卡片消息桥尚未完成真实 Codex 点击链路验收，默认提供可复制请求，不因缺少卡片能力打开工作台。详见[对话与可选卡片](skills/prototype-flow/references/conversation-ui.md)。

开发验证通过 316 项 Python 测试、52 项前端测试、生产构建、浏览器独立页面/历史链接与卡片布局检查；发布包另按准确文件闭包、CLI 和只读 HTTP 资源检查。浏览器 wrapper 和 DOM 模拟不代替真实宿主消息送达。仅同步主 Skill，保留两个按需依赖及锁文件。

2026-09-23 工作台预览更新：Demo 预览不再显示覆盖画面的状态提示；工作稿保存和未保存内容变化后仍会自动刷新当前预览。同步完整预构建资源。本次通过 43 项前端测试、生产构建与 17 项分发包 HTTP 静态资源检查；运行时代码与上一版一致。

2026-09-23 工作稿预览与局部编辑更新：工作台按需读取正文和检查目标 Demo，当前预览每 2 秒检查变化，较慢的全局扫描保留每 30 秒执行；未保存内容变化可刷新当前预览，未检查证据明确显示待检查。`demo-edit` 支持显式需求或绑定范围，回执提供保存模板；`demo-save` 支持页面字段补丁和批量模块阶段更新，并复用单次操作中的读取与哈希。完整同步新版运行时、技能说明及工作台构建资源。本次通过 244 项 Python 测试、43 项前端测试、生产构建、分发包 CLI 和 17 项 HTTP 静态资源检查；未新增浏览器视觉验收。

2026-09-23 深色工作台更新：统一画布、PRD、任务与弹层的深色主题，顶部栏调整为 48px 并采用小号控件，优化窄窗口布局与来源链接换行。完整发布最新工作台预构建资源，对应开发提交 `1c3f286`。本次通过 40 项前端测试、生产构建及分发包 17 项 HTTP 静态资源检查；Python 运行时与上一版一致，沿用已通过的 220 项回归测试，未新增浏览器视觉验收。

2026-09-23 Demo 工作稿更新：新增 `demo-edit` / `demo-save`，日常调整复用同一工作稿路径并保存可恢复修订；`demo-freeze` 保存完整不可变交付版本，`demo-restore` 找回指定修订。工作台支持预览调整中的工作稿、显示修订与证据状态，并避免把新修订冒充旧任务成果；下载只使用与当前修订对应的冻结版本。冻结证据与后续工作稿变化保持独立。包含最新工作台构建资源，对应开发提交 `d7d7b63`。本次通过 220 项 Python 测试、40 项前端测试、生产构建及分发包 17 项 HTTP 静态资源检查，未新增浏览器视觉验收。详见[工作稿操作](skills/prototype-flow/references/runtime.md#demo-工作稿)。

2026-09-22 局部 Demo 工作流更新：按实际修改范围选择检查，新增 `demo-finalize` 一次登记产物、更新关联、定向检查并结束任务，失败时回滚登记。`validate --artifacts` / `--bindings` 支持检查指定对象及必要依赖；未变化页面在依赖完整且证据有效时可显式继承验证，框架与用法未变时可继承框架依据。每版仍保存完整不可变 Demo，继承证据与本次实际检查分别记录，并提供命令计量。本次通过 196 项 Python 回归测试及分发包 CLI 检查；工作台前端和依赖未变，未新增浏览器视觉验收。详见[运行时说明](skills/prototype-flow/references/runtime.md)。

2026-09-22 打包下载修复：ZIP 保留 `.gitignore`、隐藏资源目录等正常 Demo 资源，已登记的 `.DS_Store` 继续参与完整性校验但不写入交付包。覆盖当前稿、历史快照和项目迁移后的下载；绝对路径、目录穿越和反斜杠路径仍被拒绝。工作台前端与依赖未变。

2026-09-22 技能引导更新：支持根据已有资料和项目状态判断起点、沿用明确授权接续工作，并在交付时说明成果入口及有价值的可选下一步。仅在缺口会改变目标或范围时询问，不要求重新填写已知信息。同步更新技能展示说明与默认提示词；本次仅涉及技能文档和配置，未改变工作台或运行时，也未增加工作台“建议下一步”功能。

| 任务 | 完成内容 | 所需 Skill |
| --- | --- | --- |
| 初始化项目 | 项目身份、PRD 目录、索引与导航，可接入已有文档库 | [prototype-flow](skills/prototype-flow/SKILL.md) |
| 新资料整理入库 | 来源记录、PRD Markdown、稳定需求 ID 和 PRD 检查 | prototype-flow |
| 持续整理需求 | Agent 通过 CLI 编辑正文、拆分或合并需求、维护显式依赖和模块阶段 | prototype-flow |
| 核对需求与进度 | 按需打开需求图或完整工作台，查看需求详情、页面状态覆盖和真实任务进度 | prototype-flow |
| 下载已确认需求 | 工程 ZIP 保留 Demo、PRD 和本地引用；单 HTML 演示版内嵌完整运行资源，不含 PRD；支持历史版本 | prototype-flow |
| 保存和恢复版本 | 冻结当前 PRD、关系、Demo 与证据，查看历史或恢复工作副本 | prototype-flow |
| 制作高保真 Demo | 设计、交互实现、浏览器验证及页面状态与截图交付 | prototype-flow + [demo-design](skills/demo-design/SKILL.md) |
| 复用项目 Demo 框架 | 固定共享框架与完整业务 Demo，准备新目录并保留历史版本 | prototype-flow + demo-design |
| 同步飞书展示 | 本地 PRD 单向同步到已授权的飞书目标 | prototype-flow + [use-feishu-cli](skills/use-feishu-cli/SKILL.md) |

2026-09-15 更新：内建文档维护、一次入库 `intake`、默认摘要输出及 `validate --stage prd` 已发布。详见[实现提交 df8d8e7](https://github.com/lomenory/prototype-flow-skills/commit/df8d8e79961bb5f74d9830cea0c07056649817ba)。

2026-09-16 更新：查询保持只读；局部 Demo 按实际依赖判断过期；流程引用与截图指纹可校验；损坏 Demo 支持保留备份后恢复；快照保存中断任务，并通过 `run-resume` 独立续作；飞书含图部分失败可继续同一计划。Demo 成功交付须记录 `run-finish --status completed`。

2026-09-16 工作台更新：工作台仅提供浏览，新增模块、新增需求、需求编辑与其他写入操作统一交给 Agent 通过 CLI 执行；PRD 与流程画布中的需求点均可复制名称和稳定编号。确认模块后清除对应的待分析状态，之后有新变更时重新提示。

此前打包下载发布包通过 115 项 Python 回归测试、10 项前端测试和前端构建；Chromium 已验证打包下载、解压后 Demo 的下单与支付状态交互，此前已验证浏览、需求复制、历史查看与刷新。飞书恢复验证使用模拟传输，未执行真实云端写入。旧截图证据缺少指纹时显示待复核，旧快照未保存的任务记录不会自动补造。详见[运行时说明](skills/prototype-flow/references/runtime.md)与[场景验收](skills/prototype-flow/references/acceptance.md)。

2026-09-16 打包下载更新：已确认模块可在总览卡片顶部右侧、PRD 页面和画布详情下载 ZIP。卡片中的下载按钮替换原箭头，点击下载不会打开卡片详情。按需求关联选择 Demo，多套 Demo 保留各自目录，共享 Demo 保持完整，不裁剪其他模块的页面。包内包含 PRD Markdown、本地引用与运行说明；缺少资源、Demo 损坏或依据旧稿时明确提示。外部在线资源仍需联网。

2026-09-16 工作台布局更新：默认进入用户流程，侧栏精简为用户流程、PRD 与需求、项目总览三个图标入口。顶部保留项目名称和版本选择，提供流程图 / Demo 演示切换。当前节点搜索高亮匹配项，卡片采用图标与标题、两行 12px 描述、状态与类型标签，并在需求卡片右下角提供复制图标。

Demo 直接嵌入工作区，右上角可收起的需求列表切换登记页面状态；模式切换保留已加载页面，历史版本使用对应快照。PRD 三栏铺满页面且标题高度对齐；需求抽屉精简信息，在底部固定 PRD 跳转。项目总览合并进度、版本历史与资料依据，版本摘要并入顶部统计面板。

本次布局更新通过 117 项 Python 测试、15 项前端测试和构建；浏览器已核对模式切换、状态导航、搜索高亮、复制不误触、抽屉固定底栏、PRD 定位及三栏对齐。发布包另做文件哈希、HTTP 资源、只读接口和 ZIP 资源检查。

2026-09-17 完整工作台更新：发布需求分支折叠与搜索定位、可调宽度的详情标签面板、居中的 Demo 需求/状态选择器、按阶段切换的项目总览，以及可收起的 PRD Anchor 目录和正文标题布局。需求整理拆分保存并检查通过后自动启动工作台。本次重新通过 117 项 Python 测试、19 项前端测试和生产构建；浏览器交互证据沿用开发仓库中对应相同构建的验收记录。

2026-09-17 PRD 导航更新：PRD 切换器移至顶部版本选择右侧，左侧 Anchor 目录只展示当前 PRD 的标题和需求，切换后目录同步更新。此条更新对应开发提交 `ed7c158`；验证范围为前端测试、生产构建与发布包 HTTP 资源检查，未重新执行浏览器交互验收。

2026-09-17 导航布局更新：顶部栏横跨窗口，品牌按钮移至左上角，版本切换采用下拉菜单；侧栏位于顶部栏下方，宽 57px，按钮 32px、图标 16px，窄窗口下随顶部栏换行调整内容区域。对应开发提交 `eab3ae3`。发布验证覆盖 19 项前端测试、生产构建与 HTTP 资源检查；浏览器证据沿用该提交的 `output/playwright/figma-shell/` 验收记录，包含版本切换、PRD 导航和 900px 窗口检查。

2026-09-17 主题配色更新：统一使用 `indigo/600` 主题色、`green/600` 成功色和 `yellow/600` 警告色，配套按钮交互色阶、Alert 浅底与边框、状态标签及画布强调；错误提示边框减轻为 `red/200`。对应开发提交 `a9054e5`。发布验证覆盖 19 项前端测试、生产构建与 HTTP 资源检查；浏览器配色证据沿用该提交的 `output/toast-audit/` 第二轮记录，不代表新增业务失败路径测试。

2026-09-18 工作台与运行时更新：新增独立“待办与任务”页面，以表格和详情抽屉查看待处理事项及任务记录；结构图项目节点显示最近任务，相关卡片标记进行中或受阻。新增本地及历史资料预览、PRD 内部链接定位、审查位置链接与上下文复制；当前稿每 30 秒及页面回焦时检查变化，按需刷新并保留有效阅读位置。任务状态来自已保存记录，任务完成不代表需求或交付已确认，所有页面仍只读。打包下载保留在总览卡片和 PRD 页面，画布详情不再提供该入口。

`serve --reuse` 支持发现并健康检查同项目服务；Demo 任务默认只固定相关输入，确需全库上下文时使用 `run-start --full-context`。普通 Demo 在完成修改与验证后一次性登记不可变产物，中断成果通过任务 `outputs.paths` 保存；默认 `validate` 检查当前稿，历史内容在读取、比较或恢复对应版本时校验。对应开发提交 `8365fb8`、`7e9803a`；本次通过 129 项 Python 测试、37 项前端测试、生产构建和发布包 HTTP 资源检查，未新增浏览器视觉验收结论。

2026-09-20 演示与详情更新：进入 Demo 演示模式时隐藏工作台侧栏，演示区域占满顶部栏下方宽度；切回“需求结构”恢复侧栏并保留已加载的 Demo。需求详情标签调整为“关联页面 / 需求 / 依据与依赖”，首次打开默认展示关联页面，切换需求保留当前标签。本次发布当前开发工作区的完整预构建资源，通过 37 项前端测试、生产构建和 HTTP 资源检查；运行时和依赖未变，未新增浏览器视觉验收结论。

2026-09-20 共享 Demo 框架更新：新增 `framework`、`demo-prepare` 和框架数据格式。首次生成或接入 Demo 先建立项目共享框架；后续任务固定框架版本和完整基准 Demo，在新目录复用公共实现与已有业务成果。只有验证证据和输入基线符合要求时才同步切换当前框架与 Demo，冲突或写入失败不推进指针；旧项目仍可浏览，后续生成前需提取框架。详见[项目共享框架](skills/prototype-flow/references/demo-framework.md)。本次通过 142 项 Python 测试，并检查发布包命令与 HTTP 资源；工作台资源与上一版一致，沿用已有前端验证，不新增视觉验收结论。

2026-09-21 查询与运行时更新：新增按任务或产物及编号查询，避免加载无关内容；Demo 续作优先使用恢复成果，多个成果可用 `demo-prepare --from-output` 选择。新登记的已验证框架产物必须把真实验证报告或截图保存在自身 Demo 包内；统一流程步骤的依赖解析，加强刷新失败回滚和来源文件保护。飞书本地命令不准备云端依赖，状态检查包含引用图片的变化，转换保留代码示例并拒绝真实本地链接。对应开发提交 `cabf2bf`，通过 164 项 Python 测试及发布包 CLI、HTTP 检查；工作台资源沿用已验证版本，飞书验证使用模拟传输，未执行真实云端同步。

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

> 读取 `<已安装的主-Skill-目录>/SKILL.md`，将我提供的资料整理到 projects/my-prototype，建立 PRD 和需求关联；本次先不生成 Demo，需要核对时我会再打开需求图。

目录、宿主工具映射和支持边界见 [Agent 兼容说明](skills/prototype-flow/references/agent-compatibility.md)。自动发现取决于宿主；CLI 能找到文件不代表每个宿主都会在选择器中列出它。

### Codex 已有安装入口

Codex 用户也可以继续发送：

> 使用 skill-installer 安装 https://github.com/lomenory/prototype-flow-skills/tree/main/skills/prototype-flow

安装后可用 `$prototype-flow` 发起任务。主 Skill 可以单独安装，无需克隆整个仓库。

### 更新已有安装

`git pull` 只更新当前仓库；如果 Agent 使用的是个人目录中的 Skill 副本，还需更新该副本。安装器不会覆盖不同内容的已有目录。

1. 在本分发仓库运行 `git pull --ff-only`，确认获取最新 `main`。
2. 核对 Agent 实际读取的 `prototype-flow/SKILL.md` 路径。若直接使用本仓库，无需再复制；若使用个人目录，先备份旧的 `prototype-flow` 到 skills 目录之外，再用本仓库的 `skills/prototype-flow` 完整替换原目录。不要只复制 `SKILL.md` 或将新版资源叠加到旧目录。
3. 在本分发仓库运行 `python3 -B skills/prototype-flow/scripts/install.py --dest <实际的-skills-根目录> --check`，确认返回 `ok: true`、`status: available`。例如 Codex 安装在 `~/.codex/skills/prototype-flow` 时，`--dest` 使用 `~/.codex/skills`。
4. 按用途使用新包：查看需求图用 `requirement-map <项目目录>`，完整项目管理用 `serve <项目目录> --reuse`，查看 Demo 时运行 `preview <项目目录> --reuse` 后用 `demo-entry --current` 解析入口。用 `service <项目目录> --kind workbench|preview` 核对服务版本；确需加载新运行时才显式加 `--restart`。关闭浏览器标签页不等于停止服务，停止需求图共用服务用 `requirement-map <项目目录> --stop`，独立预览保留。日常保存不启动或重启这些服务。

需求文档、Demo 和项目版本保存在项目目录中，更新技能时保留这些项目目录。

### 按阶段准备依赖

PRD 整理、入库、本地工作台及飞书 `configure/prepare/status` 使用内建运行时，无需外部 Skill。主 Skill 进入 Demo 阶段时使用 `demo-design`，飞书云端操作 `bind/sync` 使用 `use-feishu-cli`。下载固定到 Git 提交，逐文件校验后安装；已有 Skill 会被复用，不会被自动覆盖或升级。只查看已有工作台和历史无需下载依赖。

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

CLI 默认返回摘要，`document` 读取单份正文。任务、产物或页面绑定查询使用 `state <project-dir> --section runs|artifacts|bindings`，单项追加 `--id <id>`；此时 `--full` 只展开所选记录。只有确需全部状态时使用无 section 的 `state <project-dir> --full`。普通文档补检用 `validate <project-dir> --stage prd`。Agent 在需求整理拆分保存并检查通过后交付真实回执、文件入口和必要说明，工作台、需求图及对话快照按需展示。入库不自动生成 Demo 或保存项目快照。

内建维护生成一份 `DOC_MAP.md` 导航，保留旧项目的文档身份、关联块和历史兼容；不再自动生成独立 dashboard 或回写全库关联。

## 按需需求图

顶部“更多”提供全部展开、全部收起、定位当前及完整统计，菜单支持方向键、Home / End、Escape 和点击外部关闭。关闭右侧详情可扩大结构阅读区，“查看详情”恢复当前需求。编号、确认状态和完整标题在“需求”页签中核对，任务及页面状态在“Demo 覆盖”页签中核对，来源在“依据”页签中核对。

相关写命令默认仅保存数据。显式添加 `--requirement-map` 后，成功回执中的 `requirementMap` 包含 `status`、本机 `url`、`projectId`、`reused`、`autoUpdate` 和参数数组 `snapshotCommand`。也可随时显式查看：

```bash
python3 -B skills/prototype-flow/scripts/flow.py requirement-map ../my-prototype
python3 -B skills/prototype-flow/scripts/flow.py review-state ../my-prototype --view requirement-map
```

`requirement-map` 返回真实 `snapshot`，后台准备或复用服务，命令本身不打开浏览器。Agent 首次打开回执链接，后续需求、任务及 Demo 保存自动更新同一页；不要每次重开或刷新。默认每 2 秒检查已保存变化，每 30 秒检查外部文件变化，回到页面立即检查。可用 `--module` 定向查看、`--requirement` 设置初始选中、`--version` 查看固定历史；一次投影最多 200 条需求，超限按模块查看。渲染器读取 `snapshot` JSON，不读取整个命令回执。

简单只读查询和普通写命令不启动服务。旧 `--no-requirement-map` 参数保留兼容，与 `--requirement-map` 互斥，均不关闭已开图；显式准备服务失败时，回执 `unavailable/error/errorStatus` 只表示展示不可用，业务保存仍然成功，不重放写入。只有需要对话图示时才运行 `snapshotCommand`，没有内嵌能力时按需交付本机链接、离线图文件或文字。

关闭页不会停止服务。需要停止时执行 `requirement-map ../my-prototype --stop`，仅停止该项目共用的图和完整工作台服务，Demo 预览独立保留；之后普通写命令不会再次启动服务，显式请求查看时再准备。停止不能与范围、版本或端口参数同用。图的已验证状态来自当前实际证据，不自动确认需求、制作 Demo 或扩大授权范围；查看图也不要求补齐覆盖或截图。

## 打开完整本地工作台

需要查看项目时执行：

```bash
python3 -B skills/prototype-flow/scripts/flow.py serve ../my-prototype --reuse
```

打开命令返回的本机 URL；返回 `reused: true` 表示复用已有服务，新启动的服务需保持进程运行，使用 `Ctrl+C` 停止。预构建工作台只读展示 PRD、模块阶段、页面截图、需求结构、待办与任务和版本历史；Demo 链接新窗口独立打开。需求点的复制按钮会复制明确的需求名称与编号，画布右下角可复制审查上下文。编辑、阶段确认、保存或恢复版本等写入操作由 Agent 通过 CLI 执行，工作台 HTTP 写入请求返回 405。本机地址仅当前电脑可用；生成 Demo 或同步飞书仍按具体任务执行。

## 独立 Demo 与可选对话卡片

```bash
python3 -B skills/prototype-flow/scripts/flow.py preview ../my-prototype --reuse
python3 -B skills/prototype-flow/scripts/flow.py demo-entry ../my-prototype --current
python3 -B skills/prototype-flow/scripts/flow.py review-state ../my-prototype --view requirement --requirement <需求ID>
```

需求变更后的产物名称与本轮成果一起保存。名称涉及新规则时先声明目标，再按任务回执的 `saveTemplate` 完成适用检查并保存：

```bash
python3 -B skills/prototype-flow/scripts/flow.py demo-edit ../my-prototype --requirements <需求ID> --change-file <变化说明JSON> --title "七天退款申请"
python3 -B skills/prototype-flow/scripts/flow.py demo-save ../my-prototype <任务ID> --file <保存JSON>
```

省略目标标题时沿用当前名称；运行时不从任意需求正文猜测业务标题。声明后的名称在成功保存时更新，冻结原版本继续使用原标题。

日常复用最小 `saveTemplate` 记录本轮修改、实际检查和限制；未变绑定与模块阶段不重复提交。PRD 规则变更先保存正文，再建立 Demo 新基线；新增、删除或改变入口时维护必要关联。已有实际报告确需汇总时才用 `demo-assemble`，不为每轮保存编写全套报告。评审或交接时集中核对约定范围的覆盖和截图证据，明确缺口并冻结版本；冻结不等于用户确认。

`preview` 不依赖工作台构建或管理进程，浏览器验证与交付复用同一服务。`demo-entry --current` 返回当前 Demo 及 PRD、修订信息；也可指定 `--requirement <需求ID>`、产物或精确绑定。绑定使用 `--binding <绑定ID> --within-artifact <产物ID>`，历史加 `--version`。一个需求多页面时使用明确默认；旧数据无默认保留精确页面链接，不猜第一项、不自动写入默认。冻结与历史不会回退当前稿。

多对象选择、比较或复杂输入确有帮助时，Agent 可用 `review-state` 和 `render_conversation.py` 生成安全的只读快照。卡片不是项目权威源，旧请求仍需核对真实基线。真实内嵌消息桥未验收时使用完整可复制请求；普通对话、文件和独立 Demo 始终可以推进任务。

用户明确请求模块交付包时，运行 `export-module <项目目录> <模块ID> --output <绝对ZIP路径> [--version <版本ID>]`。新格式按运行资源清单导出；旧格式默认完整导出，需要精简时追加 `--resource-manifest <清单JSON路径>`，按所选冻结产物 ID 提供资源声明。沿用确认、冻结及完整性条件，不自动确认模块、冻结工作稿或覆盖已有文件。项目快照另保留设计、契约和验证资料；字段与排除规则见[资源边界](skills/prototype-flow/references/runtime.md#demo-资源边界)。

## 分发内容

本仓库仅分发 `prototype-flow` 主 Skill，以及 Demo 和飞书阶段按需使用的 `demo-design`、`use-feishu-cli`。

主 Skill 包含 `SKILL.md`、界面元数据、依赖锁文件、Python 运行时、阶段参考、数据 schema，以及预构建工作台、实时与离线需求图、其他对话卡片模板和第三方许可证。

公开仓库不包含开发工作台的 React 源码、`node_modules`、开发测试、业务项目、订单示例、演练截图、开发日志、缓存或账号配置。依赖 Skill 内用于运行和理解规范的模板与小型 JSON 示例保留。

## 兼容验证范围

已验证主 Skill 的标准及自定义目录解析、完整包安装、依赖校验、PRD 初始化与索引维护、结构检查和版本保存；工作台沿用已通过测试的构建。Claude Code/Cursor 的原生发现、实际对话决策和 Demo 浏览器操作仍需对应宿主的实测，CLI 演练不替代这些证据。

## 快照维护

首批分发快照整理于 2026-09-15：

- `use-feishu-cli`：保留作者维护的现有 Skill 文件。
- `demo-design`：仅分发经过 Core 验证的 Runtime/Contract v9，契约哈希 `e0a96def6e9c`；文件哈希和原始来源提交记录在 `runtime-manifest.json` 中。

维护时只发布已经验证的 Skill 运行目录；不把开发仓库的 Git 历史或工作目录整体同步到这里。更新依赖时先验证新的完整快照，再更新主 Skill 的 `dependencies.lock.json` 中的提交与文件哈希。仅更新主 Skill 时保留依赖锁；已安装版本不会自动追踪分支最新内容。
