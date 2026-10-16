# 本地运行时与数据

运行时要求 Python 3.9+，维护脚本只使用标准库。预构建工作台随 Skill 分发，打开项目无需构建前端。先运行 `python3 -B <skill-dir>/scripts/flow.py --help`，需要某个命令时查看其子命令帮助。

## 接入项目

在项目实际根目录初始化：

```bash
python3 -B <skill-dir>/scripts/flow.py init <project-dir> --name "项目名称" --library-root prd-library
```

已有文档库可把 `--library-root` 指向项目内现有目录；先检查目录与文档再执行，初始化会给接入 PRD 补稳定文档身份。单份新需求入库可用 `--empty` 初始化，不建立占位总览模块。文档库不能就是项目根目录，不能包含 `versions/`。重复 init 返回既有项目，不重置内容。飞书模式 `--mode feishu` 不自动登录、绑定或写入云端。

典型项目布局：

```text
project/
├── prd-library/               当前 PRD、来源资料与 DOC_MAP 导航
├── .prototype-flow/          当前项目清单、索引、关系、任务、内容库及同步账本
├── demos/<artifact-id>/      可连续编辑的工作稿，以及按需展开的冻结 Demo 缓存
├── demo-framework/<id>/     不可变共享框架版本，含 DESIGN.md 与可运行代码
└── versions/<version-id>/    不可变项目快照
```

需求和 Demo 写命令默认只保存数据，不启动工作台或需求图。需要查看时运行 `requirement-map <project-dir>`，或在本次写命令加 `--requirement-map` 返回服务回执；旧 `--no-requirement-map` 兼容，不能与启用参数同时使用。需要完整工作台时运行 `serve <project-dir> --reuse`，按项目路径发现并健康检查已有服务，成功复用时返回 `reused:true`；否则启动新服务。`serve` 新启动的前台进程仍需保持运行，需求图命令则后台准备服务。已有图继续读取保存结果，不要求每轮准备服务或生成快照。发现信息保存在本机临时目录，不进入项目修订或快照。产品 Demo 在独立 loopback origin 下只读预览。工作台 API 有会话令牌和来源检查，仅提供读取；POST、PUT、PATCH、DELETE 返回 405，Agent 通过本地 CLI 执行写入。不要把本地服务器绑定至公网或向他人分享 API 令牌。

目录与导航由内建运行时维护，无需外部文档维护 Skill。`00-ai-context/DOC_MAP.md` 是统一导航；旧工具生成的 `INDEX.md` 转为导航指针，用户自写 INDEX 保留。已有 `AI_GUIDE.md` 仅替换已知过期维护指引，保留自定义补充，不创建新指南。旧 dashboard 和 `prdlib:related` 正文块不删除、不再生成或回写；历史快照不参与当前文档库维护。

## 数据权威及核心结构

- `.prototype-flow/project.json`：项目身份、模块、文档路径和整数项目修订；格式见 `schemas/project.schema.json`。
- 当前 Markdown：可编辑的业务要求。`document.revision` 是正文 SHA-256，`businessHash` 区分业务内容与已知工具维护字段。
- 需求索引：从 `pf:req` 内容块重建。块元数据见 `schemas/requirement-block.schema.json`。
- `relations.json`：人工语义关联；格式见 `schemas/relations.schema.json`。刷新需求不重新推断依赖。
- `artifacts.json`：工作稿、冻结产物与输入依据。`currentDraftId` 定位工作稿，`lastFrozenArtifactId` 定位最近冻结版；`currentArtifactId` 可指向工作稿。冻结物的页面与流程保存在 `frozenRelations`，不混入当前关联；用 `state --section artifacts --id <id> --full` 查看，`validate --artifacts <id>` 校验。单项字段见 `schemas/artifact.schema.json`。
- `frameworks.json`：共享框架版本、文件哈希和当前框架指针；`framework` 登记候选，`run-start` 固定版本，`demo-prepare` 准备新的完整 Demo，已验证产物登记时同步启用。提取、升级和证据见[项目共享框架](demo-framework.md)。
- `sources.json`：来源登记和已提取内容；文档依据引用来源 ID，不把登记当作已完成分析。
- `runs/`：固定一次任务输入、修改范围和实际进度；工作稿用 `demo-edit` / `demo-save` 管理，首次制作兼容 `run-start` / `demo-finalize`，中断用 `run-finish` 记录，`run-resume` 创建独立续作。原始完整文档与决定产物有效性的 `documentHashes` 分开保存。
- `draft-revisions/<draft-id>/<n>.json` 与 `draft-blobs/<sha>`：工作稿各修订的恢复清单及按内容去重的文件字节；不为每次小改保存完整目录。由运行时维护，不能手改或自行删除仍被引用的数据。
- `storage.json`：新项目的内容存储模式和存储组清单，文件内容复用 `draft-blobs/<sha>`；每组保存逻辑路径与哈希。没有此文件的旧项目继续使用原目录布局，不因只读查询或重复初始化自动迁移。`storage-local.json` 只记录本机已展开路径，受 Git 忽略且不进入历史快照，不是恢复依据。
- `feishu.json` 和 `feishu-plans/`：实时同步账本和固定计划，恢复历史时保留。

schema 是集成格式说明，Python 运行时还有路径、引用、哈希及版本一致性校验；只验证 JSON schema 不代表项目可用。

一个页面绑定示例：

```json
{
  "schemaVersion": 1,
  "flows": [{"id":"FLOW-CHECKOUT", "title":"下单到退款", "requirementIds":["REQ-ORDER-CANCEL"], "steps":[{"title":"查看订单", "bindingId":"BIND-ORDER-UNPAID"}]}],
  "bindings": [{"id":"BIND-ORDER-UNPAID", "requirementIds":["REQ-ORDER-CANCEL"], "artifactId":"DEMO-ORDERS-1", "screenId":"SCREEN-ORDER", "stateId":"STATE-UNPAID", "route":"index.html?screen=order&state=unpaid", "fixtureId":"order-001", "screenshot":"demos/DEMO-ORDERS-1/screenshots/unpaid.png", "verified":false}],
  "supersessions": []
}
```

