# Demo、页面关联与变化处理

用于生成高保真 Demo、接入已有演示或按最新 PRD 更新。读取当前 demo-design Skill 和本次命中的参考路径，复用已读且仍适用的内容，不复制或改写其产品契约。

## 先限定本次修改

先确定目标、受影响页面或状态及最小充分检查，再固定任务输入。按实际行为影响分级，不按改动文件数，也不因涉及业务语义自动升级：

| Tier | 本次变化 | 默认检查范围 |
| --- | --- | --- |
| 0 | 不改变业务含义的文案 | 精确差异和必要静态检查；不要求浏览器重跑 |
| 1 | 单一父容器的颜色、字号、间距、尺寸或排列 | 一个相关视口、目标区域观察及必要截图 |
| 2 | 边界明确的局部业务规则、交互或状态 | 对应 PRD/契约差异、受影响动作及必要成功/错误路径 |
| 3 | 主要业务模型或公共框架能力变化 | 适用完整流程、受影响代表页面及跨模块路径 |

首次制作按 demo-design 的实际范围选择适用 Tier，并完成首次框架接入。将判断保存为 `run-start --change-file <change.json>`，例如 `{"tier":1,"summary":"调整订单详情按钮间距","affectedBindingIds":["BIND-ORDER-UNPAID"]}`。只列已存在且确实受影响的绑定；新页面可留空。Tier 是本次检查范围声明，不自动证明验证通过。

关联需求、传递依赖、完整正文及来源是理解和固定输入的闭包，不自动成为全部复验对象。共享样式、脚本、数据或依赖变化时扩大受影响范围；无法判断时保守复验。局部修改仍准备新的完整 Demo，保留固定输入与不可变历史，不创建跨轮可变产物。依赖路径、框架用法和任务范围未变化时，复用已准备能力与已有依据，不重复读取全部参考或执行无关全量 `validate`。

## 固定输入并生成

