# 本地运行时与数据

运行时要求 Python 3.9+，维护脚本只使用标准库。预构建工作台随 Skill 分发，打开项目无需构建前端。先运行 `python3 -B <skill-dir>/scripts/flow.py --help`，需要某个命令时查看其子命令帮助。

## 接入项目

在项目实际根目录初始化：

```bash
python3 -B <skill-dir>/scripts/flow.py init <project-dir> --name "项目名称" --library-root prd-library --maintainer-path <prd-doc-maintainer-dir>
python3 -B <skill-dir>/scripts/flow.py serve <project-dir>
```

已有文档库可把 `--library-root` 指向项目内现有目录；先检查目录与文档再执行，初始化会给接入 PRD 补稳定文档身份。文档库不能就是项目根目录，不能包含 `versions/`。重复 init 返回既有项目，不重置内容。飞书模式 `--mode feishu` 不自动登录、绑定或写入云端。

典型项目布局：

```text
project/
├── prd-library/               当前 PRD 及 maintainer 约定结构
├── .prototype-flow/          当前项目清单、索引、关系、任务及同步账本
├── demos/<artifact-id>/      独立完整 Demo 和资源
└── versions/<version-id>/    不可变项目快照
```

产品 Demo 在另一 loopback origin 下只读预览。工作台 API 有会话令牌和来源检查，不将写入接口交给 Demo 或来源文档。不要把本地服务器绑定至公网或向他人分享 API 令牌。

## 数据权威及核心结构

- `.prototype-flow/project.json`：项目身份、模块、文档路径和整数项目修订；格式见 `schemas/project.schema.json`。
- 当前 Markdown：可编辑的业务要求。`document.revision` 是正文 SHA-256，`businessHash` 区分业务内容与已知工具维护字段。
- 需求索引：从 `pf:req` 内容块重建。块元数据见 `schemas/requirement-block.schema.json`。
- `relations.json`：人工语义关联；格式见 `schemas/relations.schema.json`。刷新需求不重新推断依赖。
- `artifacts.json`：完整产物与输入依据。单项注册格式见 `schemas/artifact.schema.json`。
- `sources.json`：来源登记和已提取内容；文档依据引用来源 ID，不把登记当作已完成分析。
- `runs/`：固定一次任务输入和实际进度；`run-start` / `run-finish` 管理。
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

浏览器测试、AI 审查或产物登记不会自动升级为用户已确认。需求、共享正文或已声明依赖变化时，受影响的 `confirmed` 模块自动回到 `review`，原确认与失效原因保留在阶段历史；已经处于 draft、demo 或 validation 等手动阶段的模块保持原阶段。纯工具维护区域刷新不会撤销确认。此处记录状态不新增审批流程，继续执行当前已授权范围。

## 保存与变更

`document <root> <id>` 返回当前完整内容及修订。候选正文保存到项目临时文件，再执行：

```bash
python3 -B <skill-dir>/scripts/flow.py save <project-dir> <document-id> --file <candidate.md> --base-revision <loaded-revision>
```

冲突时重新读当前正文，与本地未保存草稿比较后形成合并候选；不要把最新 revision 简单填到旧内容上强行覆盖。工作台保留草稿与外部变化提示。业务正文保存成功后，即使 maintainer 失败也保留正文，维护结果独立报告。

`requirement` 显式执行 add/split/merge/move/remove；用 `--parts-file` 提供新需求数组，每项至少有 `title` 和 `content`，可含 `priority/sourceIds/dependsOn`。提供 `--base-revision` 时使用整数项目修订。关系变更以整个 `relations.json` 候选写入，先读取现有值避免删除别人的关联。

注册 Demo 候选的 JSON 示例：

```json
{"id":"DEMO-ORDERS-1", "title":"订单跨模块演示", "path":"demos/DEMO-ORDERS-1", "entryHtml":"index.html", "runId":"RUN-实际任务ID", "status":"candidate", "evidence":{}}
```

`artifact --file` 注册后产物身份不可复用，更新注册新 ID。`runId` 关联真实任务输入；不杜撰占位 runId。只有观察与证据支持才能标 current。将当前产物切换和更新关联作为同一任务完成，途中保持明确候选状态。

## 版本与恢复

`snapshot --name` 固定当前 PRD、关系、完整 Demo、图片及验证状态。版本允许未完成项，但如实记录缺失/未验证；保留文件清单及校验值。`compare --from <version-id> --to working` 比较需求、正文与截图；工作台可读历史版本。

`restore <root> <version-id>` 会先保存当前工作的安全版本，再从历史形成新工作修订。历史自身不可编辑；运行时校验其完整性。当前飞书绑定与同步基线保持不变，之后若要改变云端必须另行执行已授权同步。

已有 Demo、截图、依赖和未完成任务均通过项目数据恢复。恢复任务时优先查看 `state` 的 runs、当前修订、产物输入与差异，再继续未完成工作，不依赖完整聊天记录。

## 用户流程画布

工作台「用户流程」以无限画布展示项目 → 全部 PRD → 各 PRD 需求的结构，不需要先登记 `flows`。空 PRD 和未关联页面的需求也会显示；分支连线表示归属关系，不表示业务执行顺序。支持查看详情、拖动排布、平移、缩放、适应视图、重置排布、缩略地图，以及 PRD/截图/Demo 联动。

点击项目、PRD 或需求卡片查看对应详情；需求详情包含正文、验收条件、关联页面截图、依赖和资料出处，可跳转至 PRD 中的需求位置。截图支持放大和跳转 Demo；失效产物禁止 Demo 跳转。既有 `flows[].steps` 和页面绑定仍作为项目数据保留，由关系文件维护，画布不提供手动连线来改变业务语义。

拖动位置和视口仅保存在当前浏览器的项目/版本隔离布局中，不改变 PRD、关系、快照或飞书内容。该偏好不跨浏览器来源（含本地端口）共享。历史内容只读，历史画布仍可临时浏览和排布。切换版本时等待对应数据后再展示，避免混用当前与历史页面。