此处 `verified:false` 是正确的未验证状态；不能为了卡片显示完成改成 true。可在 bindings 扩展 `contractRefs`、证据和专业判断说明，产品契约自身 schema 保持不动。

## 内容存储与兼容迁移

新项目默认使用 `content` 模式。当前工作稿源码保持展开以供编辑；冻结 Demo、存档证据和任务固定输入以完整清单引用按 SHA-256 去重的内容库。相同字节只需一份，产物身份、每次观察的修订、范围、结论及证据引用仍分别保留。工作稿修订和冻结版保留完整逻辑内容及可验证的恢复能力，不要求每个身份各复制一个物理目录。项目快照沿用完整版本格式，从内容库补齐未展开文件并保全引用对象，不改写既有历史版本。

`state`、校验、历史读取和快照从清单读取内容，不为只读查询先展开全部文件。预览、继续编辑和导出按实际需要读取或展开资源；已保存的证据缓存未展开时，不应被下一次保存当作删除。逻辑资源完整而物理缓存不存在是正常状态；清单引用的内容缺失或字节损坏仍明确报错，不能从当前 PRD 或另一版 Demo 补造旧输入。由运行时管理内容库、清单及缓存，勿手改哈希或自行清理仍被引用的对象。

先检查模式、组编号及完整性；旧项目的迁移默认只返回计划：

```bash
python3 -B <skill-dir>/scripts/flow.py storage <project-dir> --action status
python3 -B <skill-dir>/scripts/flow.py storage <project-dir> --action migrate
python3 -B <skill-dir>/scripts/flow.py storage <project-dir> --action migrate --apply
```

`status` 只读汇总，`migrate --apply` 才校验既有文件、捕获内容并启用存储；失败不会用不完整内容替代原布局。旧项目首次迁移先把现有 `local_tasks/` 全量保全到 `archive:legacy-local-tasks` 组及内容库，再启用忽略规则，避免遗漏唯一资料。迁移不重写旧快照、修订、冻结记录及原哈希，不删除物理文件，也不执行 Git 取消追踪。运行时在 `.gitignore` 的受管理区维护可再生缓存与 `local_tasks/` 临时文件的规则，保留用户已有规则；已被 Git 追踪的重复文件不会因此自动退出索引。如需取消追踪，必须在保全内容、核对计划并取得该操作授权后另行处理。

需要完整物理目录时，从 `status` 结果选择准确组编号；省略 `--output` 按清单恢复到原逻辑位置，也可展开到绝对路径：

```bash
python3 -B <skill-dir>/scripts/flow.py storage <project-dir> --action materialize --group <group-key>
python3 -B <skill-dir>/scripts/flow.py storage <project-dir> --action materialize --group <group-key> --output <absolute-directory>
python3 -B <skill-dir>/scripts/flow.py storage <project-dir> --action export --artifact <artifact-id> --output <absolute-directory>
```

展开与导出先验证所需内容，目标有未知或不同字节时拒绝覆盖。`export` 导出所选 Demo 的完整运行文件及存档资料为独立文件夹，可脱离仓库使用，不依赖内容库或绝对本机路径；外部在线资源仍需联网。模块交付继续使用 `export-module`，按资源清单提供运行资源 ZIP，PRD 明确引用的存档资料也随包保留。

`local_tasks/` 放临时输入、日志、组装结果和辅助工具，默认不新增到 Git。若其中含唯一的用户确认、有效验证报告/截图或后续需要的可复跑脚本，先保存到项目正式来源、Demo 存档或其他已维护位置，并修正引用，再清理对应临时文件；不能按目录名一概删除。迁移和忽略规则不会代替这项内容判断，也不回收旧历史或备份。

## 模块工作阶段

阶段值为 `intake`（资料整理）、`draft`（PRD 草稿）、`review`（待确认）、`demo`（Demo 制作）、`validation`（待验收）、`confirmed`（已确认）。Skill 在相应工作开始或完成后，按实际情况更新模块，工作台读取项目清单显示：

```bash
python3 -B <skill-dir>/scripts/flow.py module-stage <project-dir> <module-id> --stage demo
python3 -B <skill-dir>/scripts/flow.py module-stage <project-dir> <module-id> --stage validation --evidence-file <stage-evidence.json>
```

Python 对应 `ProjectStore.set_module_stage(module_id, stage, evidence=None)`，返回更新后的模块。运行时保存 `stageEvidence`、`stageUpdatedAt` 和 `stageHistory`，自动绑定当前 PRD 修订及需求哈希；证据不能只写成与当前输入无关的完成结论。

只有已有明确用户确认记录时才设置 `confirmed`。`--evidence-file` 必须提供以下结构，填写实际确认内容和可定位来源：

```json
{"type":"user-confirmation","summary":"实际用户确认的范围及结论","source":"实际对话或评审记录位置"}
```

确认模块会关闭该模块中被本次确认覆盖、且需求哈希和 PRD 业务哈希仍一致的待分析记录；其他模块和后续变更保持待分析。读取旧项目或旧快照时，同样按有效确认依据计算标签，不为修正标签写入文件，也不把页面关联自动标成已验证。

浏览器测试、AI 审查或产物登记不会自动升级为用户已确认。需求、共享正文或已声明依赖变化时，受影响的 `confirmed` 模块自动回到 `review`，原确认与失效原因保留在阶段历史；已经处于 draft、demo 或 validation 等手动阶段的模块保持原阶段。纯工具维护区域刷新不会撤销确认。此处记录状态不新增审批流程，继续执行当前已授权范围。

