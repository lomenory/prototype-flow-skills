# 项目共享 Demo 框架

首次生成或接入已有 Demo、后续新增页面、需求影响公共界面时读取。框架是项目自己的可执行设计基础，不是工作台 UI，也不是另一套产品契约。

## 首次固化

首次生成先建立最小公共框架，再用首批页面验证；导入已有 Demo 时读取实际代码、设计文件和渲染结果，从中提取框架并保留原 Demo。不同页面已有冲突时明确采用哪一套，不把冲突原样固化。CLI 不猜测哪些 CSS 或组件属于共享能力。

框架放在 `demo-framework/<framework-id>/`，包含根级 `DESIGN.md`、可运行 HTML 示例入口，以及实际 Token、导航/页面壳、公共组件、公共状态展示和必要资源。业务字段、演示数据、模块页面和业务规则留在 Demo。资源使用包内相对路径，不依赖旧 Demo 目录。`DESIGN.md` 还应说明内容插槽、导航配置、组件用法、扩展点和受保护的约定，不能只有视觉描述。

准备完整候选后，执行 `framework <project-dir> --file <framework.json>`：

```json
{
  "id": "FRAME-V1",
  "title": "项目公共界面框架",
  "path": "demo-framework/FRAME-V1",
  "entryHtml": "index.html",
  "basedOn": null,
  "changeSummary": "提取现有设计 Token、导航和公共组件"
}
```

字段见 `schemas/framework.schema.json`。`basedOn` 必须显式填写：首版为 null，升级为读取到的当前框架 ID；已变化则先比较，不用最新 ID 掩盖旧候选。从已登记产物提取时可填写 `sourceArtifactId`。登记后目录和 ID 不可变，修改使用新目录和新 ID。登记仅创建候选，不切换当前框架。

首次导入尚未登记的完整 Demo 时，将原目录保留在 `demos/<原目录>`，先提取并登记框架，再用 `run-start --stage demo --base-demo demos/<原目录>` 固定原业务成果；非默认入口追加 `--base-entry <入口.html>`。之后同样 `demo-prepare` 到新目录，再迁移公共实现并验证。不需要先把原 Demo 伪报为已验证产物。项目已经有登记产物时使用 `--base-artifact`，避免丢失业务输入依据。

## 后续复用

```bash
python3 -B <skill-dir>/scripts/flow.py run-start <project-dir> --stage demo --requirements <IDs...>
python3 -B <skill-dir>/scripts/flow.py demo-prepare <project-dir> <run-id> --path demos/<new-artifact-id>
```

`run-start` 默认选当前框架与当前完整 Demo；没有当前指针时，仅在框架首版候选或既有 Demo 各自唯一时自动选取。多个候选用 `--framework <id>` 或 `--base-artifact <id>` 指定；缺少框架会阻止 Demo 生成，不影响 PRD 入库。选中的源码、设计文档、文件哈希和当前指针均固定在任务输入中，包括旧 Demo 子目录内的设计文件。候选框架须基于当前框架。

`demo-prepare` 只接受尚不存在的 `demos/<新目录>`：从固定输入复制完整业务 Demo，把框架包放入 `_framework/`，并将框架 `DESIGN.md` 复制到 Demo 根目录。没有既有 Demo 时只准备框架，Agent 创建业务入口。命令自动把工作目录加入任务 `outputs.paths`，中断时可随快照保存。继续原任务时使用已准备目录，或 `run-resume` 找回成果，不重复覆盖目录。

复制只是起点。让业务页面实际使用 `_framework/` 的样式、页面壳和公共组件，保留已有页面、导航、对象身份和跨模块状态。接入旧 Demo 时在新目录迁移样式与组件，检查覆盖冲突；不能仅附带一个未使用的框架包。导航新增菜单若已有配置能力，直接修改业务侧配置，不必升级框架。

## 需求推动框架更新

页面文案、字段和局部业务行为在 Demo 修改；新通用组件、全局 Token、导航结构或页面壳能力进入框架。特殊页面优先用已有扩展点，不把每个特例推广到整个项目。

影响框架时复制当前框架到新版本目录，修改公共实现、`DESIGN.md` 和可运行示例，记录 changeSummary，登记候选，再用 `run-start --stage demo --framework <新ID>` 固定新任务。中途发现框架变化时，原任务以 `run-finish --status partial` 保留成果；创建新任务并移植已完成的业务修改，不修改原固定输入或原框架。把受公共变化影响的模块需求纳入本次范围，验证代表页面和跨模块路径。

实际完成浏览器检查后，产物登记使用对应 `runId`，在 `evidence` 中补充：

```json
{
  "frameworkReview": {
    "summary": "填写实际观察的 Token、导航、公共组件、代表页面和跨模块路径及结果",
    "source": "填写实际截图或验证报告在项目内的定位"
  }
}
```

这只是格式示例，不能当作已完成验证。检查真实渲染、资源引用和适用交互；字节一致不证明页面正在使用框架。

`artifact` 从任务取得框架和基准 Demo ID，校验 `_framework/` 与固定框架的文件清单和内容完全一致、根级 `DESIGN.md` 一致；`verified/current` 需要上述证据记录。具体 Demo 内对框架包的局部修改会被拒绝，应登记新框架版本。

仅当 PRD 输入仍有效、框架和基准 Demo 当前指针没有被其他任务推进时，登记已验证 Demo 会一起切换当前框架和当前 Demo；返回 `activated:true` 才说明切换成功。候选或输入过期的产物不推进指针。基线冲突保留当前版本及工作目录，先比较差异再创建新任务；写入失败会回滚登记文件，不留下仅框架已切换的状态。此切换是本地默认版本选择，不是部署或用户验收。

旧页面继承原 Demo 的需求和文档哈希，本次选中输入覆盖更新其依据。旧页面已落后于 PRD 时，复制不会被伪报为最新；应将相关需求纳入任务并真正更新。

## 历史与兼容

- 框架版本、当前选择、固定输入和 Demo 随快照保存；恢复先备份，任务续作沿用原框架和原业务 Demo。
- 历史 Demo 内置当时的 `_framework/`，不链接项目中的可变目录。整个 Demo 文件夹包含框架资源。
- 旧项目和快照不自动改写；未绑定框架的 Demo 仍可查看、校验和恢复，显示 `framework-unbound` 提示。再次生成前提取框架，并以原 Demo 为业务基线。
- 仅接入已有 Demo 时也先提取框架，在新目录完成绑定和验证。无框架的旧记录登记仅保留历史数据与已验证固定样例兼容，不用非 demo 阶段绕过新任务的框架要求。
- 运行时负责路径、资源清单、版本、输入和证据字段检查；Agent 负责框架提取、影响判断、实际使用和浏览器验证。不能把结构检查当作视觉或业务正确的证明。
