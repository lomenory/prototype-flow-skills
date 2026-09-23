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
├── .prototype-flow/          当前项目清单、索引、关系、任务及同步账本
├── demos/<artifact-id>/      可连续编辑的工作稿，以及完整冻结 Demo 和资源
├── demo-framework/<id>/     不可变共享框架版本，含 DESIGN.md 与可运行代码
└── versions/<version-id>/    不可变项目快照
```

需要打开工作台时运行 `serve <project-dir> --reuse`，按项目路径发现并健康检查已有服务，成功复用时返回 `reused:true`；否则启动新服务。新启动的服务仍需保持进程运行。发现信息保存在本机临时目录，不进入项目修订或快照。产品 Demo 在另一 loopback origin 下只读预览。工作台 API 有会话令牌和来源检查，仅提供读取；POST、PUT、PATCH、DELETE 返回 405，Agent 通过本地 CLI 执行写入。不要把本地服务器绑定至公网或向他人分享 API 令牌。

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

CLI 的 `state` 和变更操作默认返回摘要，含定位文档所需的身份、修订和结果；需要原完整返回时追加 `--full`。工作台仍使用完整数据接口，不受 CLI 输出精简影响。通过摘要或 `DOC_MAP.md` 选定相关文档后按需读取，无需逐层加载多份全库导航。

查询任务或产物使用 `state <project-dir> --section runs|artifacts`，单项加 `--id <id>`，历史加 `--version <version-id>`。此时 `--full` 只展开所选记录。任务查询不加载 PRD 或 Demo；产物查询只检查所选产物及其依赖文档。返回的 `project.revision` 是已落盘修订，不包含全项目 `refreshRequired`；检查全局外部变化仍用普通 `state`。历史查询保留整份快照的完整性检查。

`state`、`document`、`compare` 和 `validate` 不创建或写回项目文件。`state` 的项目及模块状态按当前文件计算；`storedRevision` 是已落盘修订，`refreshRequired:true` 表示返回的变化尚未持久化。只读检查到此报告；获准维护后执行 `refresh` 才更新索引、项目修订和确认阶段。工作台 GET 查询同样只读。

新建单份 PRD 使用 `intake <project-dir> --file <payload.json>`：一次保存新模块、来源、公共正文和需求块，设为 `draft`，收尾一次并返回维护及结构检查结果。候选格式见 [需求与资料](requirements.md#一次入库)。该命令不更新已有模块；更新正文或拆合已有需求继续使用下面的操作。

`intake` 自带本次 PRD 的结构检查。单独补检文档使用 `validate <project-dir> --stage prd`，检查文档、需求 ID、来源与引用。局部 Demo 使用 `validate <project-dir> --artifacts <IDs...>` 或 `--bindings <IDs...>`，检查指定对象及其必要依据，不复验无关旧产物；可以同时指定两者。默认 `validate <project-dir>` 保留全项目检查，不遍历历史快照。历史完整性在读取、比较和恢复对应版本时校验。`demo-save` / `demo-finalize` 已检查本次对象，成功后无新改动不再重复运行。纯 PRD 入库不因尚无页面截图而进入 Demo 工作。

`document <root> <id>` 返回当前完整内容及修订。候选正文保存到项目临时文件，再执行：

```bash
python3 -B <skill-dir>/scripts/flow.py save <project-dir> <document-id> --file <candidate.md> --base-revision <loaded-revision>
```

冲突时重新读当前正文，与本地未保存草稿比较后形成合并候选；不要把最新 revision 简单填到旧内容上强行覆盖。Agent 保留候选正文并核对外部变化；工作台仅显示已保存内容。业务正文保存成功后，即使导航维护失败也保留正文，维护结果独立报告；修复后运行 `refresh`，无需再次保存正文。

`requirement` 显式执行 add/split/merge/move/remove；用 `--parts-file` 提供新需求数组，每项至少有 `title` 和 `content`，可含 `priority/sourceIds/dependsOn`。提供 `--base-revision` 时使用整数项目修订。关系变更以整个 `relations.json` 候选写入，先读取现有值避免删除别人的关联。

注册 Demo 候选的 JSON 示例：

```json
{"id":"DEMO-ORDERS-1", "title":"订单跨模块演示", "path":"demos/DEMO-ORDERS-1", "entryHtml":"index.html", "runId":"RUN-实际任务ID", "status":"candidate", "evidence":{}}
```

上述 `artifact` 登记用于不可变完整产物，包括 candidate；注册后的文件和身份不能原地改写或重用。首次制作可用 `demo-finalize` 一次登记和收尾，后续普通调整优先使用下面的工作稿命令。工作稿只能经专用命令推进修订，不能用 `artifact` 覆盖登记。未完成成果通过 `run-finish --outputs-file` 的 `paths` 保存即可。`runId` 关联真实任务输入；不杜撰占位 runId。只有适用证据支持才能标 current。

## Demo 工作稿

已有 Demo 的日常修改使用同一工作稿，输入仍按轮次固定：

```bash
python3 -B <skill-dir>/scripts/flow.py demo-edit <project-dir> --requirements <IDs...> --change-file <change.json>
python3 -B <skill-dir>/scripts/flow.py demo-save <project-dir> <run-id> --file <payload.json>
```

`demo-edit` 创建任务并返回 `draftId`、`artifactId`、`draftRevision`、`beforeRevision` 和 `path`；`draftRevision` 是修改前的修订，初始为 0，首次保存后为 1。首次复制原冻结产物，后续复用同一工作稿编号和路径。按命令返回路径修改文件，不修改原冻结目录。本轮任务记录 `kind:"draft-edit"`；工作稿产物记录 `kind:"working-draft"`、`draftRevision`、`activeRunId` 和 `editStatus`（`editing`、`ready`，或中断后有未保存改动的 `needs-review`）。一个工作稿同时只允许一个编辑任务，发生冲突时检查当前任务，不用旧输入覆盖。

`change.json` 与旧路径的 `run-start --change-file` 相同。Tier 3 开始前，若当前已保存修订尚未冻结，运行时自动保存检查点。未保存改动应先完成当前任务或明确恢复，不把它们冒充已保存修订。额外业务依据用 `--documents` 加入；输入变化仍需判断影响。

`demo-save` 可使用空对象 `{}` 保存修改；`artifact` 可选，`id`、`path`、`runId` 由任务固定，不可改成另一产物。省略 `status` 时保存为 `candidate`，不新增验证结论；明确保存为 `verified/current` 必须提供适用的 `evidence.frameworkReview`。框架依据仍有效时可以复用其真实来源，不能声称本轮重新观察。例如仅修改文案：

```json
{
  "artifact": {"title": "订单工作稿", "entryHtml": "index.html"},
  "bindings": [],
  "flows": [],
  "outputs": {"summary": "修改页面标题并完成静态检查；受影响旧截图待复核"}
}
```

`bindings`、`flows` 只提供本次新增或更新条目，按 ID 合并；空数组保留已有条目。实际重新验证的绑定使用真实 evidence、`verified:true` 和 `reverify:true`；完整依赖范围及继承规则见[页面状态入口](demo-and-change.md#页面状态入口)。运行时以 `verificationDraftRevision` 记录工作稿证据的修订，受影响页面不会因重新保存而继续标为已验证。Tier 0 可保存静态检查结果并保留截图待复核。

保存产生新 `draftRevision`，返回 `artifactId`、`path`、`validation` 并结束本次任务；失败不登记成功修订，工作文件和运行中的任务保留，修正后可用同一任务重试。修订保存文件清单及新增内容对象，未改变的字节复用，不生成每轮独立完整 Demo。它提供恢复依据，不能替代长期交付版本；`measurements` 仍只填写实际计量结果。

冻结与恢复：

```bash
python3 -B <skill-dir>/scripts/flow.py demo-freeze <project-dir> --artifact <draft-id> --title "订单评审版 v1"
python3 -B <skill-dir>/scripts/flow.py demo-restore <project-dir> <draft-id> --revision <n>
```

首次可用、提交评审、确认里程碑或明确保存 Demo 版本时冻结。`demo-freeze` 复制已保存工作稿为不可变完整产物，记录 `frozenFrom:{artifactId,revision}`；同一修订已经冻结时复用并返回 `reused:true`。工作稿及当前指针保持原样，最近冻结版由 `lastFrozenArtifactId` 记录。冻结保留 candidate 或真实验证状态，不证明用户确认，不自动发布或保存项目快照。

`demo-restore` 找回指定工作稿修订并形成新修订，旧修订不被覆盖，恢复后的 PRD 有效性仍需核对。修订号递增，包含恢复检查点时可以跳号。有活动编辑任务时，冻结、恢复和另起编辑均会拒绝；先完成保存，或用 `run-finish --status partial|failed` 结束当前任务再恢复。恢复前有未保存文件时，运行时先保存其去重恢复数据，并返回 `recoveryCheckpoint` 路径和可恢复的 `recoveryRevision`，不直接丢弃这些字节。

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

命令原子执行产物登记、关联更新、定向校验与任务结束；失败回滚登记状态并保留 Demo 工作目录，警告如实返回。单独的 `artifact` 仍不自动结束任务。不可变产物、输入过期和基线冲突规则均保留。

Demo 命令及检查返回 `commandMetrics`：`elapsedMs` 是命令内部耗时，`inventoryCalls/hashedBytes` 是目录完整性检查次数与读取字节，`copiedFiles/copiedBytes` 是复制量，不代表全部文件 I/O。任务的 `metrics` 保存准备输入、准备 Demo 和收尾的阶段记录。若实际计量，可在 payload 添加 `measurements:{"editingMs":1234,"browserVerificationMs":5678,"verifiedPages":1}`，省略未计量项。命令时间不包括 Agent 思考、进程启动与工具外的浏览器操作，不能据此推算完整任务耗时。

## 版本与恢复

`snapshot --name` 固定当前 PRD、关系、完整 Demo、图片及验证状态，也保存任务记录、所有任务的固定输入和 `outputs.paths` 声明的部分成果。输出副本放在历史的 `.prototype-flow/run-outputs/`，缺失输出保留警告。版本允许未完成项，但如实记录缺失/未验证；保留文件清单及校验值。`compare --from <version-id> --to working` 比较需求、正文与截图；工作台可读历史版本。

`restore <root> <version-id>` 先严格校验目标历史，再保存恢复前备份并形成新工作修订。恢复前备份允许当前 Demo 或固定输入损坏/缺失，保存实际可读字节、原登记记录及损坏说明，不要求先修好当前 Demo；普通快照仍拒绝篡改。备份标记 `recoveryBackup`，含损坏产物的备份仅供找回文件，不能作为完整恢复目标。历史自身不可编辑；当前飞书绑定、同步基线和实时任务保持不变。

恢复 Demo 或中断任务时用 `state <project-dir> --section runs` 定位，已知编号加 `--id <run-id>`；查看历史任务加 `--version <version-id>`。工作稿任务用 `demo-edit` 接续或 `demo-restore` 恢复修订；`run-resume` 不接受 `kind:"draft-edit"`，避免复制出不持有工作稿编辑权的任务。旧流程的 `run-resume <project-dir> <run-id> --version <version-id>` 从历史固定输入和输出创建新任务，返回 `resumedFrom` 与 `recoveredOutputs`，不覆盖实时任务或原输出。省略版本则从当前任务续作。随后用 `demo-prepare` 将恢复的 Demo 准备到新的 `demos/` 目录，选择与约束见[共享框架](demo-framework.md#后续复用)。新任务输入仍可能落后于当前 PRD，登记产物时继续计算过期状态。旧版本若没有保存任务记录，会明确报缺失，不虚构恢复上下文。

## 用户流程画布

工作台默认进入需求结构，图标侧栏依次为用户流程、PRD 与需求、项目总览、待办与任务。顶部保留版本选择，当前或最近任务摘要放入结构图的项目根节点，不另设任务横条。项目总览从模块工作流开始，保留版本历史与资料依据，移除四项统计卡片。独立“待办与任务”页面包含“待处理”和“任务记录”两个表格 Tab；待处理表展示事项、关联对象和原因，任务记录表只保留阶段、状态、开始时间、结束时间和“查看详情”。处理范围、产物、依据修订、阻碍与结果等统一在右侧详情抽屉查看，不展开表格行。支持按任务、模块或需求定位过滤，任务深链自动打开对应抽屉；跨模块任务只显示一条记录，查看操作不修改数据。

工作台「用户流程」以无限画布展示项目 → 全部 PRD → 各 PRD 需求的结构，不需要先登记 `flows`。空 PRD 和未关联页面的需求也会显示；分支连线表示归属关系，不表示业务执行顺序。支持查看详情、拖动排布、平移、缩放、适应视图、重置排布、缩略地图，以及 PRD/截图/Demo 联动。

卡片依次显示图标与标题、描述、状态与类型标签；需求卡片第三行右侧的复制图标复制名称和稳定编号，不打开抽屉。已确认需求需要重新分析时，“内容待复核”优先于旧确认标签，未确认草稿则显示“待分析”；需求内容确认与模块交付验收分别表达。搜索仅匹配当前版本画布中的节点名称与编号，保留全部节点并高亮匹配项，按 Enter 定位下一个。

相关 PRD、需求卡片另用任务标签和描边体现记录状态：进行中采用绿色描边与沿边框流光，受阻采用红色静态描边，同卡片受阻优先；完成后恢复普通描边。点击任务摘要或标记可查看对应记录和阻碍。状态来自 Agent 已保存的任务，不推测实时进程，任务完成也不代表需求或交付已确认。历史版本将进行中标为“快照时进行中”并使用静态描边；系统要求减少动态效果时也停用流光。

点击项目、PRD 或需求卡片查看对应详情；需求详情包含正文、验收条件、关联页面截图、依赖和资料出处，底部固定按钮可跳转至 PRD 中的需求位置。截图支持放大，关联页面标题直接进入工作台内的 Demo 演示；失效产物禁止 Demo 跳转。既有 `flows[].steps` 和页面绑定仍作为项目数据保留，由关系文件维护，画布不提供手动连线来改变业务语义。

顶部可切换需求结构和 Demo 演示模式，标题栏下方展示独立预览源的 Demo。顶部中间的选择器显示 PRD、需求和页面状态，搜索位于可收起的选择列表内；点击单一有效状态的需求直接切换，多状态需求展开后选择，没有有效页面时说明缺口，不猜测路由。切换模式或暂时离开用户流程会保留已加载 Demo；选中状态表示最近选择的目标，不自动跟随 Demo 内部交互。历史版本使用对应快照资源，不回退到当前稿。

拖动位置和视口仅保存在当前浏览器的项目/版本隔离布局中，不改变 PRD、关系、快照或飞书内容。该偏好不跨浏览器来源（含本地端口）共享。历史内容只读，历史画布仍可临时浏览和排布。切换版本时等待对应数据后再展示，避免混用当前与历史页面。

工作台低频检查轻量变化标识，回到页面时也检查；有变化才重新读取项目，保留仍有效的审查位置。历史版本保持固定内容。最近读取时间、连接失败提示与复制审查上下文仅显示在需求结构画布右下角固定浮层，不随平移缩放；其他视图不显示这组辅助操作。连接失败时保留旧内容。复制审查上下文包含版本、需求和本机定位链接；链接仅供当前电脑使用，且需要对应服务仍在运行。内部 PRD 链接在阅读器定位，来源资料按当前或历史版本读取。所有这些操作均不落盘项目业务数据。