## 保存与变更

CLI 的 `state` 和变更操作默认返回摘要，含定位文档所需的身份、修订和结果；需要原完整返回时追加 `--full`。工作台默认读取展示摘要，PRD 正文按需读取，进入 Demo 时检查目标产物与页面证据；未检查的完整性明确显示待检查，不冒充当前已验证。通过摘要或 `DOC_MAP.md` 选定相关文档后按需读取，无需逐层加载多份全库导航。

查询任务、产物或页面绑定使用 `state <project-dir> --section runs|artifacts|bindings`，单项加 `--id <id>`，历史加 `--version <version-id>`。此时 `--full` 只展开所选记录。任务查询不加载 PRD 或 Demo；产物查询只检查所选产物及其依赖文档；绑定查询返回 `relations.bindings`，仅评估选中页面的当前证据。返回的 `project.revision` 是已落盘修订，不包含全项目 `refreshRequired`；检查全局外部变化仍用普通 `state`。历史查询保留整份快照的完整性检查。

`state`、`document`、`compare` 和 `validate` 不创建或写回项目文件。`state` 的项目及模块状态按当前文件计算；`storedRevision` 是已落盘修订，`refreshRequired:true` 表示返回的变化尚未持久化。只读检查到此报告；获准维护后执行 `refresh` 才更新索引、项目修订和确认阶段。工作台 GET 查询同样只读。

