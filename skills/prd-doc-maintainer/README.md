# PRD Doc Maintainer 技能说明

`prd-doc-maintainer` 用于搭建、整理和维护日常 PRD 文档库。它的脚手架会优先照顾 AI 可读性：生成 AI 快速查询地图、稳定的目录约定、机器可读元数据、自动关联文档区块和统一索引，方便 AI 在修改文档前快速定位上下文。它还支持归档历史文档、记录大型变更版本日志，并生成一个不依赖运行环境的静态 HTML 数据看板。

## 技能目录结构

```text
prd-doc-maintainer/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── assets/
│   └── dashboard-template.html
├── references/
│   └── metadata-guide.md
└── scripts/
    └── prd_library.py
```

各文件作用：

- `SKILL.md`：技能入口说明，告诉 Codex 何时使用该技能，以及维护 PRD 文档库的推荐流程。
- `README.md`：面向使用者的中文说明文档。
- `agents/openai.yaml`：技能在 Codex UI 中展示的名称、简介和默认提示词。
- `assets/dashboard-template.html`：静态数据看板模板，最终会被渲染为 `dashboard/index.html`。
- `references/metadata-guide.md`：PRD 元数据、关联文档和 changelog 规范参考。
- `scripts/prd_library.py`：核心自动化脚本，负责脚手架、索引、归档、关联同步、变更记录和看板生成。

## 生成后的 PRD 文档库结构

运行脚手架命令后，会在目标目录中生成：

```text
<library-dir>/
├── README.md
├── INDEX.md
├── CHANGELOG.md
├── .prdlib.json
├── 00-ai-context/
│   ├── AI_GUIDE.md
│   └── DOC_MAP.md
├── 01-active/
├── 02-archive/
├── 03-research/
├── 04-decisions/
├── 05-prototypes/
│   └── README.md
├── templates/
│   └── prd-template.md
└── dashboard/
    └── index.html
```

推荐约定：

- `00-ai-context/`：AI 快速查询入口，存放 AI 使用指南和自动生成的文档地图。
- `01-active/`：存放正在编写、评审、已批准或仍在维护的 PRD。
- `02-archive/`：存放已废弃、已归档或被新版替代的 PRD。
- `03-research/`：存放用户研究、竞品分析、调研记录等材料。
- `04-decisions/`：存放决策记录、ADR、关键方案取舍说明。
- `05-prototypes/`：存放原型图、线框图、流程截图、设计导出图等视觉材料。
- `templates/`：存放 PRD 模板。
- `dashboard/index.html`：文档库使用情况看板，可直接用浏览器打开。

## AI 可读性设计

脚手架会生成 `00-ai-context/`，这是给 AI 使用的轻量入口，不是业务需求的唯一事实来源。

关键文件：

- `00-ai-context/AI_GUIDE.md`：告诉 AI 修改文档前应该先读什么、如何保持元数据和关联关系。
- `00-ai-context/DOC_MAP.md`：每次刷新时自动生成，包含文档路径、标题、状态、负责人、产品线、更新时间、标签和关联文档。

推荐 AI 查询顺序：

1. 先读 `00-ai-context/DOC_MAP.md`，快速判断哪些文档相关。
2. 再读 `INDEX.md`，确认完整目录。
3. 只打开相关 PRD、研究记录、决策记录和原型材料，避免无关上下文干扰。
4. 修改后运行 `refresh --sync-related --dashboard`，同步索引、AI 文档地图、关联文档和看板。

## 常见提示词示例

可以直接把下面的提示词发给 Codex，并按实际路径替换 `<library-dir>`、文档名或功能名。

### 1. 创建新的 PRD 文档库

```text
使用 $prd-doc-maintainer 在 <library-dir> 创建一个新的 PRD 文档库脚手架。要求目录适合 AI 快速查询和后续维护，并生成初始索引、AI 文档地图和 HTML 看板。
```

### 2. 查看文档库现状

