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
├── demos/<artifact-id>/      独立完整 Demo 和资源
└── versions/<version-id>/    不可变项目快照
```

需要打开工作台时运行 `serve <project-dir>`。产品 Demo 在另一 loopback origin 下只读预览。工作台 API 有会话令牌和来源检查，仅提供读取；POST、PUT、PATCH、DELETE 返回 405，Agent 通过本地 CLI 执行写入。不要把本地服务器绑定至公网或向他人分享 API 令牌。

目录与导航由内建运行时维护，无需外部文档维护 Skill。`00-ai-context/DOC_MAP.md` 是统一导航；旧工具生成的 `INDEX.md` 转为导航指针，用户自写 INDEX 保留。已有 `AI_GUIDE.md` 仅替换已知过期维护指引，保留自定义补充，不创建新指南。旧 dashboard 和 `prdlib:related` 正文块不删除、不再生成或回写；历史快照不参与当前文档库维护。

## 数据权威及核心结构

- `.prototype-flow/project.json`：项目身份、模块、文档路径和整数项目修订；格式见 `schemas/project.schema.json`。
- 当前 Markdown：可编辑的业务要求。`document.revision` 是正文 SHA-256，`businessHash` 区分业务内容与已知工具维护字段。
- 需求索引：从 `pf:req` 内容块重建。块元数据见 `schemas/requirement-block.schema.json`。
- `relations.json`：人工语义关联；格式见 `schemas/relations.schema.json`。刷新需求不重新推断依赖。
- `artifacts.json`：完整产物与输入依据。单项注册格式见 `schemas/artifact.schema.json`。
- `sources.json`：来源登记和已提取内容；文档依据引用来源 ID，不把登记当作已完成分析。
- `runs/`：固定一次任务输入和实际进度；`run-start` / `run-finish` 管理，`run-resume` 创建独立续作。原始完整文档与决定产物有效性的 `documentHashes` 分开保存。
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

`state`、`document`、`compare` 和 `validate` 不创建或写回项目文件。`state` 的项目及模块状态按当前文件计算；`storedRevision` 是已落盘修订，`refreshRequired:true` 表示返回的变化尚未持久化。只读检查到此报告；获准维护后执行 `refresh` 才更新索引、项目修订和确认阶段。工作台 GET 查询同样只读。

新建单份 PRD 使用 `intake <project-dir> --file <payload.json>`：一次保存新模块、来源、公共正文和需求块，设为 `draft`，收尾一次并返回维护及结构检查结果。候选格式见 [需求与资料](requirements.md#一次入库)。该命令不更新已有模块；更新正文或拆合已有需求继续使用下面的操作。

`intake` 自带本次 PRD 的结构检查。单独补检文档使用 `validate <project-dir> --stage prd`，检查文档、需求 ID、来源与引用；默认 `validate <project-dir>` 保留全项目检查，包括 Demo 关联、资源和版本。按本次范围选择，纯 PRD 入库不因尚无页面截图而进入 Demo 工作。

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

`artifact --file` 注册后产物身份不可复用，更新注册新 ID。`runId` 关联真实任务输入；不杜撰占位 runId。只有观察与证据支持才能标 current。将当前产物切换和更新关联作为同一任务完成，途中保持明确候选状态。

## 版本与恢复

`snapshot --name` 固定当前 PRD、关系、完整 Demo、图片及验证状态，也保存任务记录、所有任务的固定输入和 `outputs.paths` 声明的部分成果。输出副本放在历史的 `.prototype-flow/run-outputs/`，缺失输出保留警告。版本允许未完成项，但如实记录缺失/未验证；保留文件清单及校验值。`compare --from <version-id> --to working` 比较需求、正文与截图；工作台可读历史版本。

`restore <root> <version-id>` 先严格校验目标历史，再保存恢复前备份并形成新工作修订。恢复前备份允许当前 Demo 或固定输入损坏/缺失，保存实际可读字节、原登记记录及损坏说明，不要求先修好当前 Demo；普通快照仍拒绝篡改。备份标记 `recoveryBackup`，含损坏产物的备份仅供找回文件，不能作为完整恢复目标。历史自身不可编辑；当前飞书绑定、同步基线和实时任务保持不变。

恢复 Demo 或中断任务时用 `state <project-dir> --full` 读取实时任务；查看历史任务加 `--version <version-id>`。`run-resume <project-dir> <run-id> --version <version-id>` 从历史固定输入和输出创建新任务，返回 `resumedFrom` 与 `recoveredOutputs`，不覆盖实时任务或原输出。省略版本则从当前任务续作。新任务输入仍可能落后于当前 PRD，登记产物时继续计算过期状态。旧版本若没有保存任务记录，会明确报缺失，不虚构恢复上下文。

## 用户流程画布

工作台「用户流程」以无限画布展示项目 → 全部 PRD → 各 PRD 需求的结构，不需要先登记 `flows`。空 PRD 和未关联页面的需求也会显示；分支连线表示归属关系，不表示业务执行顺序。支持查看详情、拖动排布、平移、缩放、适应视图、重置排布、缩略地图，以及 PRD/截图/Demo 联动。

点击项目、PRD 或需求卡片查看对应详情；需求详情包含正文、验收条件、关联页面截图、依赖和资料出处，可跳转至 PRD 中的需求位置。截图支持放大和跳转 Demo；失效产物禁止 Demo 跳转。既有 `flows[].steps` 和页面绑定仍作为项目数据保留，由关系文件维护，画布不提供手动连线来改变业务语义。

拖动位置和视口仅保存在当前浏览器的项目/版本隔离布局中，不改变 PRD、关系、快照或飞书内容。该偏好不跨浏览器来源（含本地端口）共享。历史内容只读，历史画布仍可临时浏览和排布。切换版本时等待对应数据后再展示，避免混用当前与历史页面。
