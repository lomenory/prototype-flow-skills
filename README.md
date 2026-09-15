# Prototype Flow Skills

Prototype Flow 所需依赖 Skill 的公开分发仓库。每个 `skills/<name>/` 都是可独立安装的完整 Skill 目录。

| Skill | 用途 | 加载时机 |
| --- | --- | --- |
| [prd-doc-maintainer](skills/prd-doc-maintainer/SKILL.md) | PRD 文档库、索引、关联和 dashboard | PRD 及完整项目 |
| [demo-design](skills/demo-design/SKILL.md) | HTML 高保真 Demo 与交互验证 | 生成或更新 Demo |
| [use-feishu-cli](skills/use-feishu-cli/SKILL.md) | 飞书官方 CLI 操作指导 | 飞书相关任务 |

## 安装

使用已提供的 Prototype Flow 主 Skill 时，入口会检查当前阶段的依赖，缺失时从本仓库固定提交下载，校验后安装。已有 Skill 会被复用，安装器不覆盖现有目录。

也可以让 Codex 的 Skill Installer 安装单个目录，例如：

> 使用 skill-installer，从 GitHub 仓库 lomenory/prototype-flow-skills 安装 skills/prd-doc-maintainer。

本仓库公开可读，下载无需 GitHub 登录。安装 Skill 不等于安装 Node、浏览器工具或 `lark-cli`，也不会配置飞书账号。使用者仍需满足相应 Skill 的运行条件和宿主权限。

## 快照维护

首批分发快照整理于 2026-09-15：

- `prd-doc-maintainer` 和 `use-feishu-cli`：保留作者维护的现有 Skill 文件。
- `demo-design`：仅分发经过 Core 验证的 Runtime/Contract v9，契约哈希 `e0a96def6e9c`；文件哈希和原始来源提交记录在 `runtime-manifest.json` 中。

这里只存放依赖 Skill，不包含 Prototype Flow 主项目、业务示例、项目验证截图、私人配置或账号凭据。更新依赖时先验证新的完整快照，再更新主 Skill 的 `dependencies.lock.json` 中的提交与文件哈希；不让已分发版本自动追踪分支最新内容。