新建单份 PRD 使用 `intake <project-dir> --file <payload.json>`：一次保存新模块、来源、公共正文和需求块，设为 `draft`，收尾一次并返回维护及结构检查结果。候选格式见 [需求与资料](requirements.md#一次入库)。该命令不更新已有模块；更新正文或拆合已有需求继续使用下面的操作。

`intake` 自带本次 PRD 的结构检查。单独补检文档使用 `validate <project-dir> --stage prd`，检查文档、需求 ID、来源与引用。局部 Demo 使用 `validate <project-dir> --artifacts <IDs...>` 或 `--bindings <IDs...>`，检查指定对象及其必要依据，不复验无关旧产物；可以同时指定两者。默认 `validate <project-dir>` 保留全项目检查，不遍历历史快照。历史完整性在读取、比较和恢复对应版本时校验。`demo-save` / `demo-finalize` 已检查本次对象，成功后无新改动不再重复运行。纯 PRD 入库不因尚无页面截图而进入 Demo 工作。

`document <root> <id>` 返回当前完整内容及修订。候选正文保存到项目临时文件，再执行：

```bash
python3 -B <skill-dir>/scripts/flow.py save <project-dir> <document-id> --file <candidate.md> --base-revision <loaded-revision>
```

冲突时重新读当前正文，与本地未保存草稿比较后形成合并候选；不要把最新 revision 简单填到旧内容上强行覆盖。Agent 保留候选正文并核对外部变化；工作台仅显示已保存内容。业务正文保存成功后，即使导航维护失败也保留正文，维护结果独立报告；修复后运行 `refresh`，无需再次保存正文。

`requirement` 显式执行 add/split/merge/move/remove；用 `--parts-file` 提供新需求数组，每项至少有 `title` 和 `content`，可含 `priority/sourceIds/dependsOn/demoCoverage`。提供 `--base-revision` 时使用整数项目修订。关系变更以整个 `relations.json` 候选写入，先读取现有值避免删除别人的关联。

注册 Demo 候选的 JSON 示例：

```json
{"id":"DEMO-ORDERS-1", "title":"订单跨模块演示", "path":"demos/DEMO-ORDERS-1", "entryHtml":"index.html", "runId":"RUN-实际任务ID", "status":"candidate", "evidence":{}}
```

上述 `artifact` 登记用于不可变完整产物，包括 candidate；注册后的文件和身份不能原地改写或重用。首次制作可用 `demo-finalize` 一次登记和收尾，后续普通调整优先使用下面的工作稿命令。工作稿只能经专用命令推进修订，不能用 `artifact` 覆盖登记。未完成成果通过 `run-finish --outputs-file` 的 `paths` 保存即可。`runId` 关联真实任务输入；不杜撰占位 runId。只有适用证据支持才能标 current。

## Demo 资源边界

新产物以 `resourceManifest` 区分运行文件、存档资料和排除项；`fileHashes` 只覆盖 `runtimeFiles` 与 `archiveFiles` 的并集。工作稿修订和冻结版保留这两类文件，模块交付只读取运行清单及 PRD 引用资料，`storage --action export` 则导出完整存档副本。排除临时文件不删除当前工作目录中的原文件。辅助编辑、截图和调试脚本优先放在项目 `local_tasks/`，不要混进 Demo 交付目录。

| 类别 | 保留范围 |
| --- | --- |
| 运行文件 | 全部页面入口与跨页面导航、实际使用的 CSS/JS、图片/字体/音视频、本地数据、模板、Worker/WASM 和动态加载资源；共享 Demo 保留完整业务流程 |
| 存档资料 | 设计依据、产品契约、来源说明、已登记报告/截图及其附件、明确登记的编辑或重建源文件/配置/锁文件，以及固定框架依据；页面实际读取的资料归入运行文件 |
| 临时文件 | `.DS_Store`、`Thumbs.db`、`__MACOSX/`、Python/测试缓存、明确的缓存目录，以及未被引用的日志、交换文件和临时备份；一次性辅助脚本和废弃资源显式排除 |

不能按 `.md`、`.json`、`.py` 扩展名或 `screenshots/`、`_framework/`、隐藏目录整体删除。排除项与运行依赖或有效证据冲突时返回具体路径，先纠正声明，不能通过精简静默丢文件。未知文件在工作稿保存时保全为待分类资料；正式冻结及精简导出要求 `unresolved` 为空。

在 `demo-save/demo-finalize` payload 的 `artifact.resourceManifest` 中提供声明；单独 `artifact/framework` 登记直接使用输入对象的 `resourceManifest`，例如：

```json
{
  "schemaVersion": 1,
  "entryPoints": ["index.html", "orders/detail.html"],
  "runtimeDirectories": ["assets", "data/locales"],
  "archiveFiles": ["DESIGN.md", "prototype-contract.json", "validation-report.json"],
  "excludedFiles": ["update_deadline.py"],
  "complete": true
}
```

示例路径须换成实际内容。`entryPoints/runtimeFiles/archiveFiles/excludedFiles` 是相对 Demo 根目录的精确路径数组；输入还可用 `runtimeDirectories/archiveDirectories/excludedDirectories` 声明目录。运行时展开目录并检查静态引用，保存精确清单与哈希；`declaration` 保留原声明供下一修订重新展开。`unresolved` 为未解决分类或依赖的字符串数组。只有 Agent 已核对所有页面、业务状态及动态资源范围时才声明 `complete:true`，且 `runtimeFiles/runtimeDirectories` 必须展开至少一个运行文件；动态拼接的 `fetch()`、`import()`、语言包等须显式补齐，静态扫描和一次访问不能证明完整。完整声明不能掩盖缺失静态资源、分类冲突或未知文件。外部资源仍保留原链接，不自动下载。

无 `resourceManifest` 的旧产物继续按原全目录清单校验、预览和恢复，旧冻结版、ZIP、快照和框架不重写。旧工作稿可以在新修订中建立分类；旧框架要清理时派生新 ID，不能删减后沿用原身份。新快照混有旧产物时保留旧记录要求的文件，历史杂项不会立即消失。新运行时支持旧记录；旧运行时不保证能安全写入新格式，写操作应使用配套更新后的运行时。

持久清单另有 `excludedReasons`，按每个 `excludedFiles` 路径说明排除原因；该字段由运行时生成，不写入声明输入。读取兼容省略原因的早期清单；字段存在时必须与排除路径一一对应，原因不能为空。

## Demo 工作稿

已有 Demo 的日常修改使用同一工作稿，输入仍按轮次固定：

```bash
python3 -B <skill-dir>/scripts/flow.py demo-edit <project-dir> --requirements <IDs...> --change-file <change.json>
python3 -B <skill-dir>/scripts/flow.py demo-edit <project-dir> --bindings <binding-IDs...> --change-file <change.json>
python3 -B <skill-dir>/scripts/flow.py demo-edit <project-dir> --requirements <IDs...> --change-file <change.json> --title "商店 · 七天退款申请"
python3 -B <skill-dir>/scripts/flow.py demo-save <project-dir> <run-id> --file <payload.json>
```

`demo-edit` 创建任务并返回 `draftId`、`artifactId`、`draftRevision`、`beforeRevision` 和 `path`；`draftRevision` 是修改前的修订，初始为 0，首次保存后为 1。首次复制原冻结产物，后续复用同一工作稿编号和路径。按命令返回路径修改文件，不修改原冻结目录。本轮任务记录 `kind:"draft-edit"`；工作稿产物记录 `kind:"working-draft"`、`draftRevision`、`activeRunId` 和 `editStatus`（`editing`、`ready`，或中断后有未保存改动的 `needs-review`）。一个工作稿同时只允许一个编辑任务，发生冲突时检查当前任务，不用旧输入覆盖。

`change.json` 与旧路径的 `run-start --change-file` 相同。Tier 3 开始前，若当前已保存修订尚未冻结，运行时自动保存检查点。未保存改动应先完成当前任务或明确恢复，不把它们冒充已保存修订。额外业务依据用 `--documents` 加入；输入变化仍需判断影响。

CLI 必须通过 `--requirements`、`--bindings` 或 `change.affectedBindingIds` 明确本次范围；全项目使用 `--all-requirements`。未传 change 时 `--bindings` 只记录显式范围，不推断 Tier。命令返回 `affectedModules`、`bindings` 摘要和最小 `saveTemplate`，模板只预填产物标题与本轮摘要，不生成无变化的 binding 补丁。直接补上实际检查与限制即可保存；只有关联或证据确实变化时再增加相应字段。Python `edit_demo()` 的无参数调用保持原有全量兼容，回执以 `scopeExpandedToAll:true` 明示；旧 CLI 无范围调用应补显式选项。

需求变更涉及产物名称中的业务规则时，Agent 在本轮 `demo-edit --title "新标题"` 显式声明完成后的名称（Python 对应 `artifact_title`），如十四天改七天。任务以 `artifactTitle` 固定声明，`saveTemplate.artifact.title` 始终回显声明值或当前名称；原来未命名的产物以其 ID 显示。`demo-save` 省略 `artifact.title` 也会自动应用本轮声明；传入不同名称会拒绝保存。未声明时兼容已有行为：省略标题保留当前名称，也可在保存文件中显式提供非空 `artifact.title`。标题与业务产物、证据和修订一同成功保存后更新并在回执返回 `title`；编辑开始、失败或 PRD 单独保存不会提前改名，冻结产物与旧修订保留原名。运行时不从任意需求文字推断或替换业务名称。

`demo-save` 可使用空对象 `{}` 保存修改；日常流程优先用最小模板记录本轮修改、必要检查及限制。`artifact` 可选，`id`、`path`、`runId` 由任务固定，不可改成另一产物。省略 `status` 时保存为 `candidate`，不新增验证结论，仍保留工作稿修订和恢复数据；不要求为了保存进度整理全套覆盖材料。明确保存为 `verified/current` 必须提供适用的 `evidence.frameworkReview`；框架依据仍有效时可复用其真实来源，不能声称本轮重新观察。例如仅修改文案：

```json
{
  "outputs": {"summary": "修改页面标题并完成静态检查；受影响旧截图待复核"}
}
```

`bindings`、`bindingPatches`、`flows` 和 `moduleStages` 均可省略。`bindings`、`flows` 只提供本次新增或更新条目，按 ID 替换完整记录；空数组保留已有条目。已有页面优先使用 `bindingPatches`，按 ID 只提交变化字段，不能同时在 `bindings` 中更新同一个 ID，也不能改产物身份、验证指纹或修订字段。需要登记本轮页面验证时，patch 必须明确提供真实 `evidence`、`verified:true` 和 `reverify:true`；仅重复旧字段不会更新验证结论。完整依赖范围及继承规则见[页面状态入口](demo-and-change.md#页面状态入口)。运行时以 `verificationDraftRevision` 记录工作稿证据的修订，受影响页面不会因重新保存而继续标为已验证。日常完成必要检查后，可将未整理的覆盖证据保留为待复核，评审或交接再集中登记。页面入口改变或删除必须同时修正关联和流程引用；轻量保存不跳过缺失入口、输入冲突或框架一致性校验。

例如单个页面已经完成本次浏览器检查，可在实际保存文件中提交以下字段（编号、截图和证据替换为本轮结果）：

```json
{
  "bindingPatches": [{
    "id": "BIND-ORDER-UNPAID",
    "screenshot": "demos/实际工作稿/screenshots/order-unpaid.png",
    "verified": true,
    "reverify": true,
    "evidence": {"method": "browser", "summary": "在实际目标视口检查调整区域及对应状态"}
  }],
  "moduleStages": [{"id": "实际模块ID", "stage": "validation"}],
  "outputs": {"summary": "调整并检查订单详情间距"}
}
```

`moduleStages` 只允许本轮需求所属模块，未指定保持原阶段；相同阶段且确认依据未变不新增历史或重写导航。真实阶段变化批量处理一次，PRD 未变时复用已有需求索引；外部 PRD 变化仍更新索引及影响。`confirmed` 仍需每条更新提供用户确认 `evidence`，不能由任务完成或浏览器检查推断。

保存产生新 `draftRevision`，返回 `artifactId`、`title`、`path`、`validation`、`affectedModules` 和 `evidenceSummary` 并结束本次任务。`evidenceSummary` 保留已验证、待复核及本轮复验绑定，并用 `newNeedsReviewBindingIds`、`continuedNeedsReviewBindingIds` 与 `reviewDetails` 区分新增和延续的待复核。原因会说明本轮受影响页面、需求输入、共享文档、资源内容、依赖不明或此前待复核，并列出相关文件或编号；待复核不等于页面功能已损坏。回执可直接作为收尾依据；无后续改动不重复查询或校验。失败不登记成功修订，工作文件和运行中的任务保留，修正后可用同一任务重试。修订保存文件清单及新增内容对象，未改变的字节复用，不生成每轮独立完整 Demo。同次操作复用文件读取、哈希和已有恢复对象，最终检查文件是否在读取期间变化；缓存不跨命令，不跳过外部篡改检查。修订用于恢复，不能替代长期交付版本；`measurements` 仍只填写实际计量结果。

### 复用实际证据组装保存内容

评审、交接或局部任务已有多份实际报告需要汇总时，用 `demo-assemble` 代替手写收尾脚本。日常轻量保存可直接使用 `saveTemplate`，不为装配命令先创建整套报告。它读取运行中的 `demo-edit`、实际报告及截图，校验基线、范围和文件哈希，生成候选，不执行浏览器、保存修订或结束任务。已有保存内容可直接 `demo-save`，不必额外装配。

```bash
python3 -B <skill-dir>/scripts/flow.py demo-assemble <project-dir> <run-id> --file <assembly.json> --output local_tasks/<本轮>/assembled
python3 -B <skill-dir>/scripts/flow.py demo-save <project-dir> <run-id> --file <project-dir>/local_tasks/<本轮>/assembled/save.json
```

`assembly.json` 最小为 `{"reports":["demos/<draft>/evidence/browser.json"]}`，默认按候选状态保存。可带 `summary`、`screenshots`（绑定 ID 到项目相对截图路径），以及 `artifactStatus:"current"`。`current/verified` 还需实际框架报告 `frameworkReport`，或 `frameworkReview:{"mode":"inherited"}` 申请复用固定基线的框架依据；运行时检查来源、框架和报告字节，不能借继承声明补造新观察。

真实报告使用 [证据装配 schema](../schemas/evidence-assembly.schema.json) 的 `$defs.recordedReport`。浏览器记录示例如下，编号、尺寸、结果及 SHA-256 必须来自本轮实际检查：

```json
{
  "schemaVersion": 1,
  "runId": "本轮任务ID", "draftId": "工作稿ID", "draftRevision": 3,
  "kind": "browser", "method": "实际使用的浏览器及检查方法",
  "scope": {"bindingIds": ["BIND-ORDER"], "files": ["index.html", "order.css"], "viewports": [{"width": 1440, "height": 900}]},
  "fileHashes": {"index.html": "实际SHA-256", "order.css": "实际SHA-256"},
  "results": [{"id": "order-layout", "status": "passed", "summary": "实际操作路径与观察结果"}],
  "screenshots": {"BIND-ORDER": {"path": "demos/<draft>/evidence/order.png", "sha256": "实际SHA-256"}}
}
```

报告只列实际检查范围；`scope.files` 包含观察入口和该检查涉及的资源，不等于页面证据继承的完整依赖声明。静态报告使用 `kind:"static"`，可无绑定，不需要截图或视口。`failed/not-run/inherited` 原样保留；只有本轮浏览器通过且无相应静态失败的绑定才提出 `reverify` 补丁，继承或未跑不能升级为本轮通过。装配输出的 `proposedReverificationBindingIds` 只表示待保存候选。

输出限于项目 `local_tasks/` 下的新目录，不能覆盖已有目录或写入已登记 Demo；包含 `save.json` 与装配用 `validation-report.json`。后者是工作记录，不冒充 Demo 包内证据，实际引用的报告和截图必须已在工作稿内。报告过期或范围不匹配时保留原文件与任务，修正真实证据后重试。工具不会判断观察是否真实发生，Agent 仍对报告真实性负责。

冻结与恢复：

```bash
python3 -B <skill-dir>/scripts/flow.py demo-freeze <project-dir> --artifact <draft-id> --title "订单评审版 v1"
python3 -B <skill-dir>/scripts/flow.py demo-restore <project-dir> <draft-id> --revision <n>
```

首次可用、提交评审、确认里程碑或明确保存 Demo 版本时冻结。`demo-freeze` 按已保存资源清单保全运行文件、存档资料和绑定截图，形成不可变完整产物，记录 `frozenFrom:{artifactId,revision}`。`content` 模式保存完整存储组清单并复用内容库，不再为每次冻结复制完整目录；旧项目沿用原复制布局。同一修订已经冻结时复用并返回 `reused:true`，分类变化也必须保存为新修订。工作稿及当前指针保持原样，最近冻结版由 `lastFrozenArtifactId` 记录。冻结保留 candidate 或真实验证状态，不证明用户确认，不自动发布或保存项目快照。

`demo-restore` 找回指定工作稿修订并形成新修订，旧修订不被覆盖，恢复后的 PRD 有效性仍需核对。修订号递增，包含恢复检查点时可以跳号。有活动编辑任务时，冻结、恢复和另起编辑均会拒绝；先完成保存，或用 `run-finish --status partial|failed` 结束当前任务再恢复。恢复前有未保存文件时，运行时先保存其去重恢复数据，并返回 `recoveryCheckpoint` 路径和可恢复的 `recoveryRevision`。此原始恢复检查点也保全未登记和已排除文件，不按正式资源策略过滤，避免替换目录时丢失工作字节。

## Demo 一次收尾

此路径保留给首次制作、框架升级和旧调用方；日常调整优先使用工作稿。`demo-finalize` 本身登记完整不可变产物，不必再为同一成果调用 `demo-freeze`。

`run-start --change-file <change.json>` 可保存 `tier`（0 至 3）、`summary` 和 `affectedBindingIds`；按[修改分级](demo-and-change.md#先限定本次修改)填写。旧任务无此字段仍兼容。完成修改和适用检查后：

```bash
python3 -B <skill-dir>/scripts/flow.py demo-finalize <project-dir> <run-id> --file <payload.json>
```

```json
{
  "artifact": {
    "id": "DEMO-ORDERS-2", "title": "订单间距调整",
    "path": "demos/DEMO-ORDERS-2", "entryHtml": "index.html",
    "status": "current", "evidence": {"frameworkReview": {
      "mode": "inherited", "fromArtifactId": "DEMO-ORDERS-1",
      "summary": "框架及使用方式未变；本次只检查订单按钮所在区域",
      "source": "demos/DEMO-ORDERS-2/evidence/framework-review.md"
    }}
  },
  "bindings": [],
  "flows": [],
  "outputs": {"summary": "填写实际检查、继承证据及待复核范围", "paths": []}
}
```

示例中的状态和证据必须换成实际结果。`artifact` 沿用原登记字段，命令补入 `runId`。`bindings` 只提供本次新增或更新项，`flows` 可选且同样按 ID 合并，不要求复制整份关系；空数组保留现有条目。需要删除或重组关联时继续使用完整 `relations` 操作。绑定字段、依赖范围与 `inheritVerificationFrom` 见[页面状态入口](demo-and-change.md#页面状态入口)，框架继承见[共享框架](demo-framework.md#需求推动框架更新)。

命令原子执行产物登记、关联更新、定向校验与任务结束；`demo-finalize` 要求新资源清单分类完整，存在未解决的分类或依赖时拒绝正式收尾。失败回滚登记状态并保留 Demo 工作目录，警告如实返回。单独的 `artifact` 仍不自动结束任务。不可变产物、输入过期和基线冲突规则均保留。

Demo 命令及检查返回 `commandMetrics`：`elapsedMs` 是命令内部耗时，`inventoryCalls` 是目录清单请求次数；`readCalls/readBytes` 记录经运行时读取接口的实际读取量，`hashedBytes` 记录文件哈希接口处理量，`readCacheHits/hashCacheHits` 记录本次操作复用次数；`copiedFiles/copiedBytes` 是复制量。这些不覆盖所有底层文件操作或 Agent 工具调用。任务 `metrics.draftSave` 包含恢复对象保存，`phaseTimes` 分列实际执行的 `inventoryMs/recoveryReadMs/evidenceMs/validationMs/captureMs`，发生模块阶段更新时另有 `moduleStagesMs`。若实际计量，可在 payload 添加 `measurements:{"editingMs":1234,"browserVerificationMs":5678,"verifiedPages":1}`，省略未计量项。命令时间不包括 Agent 思考、进程启动与工具外的浏览器操作，工作台可见延迟也需单独计量。

## 版本与恢复

`snapshot --name` 固定当前 PRD、关系、Demo 运行文件和存档资料、图片及验证状态，也保存任务记录、所有任务的固定输入和 `outputs.paths` 声明的部分成果。资源策略适用于已登记 Demo/框架；旧记录沿用原全量文件。输出副本放在历史的 `.prototype-flow/run-outputs/`，缺失输出保留警告。内容存储模式的快照保全清单及其引用的对象，不保存本机缓存展开状态；内容未展开也能校验和恢复。保留修订引用的恢复对象必须随快照保全，不因新策略删除历史对象。版本允许未完成项，但如实记录缺失/未验证；保留实际存档文件清单及校验值。`compare --from <version-id> --to working` 比较需求、正文与截图；工作台可读历史版本。

`restore <root> <version-id>` 先严格校验目标历史，再保存恢复前备份并形成新工作修订。恢复前备份允许当前 Demo 或固定输入损坏/缺失，保存实际可读字节、原登记记录及损坏说明，也原样保全即将被替换目录中未登记和已排除的文件，不要求先修好当前 Demo；普通快照仍拒绝篡改。备份标记 `recoveryBackup`，含损坏产物的备份仅供找回文件，不能作为完整恢复目标。历史自身不可编辑；当前飞书绑定、同步基线和实时任务保持不变。

恢复 Demo 或中断任务时用 `state <project-dir> --section runs` 定位，已知编号加 `--id <run-id>`；查看历史任务加 `--version <version-id>`。工作稿任务用 `demo-edit` 接续或 `demo-restore` 恢复修订；`run-resume` 不接受 `kind:"draft-edit"`，避免复制出不持有工作稿编辑权的任务。旧流程的 `run-resume <project-dir> <run-id> --version <version-id>` 从历史固定输入和输出创建新任务，返回 `resumedFrom` 与 `recoveredOutputs`，不覆盖实时任务或原输出。省略版本则从当前任务续作。随后用 `demo-prepare` 将恢复的 Demo 准备到新的 `demos/` 目录，选择与约束见[共享框架](demo-framework.md#后续复用)。新任务输入仍可能落后于当前 PRD，登记产物时继续计算过期状态。旧版本若没有保存任务记录，会明确报缺失，不虚构恢复上下文。

## 用户流程画布

工作台默认进入项目总览，PRD 与需求提供按需需求结构视图，待办与任务保留。顶部保留版本选择，当前或最近任务摘要放入结构图的项目根节点，不另设任务横条。项目总览从模块工作流开始，保留版本历史与资料依据，移除四项统计卡片。独立“待办与任务”页面包含“待处理”和“任务记录”两个表格 Tab；待处理表展示事项、关联对象和原因，任务记录表只保留阶段、状态、开始时间、结束时间和“查看详情”。处理范围、产物、依据修订、阻碍与结果等统一在右侧详情抽屉查看，不展开表格行。支持按任务、模块或需求定位过滤，任务深链自动打开对应抽屉；跨模块任务只显示一条记录，查看操作不修改数据。

工作台的按需需求结构以无限画布展示项目 → 全部 PRD → 各 PRD 需求的结构，不需要先登记 `flows`。空 PRD 和未关联页面的需求也会显示；分支连线表示归属关系，不表示业务执行顺序。支持查看详情、拖动排布、平移、缩放、适应视图、重置排布、缩略地图，以及 PRD/截图/Demo 联动。

卡片依次显示图标与标题、描述、状态与类型标签；需求卡片第三行右侧的复制图标复制名称和稳定编号，不打开抽屉。已确认需求需要重新分析时，“内容待复核”优先于旧确认标签，未确认草稿则显示“待分析”；需求内容确认与模块交付验收分别表达。搜索仅匹配当前版本画布中的节点名称与编号，保留全部节点并高亮匹配项，按 Enter 定位下一个。

相关 PRD、需求卡片另用任务标签和描边体现记录状态：进行中采用绿色描边与沿边框流光，受阻采用红色静态描边，同卡片受阻优先；完成后恢复普通描边。点击任务摘要或标记可查看对应记录和阻碍。状态来自 Agent 已保存的任务，不推测实时进程，任务完成也不代表需求或交付已确认。历史版本将进行中标为“快照时进行中”并使用静态描边；系统要求减少动态效果时也停用流光。

点击项目、PRD 或需求卡片查看对应详情；需求详情包含正文、验收条件、关联页面截图、依赖和资料出处，底部固定按钮可跳转至 PRD 中的需求位置。截图支持放大，关联页面标题直接在新窗口打开独立 Demo；失效产物禁止 Demo 跳转。既有 `flows[].steps` 和页面绑定仍作为项目数据保留，由关系文件维护，画布不提供手动连线来改变业务语义。

需求 Demo 入口复用共享解析器，直接新窗口打开；有多个页面时使用 `primaryRequirementIds` 默认关系。旧数据无默认保留精确页面链接，不猜首项，不提供演示选择器。旧 `mode=demo` 深链保留版本和对象，落在相关需求及明确链接，不自动弹窗。工作台不含 iframe、预览保活、加载遮罩和内容 token 缓存。

拖动位置和视口仅保存在当前浏览器的项目/版本隔离布局中，不改变 PRD、关系、快照或飞书内容。该偏好不跨浏览器来源（含本地端口）共享。历史内容只读，历史画布仍可临时浏览和排布。切换版本时等待对应数据后再展示，避免混用当前与历史页面。

工作台继续检查管理数据的元数据及外部变化，有变化才重读展示摘要，正文按需加载；不轮询 Demo 内容或重载预览。独立 Demo 首期手动刷新。历史版本固定。连接失败保留旧展示，审查上下文仍包含版本、对象和本机定位链接。所有管理 GET 请求只读。

## 对话查询、独立服务和默认入口

按需查看需求图的命令：

```bash
python3 -B <skill-dir>/scripts/flow.py requirement-map <project-dir> --requirement <需求ID>
```

可选 `--module`、`--requirement`、`--version`、`--port`。命令后台准备或复用服务，返回 `status:"ready"`、`url`、`projectId`、`reused`、`autoUpdate`、参数数组 `snapshotCommand` 和真实 `snapshot`；历史 `autoUpdate:false`。它不修改项目业务文件、不打开浏览器、不启动 Demo 预览。Agent 首次打开回执链接，后续使用已有图页，不以 reload 更新进度。命令回执和链接不含 API token。

`init`、`intake`、`save`、`requirement` 及 Demo 任务、工作稿保存等相关写命令仅在显式添加 `--requirement-map` 时附 `requirementMap`，返回准备结果、链接、复用状态和 `snapshotCommand`，不把完整快照塞入写入回执；`ready` 仅表示本地服务可用。服务失败用 `status:"unavailable"`、`error` 与数值 `errorStatus` 报告，业务操作保持实际成功结果；按需求降级为文字或链接，不重放保存或自动补图。默认写命令和兼容的 `--no-requirement-map` 都不准备服务，也不关闭已开图；启用与关闭参数互斥。只读 `state`、`document`、`review-state` 仍不自动启动服务。

实时页每 2 秒检查已保存项目及任务变化，每 30 秒检查外部 PRD、Demo 与证据变化，回焦立即检查；读取只更新展示。稳定 ID 仍存在时保留选中、展开及键盘焦点，历史固定不轮询。只有需要对话图时才按 `snapshotCommand` 读取并呈现离线快照，不声明旧消息实时刷新。一次投影最多 200 条需求，超限时按 `--module` 定向查看或文字交付。覆盖分母由明确 `demoCoverage` 提供，未声明保持未知；验证由当前输入、页面与真实证据决定，不能以任务结束补造。详见[按需需求图与对话呈现](conversation-ui.md)。

`requirement-map <project-dir> --stop` 显式停止该项目共用的需求图与工作台服务，独立 Demo 预览保留。`--stop` 不能和 `--module`、`--requirement`、`--version`、`--port` 同用；返回 `status:"stopped"|"not-running"`、`autoUpdate:false`。关闭标签页不停止后台 worker。停止后普通写命令不会重启服务；再次显式查看或追加 `--requirement-map` 才会准备服务。

`review-state` 按对象范围查询，展示 schema 独立版本化；列表游标绑定实际来源。`preview --reuse` 独立运行，不加载工作台构建或全量 state；`demo-entry` 仅使用已运行预览。注册与健康检查区分 workbench/preview，核对根目录、项目、协议和进程身份，退出只清理本实例注册。`serve --port` 是工作台端口，`--preview-port` 是之后按需启动的预览端口；关闭标签页不停止服务。

binding 可选 `primaryRequirementIds` 是去重需求 ID 数组，须为 `requirementIds` 子集，同产物同需求最多一个默认。省略时保留并裁剪解绑项，显式 `[]` 清空；patch 检查最终集合，可一次清旧设新。完整替换只继承已核实同一逻辑关系；拆合移除清理退役默认，不映射新需求。导航字段不进入需求哈希或验证指纹，冻结/恢复保留，旧快照不改写。新运行时兼容旧命令与旧读取；旧版本运行时不能保证无损写回新增字段。

需求定位先锁版本，在当前产物覆盖时使用它，否则仅使用唯一 live 产物；多个候选报歧义。显式绑定加所属产物，冲突报错。冻结优先 frozenRelations，旧冻结仅允许同版本同 artifact 兼容；历史严格验证快照。有明确默认但失效时报错，不过滤后换别页；无默认且唯一绑定直接打开，多绑定报 default-entry-missing。

`demo-edit --expected-file <baseline.json>` 接受 `review-state` 的 basis.demo 或其 compact hash 基线，在任务、工作稿和检查点创建前核对真实文档/需求/关系/框架/产物字节。原命令未传 expected 保持兼容；冲突后不能换新 hash 强行执行旧请求。

`export-module <project-dir> <module-id> --output <absolute-zip-path> [--version <id>]` 是 module_package 的薄包装，组装完成后原子落盘，已有文件拒绝覆盖；不保存业务、不自动确认/冻结。包内保留模块 PRD、本地引用资源、打开说明，以及关联 Demo 全部入口所需的运行文件。PRD 显式引用关联 Demo 的存档文件时也保留，避免文档断链；其他设计、验证资料留在版本存档。路径和跨模块业务流程保持完整。

工作台另有“导出演示版”，CLI 对应 `export-module <project-dir> <module-id> --format single_html --output <absolute-html-path> [--version <id>]`。这是同一冻结版本的只读单 HTML 派生交付，保持现有工程 ZIP；只序列化完整清单中的运行文件，不附带 PRD 或存档材料。脚本、样式、图像、本地数据及多 HTML 入口内嵌到同一文件；入口在文件内切换，动态图标与头像路径也通过内嵌资源表解析。第三方许可随运行资源内嵌保留。导出不包含当前浏览器的 localStorage、登录态或本机上传文件。

单 HTML 要求完整资源清单，旧记录可以通过明确的只读派生声明满足；模块脚本、Worker、服务器连接、外部运行资源等尚不支持的依赖拒绝导出并指明路径，不能把残缺页面当作成功。普通外部跳转链接保留。导出完成后按范围检查页面切换、主题与选中图标、主要交互及演示内下载；HTTP 浏览器观察与实际双击人工结果分别记录，未实际双击不能声明通过。

新格式导出报告 `runtime-only`；没有资源清单的旧产物默认 `legacy-full`，保留原全量兼容行为（仍忽略 `.DS_Store`），不会重写旧记录或原包。需要只读精简旧版时追加 `--resource-manifest <file.json>`，内容按实际冻结产物 ID 提供声明：

```json
{"schemaVersion":1,"artifacts":{"DEMO-实际冻结ID":{"schemaVersion":1,"entryPoints":["index.html"],"runtimeDirectories":["assets"],"archiveFiles":["DESIGN.md"],"excludedFiles":["update_deadline.py"],"complete":true}}}
```

该参数只适用于所选包内无清单的旧产物，不能覆盖新产物清单或包含无关 ID；检查通过后报告 `derived-runtime`，不改旧产物、哈希、快照或恢复对象。多产物逐项报告模式，包内混合模式为 `mixed`；未提供声明的旧产物仍按完整方式打包。精简前必须解决分类和依赖问题，不能把未检查的包标为精简成功。