```text
使用 $prd-doc-maintainer 检查 <library-dir> 的 PRD 文档库现状。请先阅读 00-ai-context/DOC_MAP.md，再查看 INDEX.md，最后总结当前活跃 PRD、归档 PRD、缺少 owner/status/updated 的文档，以及需要补充关联关系的文档。
```

### 3. 新增一篇 PRD

```text
使用 $prd-doc-maintainer 在 <library-dir> 中新增一篇「会员积分体系」PRD。请使用 templates/prd-template.md 作为基础，放到 01-active/，补齐 YAML frontmatter，并根据已有研究、决策记录和原型图建立 related 关联。完成后刷新索引、AI 文档地图、关联文档和看板。
```

### 4. 修改已有 PRD

```text
使用 $prd-doc-maintainer 修改 <library-dir> 中关于「支付流程」的 PRD。请先读 00-ai-context/DOC_MAP.md 找到相关 PRD、研究记录、决策记录和原型图，再修改需求内容。修改后更新 updated/version/related，必要时记录 CHANGELOG，最后运行 refresh --sync-related --dashboard。
```

### 5. 同步关联文档

```text
使用 $prd-doc-maintainer 检查 <library-dir> 中所有与「登录注册」相关的文档。请根据 frontmatter、Markdown 链接、正文提及和 05-prototypes/ 中的原型资源补齐 related 关系，并刷新自动关联区块、INDEX.md、00-ai-context/DOC_MAP.md 和 dashboard/index.html。
```

### 6. 归档过期 PRD

```text
使用 $prd-doc-maintainer 将 <library-dir> 中已经被新版替代的「旧版结算页 PRD」归档。请移动到 02-archive/<year>/，更新 status/archived_at/updated，在 CHANGELOG.md 记录归档原因，并刷新索引、AI 文档地图、关联文档和看板。
```

### 7. 记录大型版本变更

```text
使用 $prd-doc-maintainer 为 <library-dir> 中「企业工作台 PRD」记录一次大型变更：版本从 1.4.0 升级到 2.0.0，主要变化是新增多角色权限、审批流和数据看板。请更新相关 PRD 元数据，补充 CHANGELOG.md，并同步关联文档与看板。
```

### 8. 整理原型图

```text
使用 $prd-doc-maintainer 整理 <library-dir> 的原型图。请把散落的原型图片、流程截图和 PDF 原型说明移动或归类到 05-prototypes/，按 feature-name-flow-v1.png 这类规则命名，并把相关 PRD 的正文链接和 related 字段补齐。
```

### 9. 生成文档库数据看板

```text
使用 $prd-doc-maintainer 为 <library-dir> 重新生成静态 HTML 数据看板。要求 dashboard/index.html 可以直接用浏览器打开，并且数据来自当前 PRD、归档文档、关联关系和 CHANGELOG。
```

### 10. 做一次文档库维护巡检

```text
使用 $prd-doc-maintainer 对 <library-dir> 做一次 PRD 文档库维护巡检。请检查缺失 frontmatter 的文档、过期 updated 日期、孤立 PRD、没有被引用的原型图、未记录 changelog 的大型变更迹象，并给出可执行的修复清单。若可以安全修复，请直接修复并刷新索引、AI 文档地图和看板。
```

## 使用方法

以下命令中的 `<library-dir>` 替换为你的 PRD 文档库路径。

### 1. 快速搭建 PRD 文档库

```bash
python scripts/prd_library.py scaffold <library-dir>
```

该命令会创建标准目录、`INDEX.md`、`CHANGELOG.md`、`.prdlib.json`、PRD 模板和初始看板。
同时会创建 `00-ai-context/` 和 `05-prototypes/`，分别用于 AI 快速查询和原型图存放。

### 2. 刷新索引目录

```bash
python scripts/prd_library.py refresh <library-dir>
```

该命令会扫描文档库中的 Markdown 文档，并重新生成 `INDEX.md`。

### 3. 同步关联文档并更新看板

