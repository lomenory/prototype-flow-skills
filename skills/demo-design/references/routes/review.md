# Design Review Route

- 只基于用户提供的截图、URL、Figma 摘要、HTML/CSS、已有渲染或可见设计证据输出 Findings。
- 先判断 `preserve`、`overhaul` 或 `greenfield`。用户只要求 Review 时不生成 Redesign。
- Findings 按阻塞、重要、改进建议排序，并指出具体证据、影响和最小修复方向。
- 评审视觉层级、内容结构、组件一致性、状态、响应式、可访问性和数据表达；不为不可见 UI 编造问题。
- Preserve 模式不得静默修改 Logo、URL/Anchor、主导航、表单语义、法务/隐私/价格文案、分析敏感 CTA、真实指标或已有可访问性能力。
- Mode 为 `data_viz` 时额外检查来源、单位、Axis、Legend、Tooltip、颜色区分和状态完整性。
- 已有截图、渲染或可静态检查代码时默认 `tier_0_text_copy_only`：不强制 Playwright、截图或 `scripts/verify.py`。
- URL、Figma 或动态页面必须先取得可见证据；使用已有浏览器或 Connector 采集证据不等于执行完整验证。用户明确要求浏览器 QA、响应式或交互检查时，按受影响范围升级 Tier。
