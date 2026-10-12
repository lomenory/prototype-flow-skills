(() => {
  'use strict';
  const root = document.getElementById('__ROOT_ID__');
  const get = role => root.querySelector(`[data-role="${role}"]`);
  const { snapshot: state, hostActions } = JSON.parse(get('snapshot').textContent);
  const data = state.data, view = state.scope.view;
  const selected = new Set(state.scope.requirementId ? [state.scope.requirementId] : []);
  let pending = false, actionId = null, lastAttempt = null;
  const actionLabels = { inspect: '分析影响', change: '发送修改请求', 'read-latest': '读取最新状态',
    'open-demo': '打开 Demo', 'open-workbench': '打开工作台', compare: '比较版本',
    'continue-run': '继续任务', 'export-module': '导出交付包' };
  const statuses = { draft: '草稿', proposed: '内容待确认', confirmed: '内容已确认', approved: '内容已确认', archived: '已归档',
    running: '进行中', completed: '已完成', partial: '部分完成', failed: '失败', blocked: '受阻', cancelled: '已取消' };
  const node = (tag, text) => { const item = document.createElement(tag); if (text != null) item.textContent = text; return item; };
  get('title').textContent = data.requirement?.title || data.module?.title || state.project.name;
  get('time').textContent = `截至 ${new Date(state.observedAt).toLocaleString()} · 修订 ${state.project.storedRevision} · ${state.historical ? '历史只读' : '当前稿'}`;
  get('context').textContent = JSON.stringify({ project: state.project, versionId: state.versionId, scope: state.scope }, null, 2);
  const content = get('content');
  for (const [label, records] of [['待处理事项', data.pending], ['最近任务', data.recentTasks]]) {
    if (!records?.length) continue;
    content.append(node('h3', label));
    for (const item of records) {
      const row = node('div'); row.className = 'pf-item';
      row.append(node('span', `${item.title || '任务'} · ${typeof item.reason === 'string' ? item.reason : statuses[item.status] || '待处理'}`));
      const button = node('button', '查看详情'); button.className = 'btn'; button.type = 'button';
      button.addEventListener('click', () => submit('inspect', item.runId ? { runId: item.runId }
        : item.bindingId ? { bindingIds: [item.bindingId], artifactId: item.artifactId }
        : item.kind === 'module' ? { moduleId: item.moduleId }
        : item.kind === 'maintenance' ? { maintenance: true }
        : { requirementIds: [item.requirementId || item.id], moduleId: item.moduleId }));
      row.append(button); content.append(row);
    }
  }
  if (data.requirement) {
    content.append(node('p', data.requirement.excerpt), node('p', '正文节选；保存前需重新读取完整 PRD。'));
    for (const binding of data.bindings || []) {
      const row = node('div'); row.className = 'pf-item';
      row.append(node('span', `${binding.title || binding.screenId || binding.id} · ${binding.evidence?.label || '尚未验证'}`));
      const button = node('button', '打开此页面'); button.className = 'btn'; button.type = 'button';
      button.addEventListener('click', () => submit('open-demo', { bindingIds: [binding.id], artifactId: binding.artifactId }));
      row.append(button); content.append(row);
    }
    if (data.demoEntry?.status !== 'available') content.append(node('p', data.demoEntry?.reason || '尚未设置默认 Demo 入口'));
    if (data.demoEditUnavailable) content.append(node('p', data.demoEditUnavailable));
  }
  if (data.task) content.append(node('pre', JSON.stringify(data.task, null, 2)));
  if (view === 'result') content.append(node('pre', JSON.stringify(data, null, 2)));
  for (const item of data.items || []) {
    const row = node('div'); row.className = 'pf-item';
    if (view === 'module') {
      const label = node('label'), input = node('input'); input.type = 'checkbox'; input.value = item.id;
      label.className = 'form-check'; input.className = 'form-check-input';
      input.addEventListener('change', () => { input.checked ? selected.add(item.id) : selected.delete(item.id); persist(); });
      const text = node('span', `${item.title} · ${statuses[item.status] || item.status || '草稿'} · ${item.pageCount || 0} 个页面`);
      text.className = 'form-check-label'; label.append(input, text); row.append(label);
    } else row.append(node('p', `${item.title || item.id} · ${item.stageLabel || statuses[item.status] || item.status || ''}`));
    if (item.diffExcerpt) row.append(node('pre', item.diffExcerpt), node('span', item.excerpted ? '差异节选' : '此文档差异'));
    const button = node('button', '查看详情'); button.type = 'button'; button.className = 'btn';
    const target = view === 'module' ? { requirementIds: [item.id] }
      : view === 'tasks' ? { runId: item.id } : view === 'compare' ? { documentId: item.id } : { moduleId: item.id };
    button.addEventListener('click', () => submit('inspect', target)); row.append(button); content.append(row);
  }
  if (state.page?.nextCursor) {
    const next = node('button', '读取下一页'); next.type = 'button'; next.className = 'btn';
    next.addEventListener('click', () => submit('read-latest', { cursor: state.page.nextCursor })); content.append(next);
  }
  const canChange = state.actions.some(a => a.intent === 'change' && a.enabled);
  get('request').hidden = !canChange;
  if (!state.basis.demo) for (const option of get('scope').options) if (option.value !== 'prd') option.disabled = true;
  get('instruction').addEventListener('input', persist); get('scope').addEventListener('change', persist);
  for (const action of state.actions) {
    const button = node('button', actionLabels[action.intent] || action.intent); button.className = action.intent === 'change' ? 'btn btn-primary' : 'btn'; button.type = 'button';
    button.disabled = !action.enabled; if (!action.enabled && action.reason) button.setAttribute('data-tooltip', action.reason);
    button.addEventListener('click', () => submit(action.intent)); get('actions').append(button);
  }
  function restore(saved) {
    const value = saved?.privateContent;
    if (!value || value.contract !== 'prototype-flow.widget/1' || value.snapshotId !== state.snapshotId) return;
    selected.clear();
    for (const id of value.selected || []) if (id === state.scope.requirementId || (data.items || []).some(i => i.id === id)) selected.add(id);
    for (const input of root.querySelectorAll('input[type="checkbox"]')) input.checked = selected.has(input.value);
    get('instruction').value = String(value.instruction || '').slice(0, 2500);
    if ([...get('scope').options].some(o => !o.disabled && o.value === value.scope)) get('scope').value = value.scope;
  }
  function persist() {
    const value = { modelContent: { projectId: state.project.id, snapshotId: state.snapshotId, selected: [...selected] },
      privateContent: { contract: 'prototype-flow.widget/1', snapshotId: state.snapshotId, selected: [...selected], instruction: get('instruction').value, scope: get('scope').value } };
    if (new TextEncoder().encode(JSON.stringify(value)).length < 16 * 1024 && typeof window.openai?.setWidgetState === 'function') {
      try { Promise.resolve(window.openai.setWidgetState(value)).catch(() => {}); } catch (_) { /* State is optional. */ }
    }
  }
  function request(intent, override = {}) {
    const target = { moduleId: state.scope.moduleId || data.requirement?.moduleId, requirementIds: [...selected],
      runId: state.scope.runId, ...override };
    if (intent === 'open-demo' && !target.bindingIds?.length && data.demoEntry?.status === 'available') {
      target.artifactId = data.demoEntry.artifactId; target.bindingIds = data.demoEntry.bindingId ? [data.demoEntry.bindingId] : [];
    }
    const value = { contract: 'prototype-flow.inline-action/1', actionId,
      snapshotId: state.snapshotId, project: { id: state.project.id, rootHint: state.project.rootHint },
      view: { kind: view, versionId: state.versionId, observedAt: state.observedAt, scope: state.scope }, intent, target };
    if (intent === 'change') {
      if (state.historical || !target.requirementIds.length) throw new Error('请明确选择当前稿需求。');
      if (!get('instruction').value.trim()) throw new Error('请填写修改说明。');
      value.base = { documents: state.basis.documents, requirements: state.basis.requirements.filter(r => target.requirementIds.includes(r.id)) };
      value.input = { scope: get('scope').value, instruction: get('instruction').value.trim() };
      if (value.input.scope !== 'prd') {
        if (!state.basis.demo) throw new Error('请先读取目标 Demo 的完整详情基线。');
        value.base.demo = { contract: state.basis.demo.contract, baselineHash: state.basis.demo.baselineHash,
          project: state.basis.demo.project, versionId: state.basis.demo.versionId, scope: state.basis.demo.scope };
        if (!value.base.demo.baselineHash) throw new Error('Demo 基线缺少有效指纹，请重新读取详情。');
      }
    }
    if (intent === 'compare') value.target.fromVersion = state.versionId;
    const prompt = `${actionLabels[intent] || intent}：${state.project.name}，${target.requirementIds.join('、') || target.runId || target.moduleId || state.versionId}。${value.input?.instruction || ''}\n\n${JSON.stringify(value, null, 2)}`;
    if (new TextEncoder().encode(prompt).length > 16 * 1024) throw new Error('请求超过 16 KiB，请缩小选择范围或修改说明。');
    return prompt;
  }
  async function submit(intent, target) {
    if (pending) return;
    const attempt = JSON.stringify([intent, target, [...selected], get('instruction').value, get('scope').value]);
    if (attempt !== lastAttempt) actionId = globalThis.crypto?.randomUUID?.() || `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    lastAttempt = attempt;
    let prompt;
    try { prompt = request(intent, target); } catch (error) { get('status').textContent = error.message; return; }
    get('prompt').value = prompt; get('fallback').hidden = false;
    if (!hostActions || typeof window.openai?.sendFollowUpMessage !== 'function') {
      get('status').textContent = '完整请求已准备，可复制到当前对话。'; get('prompt').focus(); get('prompt').select(); return;
    }
    pending = true; const enabled = [...root.querySelectorAll('button')].filter(b => !b.disabled); enabled.forEach(b => b.disabled = true);
    get('status').textContent = '正在发起请求…';
    try {
      await window.openai.sendFollowUpMessage({ prompt, title: actionLabels[intent] });
      get('status').textContent = '已发起请求，等待对话结果。';
    } catch (_) {
      get('status').textContent = '调用失败或取消；输入已保留，可复制完整请求或重试。';
      pending = false; enabled.forEach(b => b.disabled = false);
    }
  }
  restore(window.openai?.widgetState);
  window.addEventListener('openai:set_globals', event => { if (!pending) restore(event.detail?.globals?.widgetState); });
})();
