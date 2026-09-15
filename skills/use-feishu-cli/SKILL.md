---
name: use-feishu-cli
description: Use the official Feishu/Lark CLI (`lark-cli`) to install and configure access, inspect authentication and identity, search or read Feishu work context, and safely create, update, send, organize, or verify messages, documents, Drive files, spreadsheets, Bitable records, calendars, meetings, Minutes, mail, tasks, Wiki content, contacts, slides, boards, OKRs, approvals, attendance, and related resources. Use whenever a request mentions 飞书、Lark、飞书 CLI、lark-cli、飞书消息/群聊/云文档/多维表格/日历/妙记/邮箱/任务/知识库, or asks an agent to complete a workflow inside Feishu from the terminal.
---

# 使用飞书 CLI

通过终端调用官方 `lark-cli`，把用户的自然语言意图转成可验证的飞书操作。优先使用运行时帮助和 schema 获取准确语法，不依赖记忆猜测子命令。

## 核心流程

1. 明确对象、范围、身份和预期结果。
   - 区分只读、明确的单次写入、对外发送、批量修改、权限变更和删除/回退等操作。
   - 从用户提供的链接、名称、群聊或时间范围中提取目标；缺少 ID 时先搜索或读取，再解析唯一目标。
   - 仅在歧义会改变收件人、内容、范围、时间、权限或不可逆结果时询问用户。

2. 按需完成最小化预检。
   - 用 `command -v lark-cli` 判断 CLI 是否存在。
   - 用 `lark-cli auth status` 查看登录状态；权限相关任务再用 `lark-cli auth check`。
   - 当作者身份、消息署名、个人数据或应用身份会影响结果时，用 `lark-cli whoami` 确认实际执行身份。
   - 不输出访问令牌、密钥、授权码或完整敏感配置。

3. 运行时发现正确命令。
   - 先用 `lark-cli help` 查看命令总览。
   - 用 `lark-cli <command> --help` 查看目标子命令的参数。
   - 用 CLI 的 `schema` 能力查询接口字段、必填项和返回结构。
   - 不凭空编造业务域名称、参数、资源 ID 或 schema；CLI 版本变化时以本机帮助为准。
   - 需要选择业务域或组合跨域流程时，读取 [references/capability-map.md](references/capability-map.md)。

4. 先解析，再变更。
   - 用只读命令确认同名用户、群聊、文档、日历、数据表、视图或邮件线程。
   - 检查分页、截断和时间范围；聚合任务必须遍历所有需要的结果，不能把首屏当全集。
   - 涉及时区时显式确认时区，并在结果中写明使用的时区。
   - 批量写入前先校验字段类型、记录数量和目标表/视图；文档写入前先确认是追加、替换还是局部修改。

5. 按用户授权执行。
   - 只读查询直接执行。
   - 用户明确要求的、范围清楚的创建或更新直接执行。
   - 收件人、正文、时间或附件存在实质歧义时，先展示待发送内容并确认。
   - 批量发送、删除、移入废纸篓、回退版本、覆盖正文、大范围权限变更等高影响操作，仅在用户已明确授权确切范围时执行；否则先给出对象数量和影响范围并确认。
   - 不因 CLI 能完成某项操作就扩大任务范围。

6. 验证用户可见结果。
   - 写操作后优先读回目标，核对标题、正文摘要、收件人、时间、记录数、状态或权限。
   - CLI 返回异步任务时，轮询到成功、失败或明确仍在处理中；不要把“已提交”表述成“已完成”。
   - 汇报实际执行身份、成功/失败数量、资源 ID 或可用链接，以及未完成项。
   - 失败时保留原始错误中的关键字段，并按“命令语法 → 登录身份 → 权限 → 资源定位 → 网络/沙箱”顺序排查。

## 安装与配置

仅在用户明确要求安装，或 CLI 缺失且用户同意安装时执行：

```bash
npx @larksuite/cli@latest install
```

根据交互提示创建或选择飞书应用并完成用户授权。配置完成后提醒用户重启 Codex 或当前 Agent 工具，以便安装器附带的 skills 被完整加载。

常用管理命令：

```bash
lark-cli config init
lark-cli auth login
lark-cli auth status
lark-cli auth check
lark-cli auth logout
lark-cli update
```

需要个人日历、消息或文档，并以用户本人名义操作时使用用户身份。应用身份还需要在飞书开放平台开通相应权限。国际版 Lark 通过 `config init` 配置对应应用。

## 权限与故障处理

- 缺少业务域权限时，依据 CLI 帮助和错误提示执行 `lark-cli auth login --domain <domain>`。
- 错误给出具体 scope 时，执行 `lark-cli auth login --scope "<missing_scope>"`；不要自行扩大到无关权限。
- OAuth 授权码过期时，重新执行 `lark-cli auth login`。
- 提示命令不存在时，检查 CLI 是否安装以及 npm 全局可执行目录是否在 `PATH`；可用 `npm root -g` 辅助定位。
- 沙箱阻止必要命令时，请求与当前任务匹配的最小权限，不要静默关闭或全面放宽沙箱。
- 应用身份仍提示无权限时，检查开放平台后台权限是否已开通，再重新授权或重试。

## 组合工作流

- 会议后执行待办：读取妙记/逐字稿 → 提取候选待办 → 明确外部动作 → 创建任务、发文档或约后续会议 → 逐项验证。
- 文档共创：读取正文和评论 → 生成修改清单 → 更新指定位置 → 添加或回复评论 → 读回核对。
- 多人约会：解析参与人 → 查询忙闲和时区 → 给出共同空档 → 创建日程/预订会议室 → 核对邀请状态。
- 会议审计：分页读取日历或妙记 → 分类与评分 → 写入多维表格 → 创建视图/仪表盘 → 核对记录数。
- 邮件处理：搜索未读邮件 → 分类和摘要 → 创建草稿 → 仅在用户授权后发送、归档或批量移动。

具体业务域能力和常见请求示例见 [references/capability-map.md](references/capability-map.md)。