```bash
python scripts/prd_library.py refresh <library-dir> --sync-related --dashboard
```

该命令会：

- 重新生成 `INDEX.md`
- 重新生成 `00-ai-context/DOC_MAP.md`
- 检索 `related` 元数据、Markdown 链接和正文中的文档标题/文件名引用
- 更新每篇相关文档中的自动关联区块
- 重新生成 `dashboard/index.html`

自动关联区块格式如下：

```markdown
<!-- prdlib:related:start -->
## Related Documents

- [示例文档](../01-active/example.md)
<!-- prdlib:related:end -->
```

建议不要手动修改这个区块；如需补充人工说明，可以写在区块外。

### 4. 自动归档文档

```bash
python scripts/prd_library.py archive <library-dir> <doc-path> --reason "已由新版 PRD 替代"
```

该命令会：

- 将文档状态更新为 `archived`
- 添加 `archived_at` 和新的 `updated` 日期
- 移动到 `02-archive/<year>/`
- 在 `CHANGELOG.md` 中记录归档原因
- 刷新索引、关联文档和看板

### 5. 记录大型变更日志

```bash
python scripts/prd_library.py record-change <library-dir> \
  --title "支付流程 PRD" \
  --version "2.0.0" \
  --summary "扩展多支付方式和异常处理场景" \
  --doc 01-active/payment-flow.md \
  --author "产品团队"
```

适合记录以下类型的变更：

- PRD 版本升级
- 需求范围、指标、流程、权限、计费、隐私或依赖发生重要变化
- 已批准或上线中的 PRD 被归档、废弃或替代
- 多篇关联文档需要同步调整

### 6. 单独生成静态看板

```bash
python scripts/prd_library.py dashboard <library-dir>
```

输出文件为：

```text
<library-dir>/dashboard/index.html
```

该文件内嵌 CSS 和数据，不依赖 Node、Python 服务或外部资源，直接用浏览器打开即可查看。

## 原型图存放

将原型图、线框图、流程截图、设计导出图、PDF 原型说明等文件放到：

```text
<library-dir>/05-prototypes/
```

推荐命名：

```text
feature-name-flow-v1.png
feature-name-mobile-v1.jpg
feature-name-wireframe-v1.pdf
```

在相关 PRD 中用相对路径引用：

```markdown
![支付流程原型](../05-prototypes/payment-flow-v1.png)
```

如果原型图与某个 PRD 强相关，也可以写入 frontmatter 的 `related`：

```markdown
related:
  - ../05-prototypes/payment-flow-v1.png
```

## PRD 元数据格式

建议每篇 PRD 使用 YAML frontmatter：

```markdown
---
title: 支付流程优化 PRD
status: draft
owner: Ada
product: Payments
version: 0.3.0
updated: 2026-06-08
tags: [payment, checkout]
related:
  - ../04-decisions/adr-payment-provider.md
  - ../05-prototypes/payment-flow-v1.png
---
```

常用字段：

- `title`：文档标题。
- `status`：文档状态，建议使用 `draft`、`review`、`approved`、`active`、`paused`、`archived`、`superseded`。
- `owner`：负责人或负责团队。
- `product`：所属产品、业务线或功能模块。
- `version`：文档版本。
- `updated`：最后更新时间，格式为 `YYYY-MM-DD`。
- `tags`：标签列表。
- `related`：相关文档路径列表。

## 推荐工作流

1. 新建文档库时运行 `scaffold`。
2. AI 修改文档前，先读 `00-ai-context/DOC_MAP.md`，再打开相关文档。
3. 编写或修改 PRD 后，运行 `refresh --sync-related --dashboard`。
4. 大型变更先运行 `record-change`，再检查 `CHANGELOG.md`。
5. 文档废弃或被替代时运行 `archive`。
6. 原型图放入 `05-prototypes/`，并从相关 PRD 中引用。
7. 日常查看 `INDEX.md`、`00-ai-context/DOC_MAP.md` 和 `dashboard/index.html`，快速了解文档库状态。
