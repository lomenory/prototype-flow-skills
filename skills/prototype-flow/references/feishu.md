# 本地 PRD → 飞书共享展示

适用于项目选择本地维护、飞书展示的模式。本地 Markdown 是唯一维护源，无双向合并、自动回流、在线编辑、通知发送或分享权限自动调整。

## 初始化与权限

读取可用的 `use-feishu-cli`。先复用已有配置；只有用户请求初始化且确有缺失时，按当前 CLI 指导完成配置或必要授权。不要把 auth token、app secret 或授权码存入项目。`flow.py feishu configure` 只记录项目目标，并非账号初始化。

首次实际飞书任务或 CLI 版本变化时，通过 CLI 读取匹配帮助与内置 skill，而不是从旧笔记猜参数：

```bash
lark-cli skills read lark-shared
lark-cli skills read lark-doc references/lark-doc-fetch.md
lark-cli skills read lark-doc references/lark-doc-create.md
lark-cli skills read lark-doc references/lark-doc-update.md
lark-cli skills read lark-doc references/lark-doc-md.md
lark-cli skills read lark-doc references/lark-doc-xml.md
lark-cli skills read lark-doc references/lark-doc-media-insert.md
```

仅在实际创建/更新时读取这些文档指出的 style/workflow 引用。身份默认为 `user`；确需应用身份时显式指定并说明实际创建归属。配置和认证执行 use-feishu-cli 的当前流程，不由工作台或同步适配器自行申请权限。

## 配置、绑定与计划

```bash
python3 -B <skill-dir>/scripts/flow.py feishu configure <project-dir> --parent-token <folder-or-wiki-node-token> --navigation-title "项目 PRD"
python3 -B <skill-dir>/scripts/flow.py feishu bind <project-dir> <document-id> --remote <docx-or-wiki-url>
python3 -B <skill-dir>/scripts/flow.py feishu prepare <project-dir> --documents <document-ids...> --include-navigation
python3 -B <skill-dir>/scripts/flow.py feishu status <project-dir>
```

`bind` 只读取云端并保存稳定 docx ID、分享链接与基线。目标已有正文时，只有用户已授权把整份目标作为此 PRD 展示副本才添加 `--accept-existing`。重复绑定复用记录，不刷新基线以掩盖云端漂移。一个云文档不能绑定两份本地 PRD。

`prepare` 不访问云端、不写云端，冻结指定 PRD 修订和本地图片副本到 `.prototype-flow/feishu-plans/SYNC-.../`，输出可检查计划。未绑定的 PRD 到真正执行时才创建；父目录绑定使用 folder/wiki token，不自行猜测目标。

## 已授权同步

```bash
python3 -B <skill-dir>/scripts/flow.py feishu sync <project-dir> <plan-id> --execute
```

用户明确要求同步指定 PRD 后，可以在相同授权范围内 prepare、检查并执行，无需反复询问。单纯保存、生成 Demo、认可方案或启用飞书模式不授权云端写入。`--execute` 表达调用方已核对本次范围；没有此参数不会写入。

同步逐文档串行：先检查固定输入和图片哈希，读取云端与绑定基线或上次进度核对，执行正文/图片更新，每步读回，完成后更新基线、需求块映射、图片映射与成功修订。绑定目标采用整份展示副本更新，保留同一文档链接；此模式不适合混有他人内容的文档。

云端意外变化会阻塞受影响文档，不覆盖；本地继续编辑不改变已冻结计划，完成后若本地新修订仍有差异，显示待同步。纯本地工作、Demo 验证与项目快照不受云端失败影响。

## 格式和图片边界

适配器导入本地 Markdown 的标准标题、段落、列表、常规表格、引用、代码、链接；去掉 frontmatter、内部需求元数据和本地自动关联区，在需求标题附上稳定 ID 后读回重建 block ID 与直达链接。

项目内图片必须独占一行，prepare 固定图片副本；同步通过当前 CLI 的本地 media-insert 插入原位置。记录本地 sha256 对应的云端 token 和 block ID。为保持顺序，文档按正文段落与图片分段发布，未完成期间可能显示部分内容，工作台必须显示 partial/failed，不能提前标成功。

外网图片先在适用授权下保存为项目资源；行内/表格图片、任意 XML/复杂嵌入和无法访问的本地链接在 prepare 阶段报出，先经人工核对转换后同步，不静默降级。常规正文的已绑定文档链接可以使用飞书 URL；目录导航自动引用稳定云端链接。不能把本地 Demo 地址放在共享 PRD 中作为可用分享入口。

readback 使用保守的 Markdown 文本/结构比较、真实图片 token 和完整需求块映射；CLI 格式转换不兼容时停止并保留实际错误，不放宽成“非空即成功”。首版模拟传输测试不能代替真实账号、云文档格式及图片呈现验收。

## 失败恢复

- 写操作超时或结果不明确：先 fetch 对比写入前和预期结果。已写入则承接进度；证据表明未写入才允许重试。无法确定时停止该文档。
- 创建返回不明确且没有文档 ID：不可自动重新创建；通过飞书查找实际目标后显式 bind，再继续同一个计划。
- 部分文档失败：成功项保持成功，执行同一 plan ID 只继续未完成部分。不要为绕过失败新建同名文档。
- 图片 token 只属于执行进度，不进入固定输入。旧运行时若曾误把 token 写进输入，只有移除该进度字段后能精确匹配原 `inputHash` 才恢复；正文或其他输入变化仍拒绝。恢复继续读回核对，不重复上传已成功图片。
- CLI 返回确认门禁时保留实际错误，按照 use-feishu-cli 的准确来源处理，不自动追加当前 help 不支持的参数或扩大权限。
- `.prototype-flow/feishu.lock` 防止并发同步；残留锁只有在确认原进程结束后才能移除。

飞书导航也是独立稳定绑定（`__navigation__`），在本轮文档全部成功后更新。导航不能将失败文档伪装成已经完成。当前账本与固定计划属于实时状态，恢复本地历史不回滚它们，也不自动回退云端。
