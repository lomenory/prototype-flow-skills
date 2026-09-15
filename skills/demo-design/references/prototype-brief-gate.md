<!-- generated-from: contracts/*.yaml; contract-hash: e0a96def6e9c; do-not-edit -->
# Prototype Brief Gate

先使用 Request Intent Schema 判断当前请求允许只读、提案、实施或 Git 操作，再使用 Execution Tier 对应的 Brief Policy；`tier_3_full_delivery` 再使用 Route Schema，命中 Mode 时追加 Mode Schema。

## Common Rules

- 先提取用户已给出的字段，只询问会实质改变交付物的缺项。
- 不重复询问已确认的值。独立字段可以一次收集最多 5 项；只有顺序敏感的选择才逐项询问。
- 用户已给出完整 PRD 或足够的对话描述时，回显关键 assumptions 后继续；只在 material blocker 存在时要求显式确认。
- “直接做”可以跳过方向确认，但不能跳过设计上下文冲突。
- 修改范围不明确时先做有界定位；只有定位后仍无法限定影响范围才升级完整交付。
- Web 与 App Flow 默认只设计一个目标展示环境；Web 未指定时使用 `1440x900`。
- Web 与 App Flow 默认首要交付 `project_bundle`，不为此追问；页面与资源放在同一个独立文件夹，整个文件夹就是分享边界。
- 只有用户或权威设计范围明确要求时，才增加 Viewport、设备、平台、方向或断点适配；不为默认单目标追问多端策略。
- Tier 0/1 默认不读取 Design Reference、不跑视觉 Diff、不做完整资源可携带性扫描；这些阶段只能由明确升级条件进入。

## Schemas

### Request Intent Schemas

| Schema | Required fields | Conditional fields | Not required |
| --- | --- | --- | --- |
| `inspect_only` | review_question、inspectable_scope | evidence_target when the request names a suspected cause or artifact | implementation_authorization、execution_plan |
| `propose_only` | decision_goal、current_context | options when the user names alternatives、constraints when they materially change the recommendation | implementation_authorization、commit_authorization |
| `execute_now` | explicit_implementation_request、requested_outcome、protected_scope | success_evidence when the result is not directly observable、error_cancel_path when async or destructive、production_boundary when Demo behavior may differ | direction_reconfirmation when material fields are complete |
| `resume_approved` | explicit_implementation_request、approved_artifact_or_conversation_scope | selected_scope when only part of the approved proposal should run | proposal_reapproval |
| `publish` | explicit_publish_request、requested_git_actions、exact_target | commit_message when commit is requested、remote_and_branch when push is requested | unrequested_commit、unrequested_push、unrequested_pull_request、unrequested_merge |

### Execution Schemas

| Schema | Required fields | Conditional fields | Not required |
| --- | --- | --- | --- |
| `text_copy_patch` | inspectable_artifact、exact_target、requested_change、semantic_impact | target_selector when the target can be addressed in HTML | page_goal、design_system、design_guidance |
| `local_ui_patch` | inspectable_artifact、exact_target、target_selectors、requested_change、expected_result、protected_scope | relevant_viewport when the target is viewport-specific、browser_policy when full candidate fallback is required | page_goal、primary_user_task、design_system_selection、new_design_guidance |
| `layout_or_interaction` | inspectable_artifact、affected_layout_or_interaction、verification_targets、expected_result、affected_viewports_or_states | action_ids when interaction changes、cancel_or_error_path when async or destructive behavior changes、browser_policy when full candidate fallback is required、portability when assets or resource paths change | full_page_rebrief、new_design_system_selection |

### Route Schemas

| Schema | Required fields | Conditional fields | Not required |
| --- | --- | --- | --- |
| `web_hi_fi` | page_goal、audience、primary_user_task、content_scope、viewport_strategy | success_outcome when the task changes state or completes a transaction、content_priority when multiple sections or decisions compete、critical_states when forms, async work, or data exist、accessibility_or_domain_risk when failure has material impact、primary_cta when conversion page、breakpoint_expectations when explicitly constrained、additional_viewports when explicitly required、design_reference when external fidelity is required | device_frame、click_flow_for_every_page、user_research_report、design_score、delivery_format_confirmation when the project_bundle default applies |
| `app_flow` | product_name、platform、primary_user_task、flow_start、trigger_action、target_state | success_outcome when target_state alone is ambiguous、content_priority when multiple actions compete、critical_states when forms, async work, or data exist、accessibility_or_domain_risk when failure has material impact、error_or_cancel_path when destructive or async、target_device_frame_or_orientation when explicitly constrained、additional_devices_platforms_or_orientations when explicitly required、design_reference when external fidelity is required | overview_screen_grid、user_research_report、design_score、delivery_format_confirmation when the project_bundle default applies |
| `design_review` | inspectable_artifact、review_scope | browser_validation when explicitly requested | generation_confirmation |

### Mode Schemas

| Schema | Required fields | Conditional fields | Not required |
| --- | --- | --- | --- |
| `data_viz` | audience、decision_goal、data_source_status | chart_types when supplied data constrains them | marketing_hero |
| `product_contract` | review_goal、primary_actors、core_scenarios | material_fields when forms or data entry exist、business_states when lifecycle exists、permission_rules when actor behavior differs、error_cancel_retry when operation is async or destructive、data_visibility when sensitive data exists、revision_and_change_set for schemaVersion 2 or changed business models | complete_backend_schema、full_api_contract、pixel_perfect_direction |

## Source

此文件由 Canonical Brief Contract 生成；Runtime 中为只读快照。