1. 用 `state` 摘要定位模块，通过 `document` 读取本次需求、来源、验收和已知依赖；旧产物和任务用 `state --section artifacts|runs` 查询，单项加 `--id <id>`。按[项目共享框架](demo-framework.md)读取已有规范与完整 Demo；首次生成/接入先提取可执行框架，后续判断是否影响公共能力，需要时准备新框架候选。
2. 用 `run-start --stage demo --requirements <IDs...>` 固定 PRD、需求哈希、项目修订、框架版本和完整基准 Demo；升级框架用 `--framework <id>`。默认保存选中需求、传递依赖、关联流程/页面及所属文档的完整正文与相关来源、图片；其他共享规则文档用 `--documents <document-ids...>` 明确加入。确需全库上下文时加 `--full-context`。运行 `demo-prepare <project-dir> <run-id> --path demos/<new-artifact-id>` 复制固定的框架和业务成果，再继续制作，保留上一套可演示产物。
3. 按上述范围选择 demo-design 适用路径，完成设计、产品契约差异、实现和必要实际验证。独立模块共用导航、公共组件、数据对象身份和业务状态；涉及跨模块的修改验证其连续操作。
4. 普通任务先完成修改和适用检查，再用 `demo-finalize <project-dir> <run-id> --file <payload.json>` 一次登记不可变完整产物、更新本次关联、定向校验并结束任务；格式见[运行时](runtime.md#demo-一次收尾)。填写本次检查或有来源的继承证据，框架依据见 `evidence.frameworkReview`。只有适用证据支持才用 `verified` 或 `current`；`activated:true` 表示本地默认框架和 Demo 已一起切换。输入过期不切换，基线被其他任务推进时先比较差异。产品契约场景、规则、状态、UI 的关系保存在旁路数据，不展示在产品 Demo 中。
5. 一次收尾失败会回滚登记并保留工作目录。中断成果用 `run-finish --status partial|failed` 的 `outputs.paths` 保存，不必提前登记候选。确需单独登记 `artifact` 时，它不会自动结束任务，仍须更新关联并 `run-finish`；候选也冻结文件和身份，后续修改使用新目录和新 ID。输出可用 `{"artifactIds":["实际产物ID"],"bindingIds":["实际绑定ID"],"paths":["项目内输出路径"]}`，未登记的部分成果须在 `paths` 中声明，才能随快照保存。无框架的显式修订登记只保留旧数据兼容。

`prototype-contract.json` 遵循 demo-design 当前 schema；新增项目需求 ID 和版本字段写入 prototype-flow 的清单，不能塞进下游 schema。

## 页面状态入口

每条截图绑定包括 `artifactId/screenId/stateId/route/fixtureId/screenshot`，其中 `route` 是相对 Demo 根目录的入口文件及查询/哈希，`screenshot` 是项目内截图路径。不要存储临时端口。

示例：`index.html?screen=order-detail&state=unpaid&fixture=order-001`。具体参数由该 Demo 定义；工作台只负责安全拼接和打开，不能替 Demo 注入业务状态。Demo 自己要在加载时解析入口、准备完整演示数据，并在刷新时恢复。直达只是第二种入口，从统一导航仍能正常走到同一状态。

一条多步骤路径保存为 `relations.flows`，每个 step 引用需求、对应 binding 或稳定页面状态；模块视图和流程视图引用同一份页面与截图。需求与页面多对多，允许一个需求的成功、错误、取消状态各有截图。

步骤使用 `requirementId`、`bindingId`，或能匹配已有 binding 的 `artifactId/screenId/stateId`。保存校验、影响传播及固定输入使用相同引用解析，无需把步骤需求再重复填进流程顶层 `requirementIds`；该列表可只补充步骤外的关联需求。拆合需求会标记相关步骤待复核，不自动把旧入口迁给新需求。

验证从真实截图入口打开，确认页面状态与截图一致、刷新恢复且可继续跨模块流程。截图存在或 URL 语法合法并不证明此行为。`verified` 与 evidence 仅记录真正执行的检查。

首次登记已验证绑定时，运行时生成 `verificationHash`，固定截图字节、产物身份、需求、入口、页面状态与 fixture。后续变化或旧数据缺少指纹时，读取和检查均显示待复核；重存旧 evidence 不会刷新结论。实际重新验证后，在对应 binding 中提供新证据、`verified:true` 与一次性 `reverify:true`，运行时才建立新指纹。

实际验证时可记录 `verificationScope:{"files":["index.html","styles/order.css","scripts/order.js"],"complete":true}`，文件为 Demo 内完整依赖闭包，须包括共享样式、脚本、数据和资源；不能仅列改动文件。只有能确认依赖完整时才写 `complete:true`。迁移未变化页面到新版 Demo 时，用 `inheritVerificationFrom:"旧绑定ID"` 请求继承，允许沿用同一绑定 ID；不使用 `reverify:true` 冒充新观察。运行时核对来源验证、依赖字节、框架、入口、截图与需求依据，不满足条件则拒绝继承。旧证据没有 scope、动态依赖不能确定或共享文件已改变时，需实际复验后建立新依据。

继承保留原验证来源，本次报告明确哪些检查重新执行、哪些继承。页面文案、视觉或状态改变后，旧截图不能当作最新截图；Tier 0 可完成静态检查并将受影响截图保留为待复核，不为获得已验证标签扩大浏览器工作。

## PRD 变化

正文保存后运行时发现哈希差异并标待分析，沿声明的依赖、共享流程及关联传播；Agent 负责补充隐含依赖与实际影响。纯排版变化可以复用适用证据，描述变化也要判断是否改变业务含义或界面文案。

检查影响时覆盖：规则和字段、权限、入口、加载和错误状态、重复操作、共享数据、公共组件及跨模块路径。删除需求时清理其界面、行为和状态消费者；候选关联和历史引用按需求生命周期处理。

用户在 R12 Demo 制作期间保存 R13 时，完成产物仍标明 R12。比较新旧输入，更新真正受影响部分后重新验证，不覆盖 R13 PRD 或沿用已过期证据。运行失败保留候选、任务输入、已完成输出和错误信息，以 `run-finish --status partial|failed` 记录。恢复从这些记录继续；未明确的业务问题只阻塞依赖它的部分。

中断任务用 `run-resume <project-dir> <run-id>` 创建独立续作；从历史接续加 `--version <version-id>`。输入仍是原固定版本，已声明的输出复制到新任务工作目录，返回 `recoveredOutputs`；原任务、历史和当前同名文件保留。再运行 `demo-prepare` 到新的 `demos/<id>`，优先使用唯一恢复 Demo；多个恢复 Demo 用 `--from-output <recoveredOutputs.path>` 指定。恢复目录用于保留成果，登记使用新 Demo 目录。若最新 PRD 已改变，仍须判断影响，不能把续作自动视为最新。

## 完成程度

`validate --artifacts <IDs...>` / `--bindings <IDs...>` 只检查指定产物或绑定及其必要依据；默认 `validate` 仍检查全项目。`demo-finalize` 已执行本次定向校验，成功后不重复同一检查，除非又有改动或失败。结构检查不证明视觉质量；按 Tier 完成适用浏览器验证，记录实际平台、尺寸、路径、页面状态及截图，不扩大成真机、线上、完整场景或用户验收结论。

CLI 的 `commandMetrics` 记录命令耗时及 I/O 次数、字节，任务的 `metrics` 保存阶段记录。人工修改和浏览器耗时只有实际计量时才在收尾的 `measurements` 填写；用相同改动范围比较结果，不把未计量时间写为零或承诺固定提速比例。

交付完整 Demo 文件夹和入口，说明本地工作台 URL 的使用范围。需要对外分享时按用户授权和 demo-design 当前交付格式提供整个资源闭包；本任务不自动部署网站。
