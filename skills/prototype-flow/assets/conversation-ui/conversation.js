(() => {
  'use strict';
  const root = document.getElementById('__ROOT_ID__');
  const get = role => root.querySelector(`[data-role="${role}"]`);
  const { snapshot, card, hostActions } = JSON.parse(get('payload').textContent);
  const historicalWrite = snapshot.historical && ['change', 'continue-run', 'export-module'].includes(card.form?.intent);
  const form = historicalWrite ? null : card.form;
  const targets = new Map((form?.targets || []).map(item => [item.id, item]));
  const fixedIds = (form?.selectedIds || []).filter(id => targets.has(id));
  const selected = new Set(fixedIds);
  const canSend = Boolean(hostActions && typeof window.openai?.sendFollowUpMessage === 'function');
  const canCopy = typeof navigator.clipboard?.writeText === 'function';
  let pending = false, actionId = null, lastAttempt = null;
  const text = value => ['string', 'number'].includes(typeof value) ? String(value) : '';
  const node = (tag, value, className) => {
    const item = document.createElement(tag);
    if (value !== undefined) item.textContent = text(value);
    if (className) item.className = className;
    return item;
  };
  const names = () => [...selected].map(id => targets.get(id)?.title || id);
  function sections(target) {
    for (const section of card.sections || []) {
      const block = node(section.collapsed ? 'details' : 'section', undefined, 'pf-content-zone');
      if (section.title) block.append(node(section.collapsed ? 'summary' : 'h3', section.title));
      if (section.type === 'text') {
        for (const value of section.paragraphs || []) block.append(node('p', value, 'pf-text'));
      } else if (section.type === 'list') {
        const list = node('ul');
        for (const value of section.items || []) list.append(node('li', value));
        block.append(list);
      } else if (section.type === 'facts') {
        const list = node('dl', undefined, 'pf-facts');
        for (const item of section.items || []) list.append(node('dt', item.label), node('dd', item.value));
        block.append(list);
      } else if (section.type === 'records') {
        for (const item of section.items || []) {
          const entry = node('div', undefined, 'pf-record');
          entry.append(node('p', item.title, 'pf-record-title'));
          if (item.detail) entry.append(node('p', item.detail, 'text-small'));
          block.append(entry);
        }
      }
      target.append(block);
    }
  }
  function comparison() {
    const list = get('comparison-list');
    for (const change of card.changes || []) {
      const entry = node('section', undefined, 'pf-comparison');
      entry.append(node('h3', change.title));
      const columns = node('div', undefined, 'pf-change-columns');
      for (const [label, values] of [['修改前', change.before], ['修改后', change.after]]) {
        const column = node('div');
        column.append(node('p', label, 'pf-change-label'));
        for (const value of values?.length ? values : ['未提供此侧变化内容。']) column.append(node('p', value, 'pf-text'));
        columns.append(column);
      }
      entry.append(columns);
      if (change.excerpted) entry.append(node('p', '这里展示的是差异节选。', 'text-small'));
      list.append(entry);
    }
  }
  function chosenScope() { return get('scope')?.value || form?.scope || 'prd'; }
  function updateSelection() {
    if (!form) return;
    get('selection-summary').textContent = selected.size ? `已选 ${selected.size} 项：${names().join('、')}` : '尚未选择对象。';
    get('selection-summary').hidden = form.selection === 'fixed';
  }
  function clearFieldError(role, inputRole) {
    const error = get(role);
    if (error) { error.hidden = true; error.textContent = ''; }
    get(inputRole)?.removeAttribute('aria-invalid');
  }
  function fieldError(role, message, inputRole) {
    const error = get(role);
    error.textContent = message; error.hidden = false;
    get(inputRole)?.setAttribute('aria-invalid', 'true');
  }
  function feedback(message, error = false) {
    get('feedback-zone').hidden = !message;
    get('status').textContent = message;
    get('status').setAttribute('role', error ? 'alert' : 'status');
    get('status').classList.toggle('text-destructive', error);
  }
  function invalidate() {
    if (pending) return;
    get('prompt').value = ''; get('manual-copy-zone').hidden = true;
    feedback('');
  }
  function persist() {
    if (!form || typeof window.openai?.setWidgetState !== 'function') return;
    const value = { modelContent: { projectId: snapshot.project.id, snapshotId: snapshot.snapshotId, selected: [...selected] },
      privateContent: { contract: 'prototype-flow.widget/1', cardContract: card.contract, purpose: card.purpose,
        requestedScope: form.requestedScope, snapshotId: snapshot.snapshotId, selected: [...selected],
        instruction: get('instruction')?.value || '', scope: chosenScope() } };
    if (new TextEncoder().encode(JSON.stringify(value)).length < 16 * 1024) {
      try { Promise.resolve(window.openai.setWidgetState(value)).catch(() => {}); } catch (_) { /* Draft state is optional. */ }
    }
  }
  function changed(field) {
    invalidate();
    if (field === 'selection') clearFieldError('selection-error', 'object-list');
    if (field === 'instruction') clearFieldError('instruction-error', 'instruction');
    if (field === 'scope') clearFieldError('scope-error', 'scope');
    persist();
  }
  function actionForm() {
    get('object-title').textContent = form.intent === 'change' ? '调整对象' : form.intent === 'continue-run' ? '继续对象' : '选择对象';
    for (const item of form.targets) {
      const row = node('div', undefined, 'pf-object-row');
      if (form.selection === 'fixed') row.append(node('p', item.title));
      else {
        const label = node('label', undefined, 'form-check'), input = node('input');
        input.type = form.selection === 'single' ? 'radio' : 'checkbox';
        input.name = root.id + '-target'; input.value = item.id; input.checked = selected.has(item.id);
        input.className = 'form-check-input'; input.setAttribute('aria-describedby', root.id + '-selection-error');
        input.addEventListener('change', () => {
          if (form.selection === 'single') selected.clear();
          input.checked ? selected.add(item.id) : selected.delete(item.id);
          updateSelection(); changed('selection');
        });
        label.append(input, node('span', item.title, 'form-check-label')); row.append(label);
      }
      if (item.detail) row.append(node('p', item.detail, 'text-small pf-object-detail'));
      get('object-list').append(row);
    }
    if (form.instruction) {
      get('input-zone').hidden = false;
      get('instruction-label').textContent = form.instruction.label;
      get('instruction').placeholder = form.instruction.placeholder || '';
      get('instruction').addEventListener('input', () => changed('instruction'));
    }
    if (form.scopes.length) {
      get('scope-zone').hidden = false;
      const initialScope = form.requestedScope || form.scope;
      const choices = [...form.scopes];
      if (!choices.some(option => option.value === initialScope)) choices.push({ value: initialScope,
        label: ({ prd: 'PRD', demo: 'Demo', 'prd-and-demo': 'PRD 与 Demo' })[initialScope], disabled: true });
      for (const choice of choices) {
        const option = node('option', choice.label); option.value = choice.value; option.disabled = Boolean(choice.disabled);
        get('scope').append(option);
      }
      get('scope').value = initialScope;
      const scopeAvailable = form.scopes.some(option => option.value === initialScope);
      get('scope').hidden = form.scopes.length === 1 && scopeAvailable;
      get('scope-text').hidden = !get('scope').hidden;
      get('scope-text').textContent = form.scopes.find(option => option.value === initialScope)?.label || '';
      if (form.scopeNote) { get('scope-note').hidden = false; get('scope-note').textContent = form.scopeNote; }
      get('scope').addEventListener('change', () => changed('scope'));
    }
    get('form').addEventListener('submit', event => { event.preventDefault(); if (card.primary) execute(card.primary, true); });
    updateSelection();
  }
  function restore(saved) {
    if (!form || pending) return;
    const value = saved?.privateContent;
    if (value?.contract !== 'prototype-flow.widget/1' || value.snapshotId !== snapshot.snapshotId) return;
    const before = JSON.stringify([[...selected], get('instruction')?.value, chosenScope()]);
    if (form.selection !== 'fixed') {
      selected.clear();
      for (const id of Array.isArray(value.selected) ? value.selected : []) {
        if (targets.has(id) && (form.selection !== 'single' || !selected.size)) selected.add(id);
      }
      for (const input of root.querySelectorAll('input[name]')) input.checked = selected.has(input.value);
    }
    if (form.instruction) get('instruction').value = text(value.instruction).slice(0, 2500);
    if (value.cardContract === card.contract && value.purpose === card.purpose && value.requestedScope === form.requestedScope
        && form.scopes.some(option => option.value === value.scope)) get('scope').value = value.scope;
    updateSelection();
    if (before !== JSON.stringify([[...selected], get('instruction')?.value, chosenScope()])) invalidate();
  }
  function validateForm() {
    if (!selected.size) { fieldError('selection-error', '请选择本次需要处理的对象。', 'object-list'); return false; }
    if (form.instruction?.required && !get('instruction').value.trim()) {
      fieldError('instruction-error', '请说明希望调整的内容及预期行为。', 'instruction'); return false;
    }
    if (form.scopes.length && !form.scopes.some(option => option.value === chosenScope())) {
      fieldError('scope-error', '此范围暂不能提交。请选择可用范围，或回到对话核对 Demo 编辑版本。', 'scope'); return false;
    }
    return true;
  }
  function request(descriptor, useForm) {
    if (!snapshot.actions.some(action => action.intent === descriptor.intent && action.enabled)) throw new Error('此操作当前不可用，请回到对话核对。');
    if (snapshot.historical && ['change', 'continue-run', 'export-module'].includes(descriptor.intent)) throw new Error('历史内容只读，请先定位当前稿。');
    const target = { ...(useForm ? form.target : descriptor.target) };
    if (useForm) {
      const ids = [...selected].filter(id => targets.has(id));
      if (ids.length !== selected.size || !ids.length) throw new Error('所选对象已失效，请重新读取当前范围。');
      if (form.targetKind === 'requirement') target.requirementIds = ids;
      else if (form.targetKind === 'module') target.moduleId = ids[0];
      else if (form.targetKind === 'run') target.runId = ids[0];
      else if (form.targetKind === 'document') target.documentId = ids[0];
    }
    const value = { contract: 'prototype-flow.inline-action/1', actionId, snapshotId: snapshot.snapshotId,
      project: { id: snapshot.project.id, rootHint: snapshot.project.rootHint },
      view: { kind: snapshot.scope.view, versionId: snapshot.versionId, observedAt: snapshot.observedAt, scope: snapshot.scope },
      intent: descriptor.intent, target };
    if (descriptor.intent === 'change') {
      if (!useForm || !target.requirementIds?.length) throw new Error('修改请求必须有明确的需求对象。');
      const requirements = snapshot.basis.requirements.filter(item => target.requirementIds.includes(item.id));
      if (requirements.length !== target.requirementIds.length) throw new Error('所选需求缺少有效依据，请在对话中重新读取。');
      value.base = { documents: snapshot.basis.documents, requirements };
      value.input = { scope: chosenScope(), instruction: get('instruction').value.trim() };
      if (value.input.scope !== 'prd') {
        const demo = snapshot.basis.demo;
        if (!demo?.baselineHash || demo.contract !== 'prototype-flow.demo-edit-baseline/1'
            || !demo.scope || !Object.keys(demo.scope).length || demo.project?.id !== snapshot.project.id
            || demo.versionId !== 'working') throw new Error('Demo 编辑依据不可用，请先在对话中核对。');
        value.base.demo = { contract: demo.contract, baselineHash: demo.baselineHash,
          project: demo.project, versionId: demo.versionId, scope: demo.scope };
      }
    }
    const selectedNames = useForm ? names().join('、') : card.context || card.title;
    const prompt = `${descriptor.verb}：${selectedNames}。${value.input?.instruction || ''}\n\n${JSON.stringify(value, null, 2)}`;
    if (new TextEncoder().encode(prompt).length > 16 * 1024) throw new Error('请求过长，请缩小选择范围或修改说明。');
    return prompt;
  }
  function requestName(descriptor) { return descriptor.intent === 'change' ? '修改请求' : `${descriptor.verb}请求`; }
  function actionLabel(descriptor) {
    const name = requestName(descriptor);
    return canSend ? `发送${name}` : canCopy ? `复制${name}` : `生成可复制的${name}`;
  }
  function manualCopy(prompt) {
    get('manual-copy-zone').hidden = false; get('prompt').value = prompt;
    feedback('请复制下方全部内容，粘贴到当前对话后开始处理。');
    try { get('prompt').focus(); get('prompt').select(); } catch (_) { /* Manual selection remains available. */ }
  }
  async function execute(descriptor, useForm) {
    if (pending) return;
    if (useForm && !validateForm()) return;
    const attempt = JSON.stringify([descriptor, useForm ? [...selected] : [], useForm ? get('instruction')?.value : '', useForm ? chosenScope() : '']);
    if (attempt !== lastAttempt) actionId = globalThis.crypto?.randomUUID?.() || `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    lastAttempt = attempt;
    let prompt;
    try { prompt = request(descriptor, useForm); } catch (error) { feedback(error.message, true); return; }
    pending = true;
    const enabled = [...root.querySelectorAll('button, input, select, textarea')].filter(input => !input.disabled && input !== get('prompt'));
    enabled.forEach(input => { input.disabled = true; });
    get('manual-copy-zone').hidden = true; get('prompt').value = '';
    feedback(canSend ? '正在发起请求…' : canCopy ? '正在复制请求…' : '');
    try {
      if (canSend) {
        await window.openai.sendFollowUpMessage({ prompt, title: descriptor.verb });
        feedback('请求已发起，等待对话处理。');
        return;
      }
      if (canCopy) {
        await navigator.clipboard.writeText(prompt);
        feedback(`${requestName(descriptor)}已复制。粘贴到当前对话后开始处理。`);
      } else manualCopy(prompt);
    } catch (_) {
      if (canSend) {
        get('manual-copy-zone').hidden = false; get('prompt').value = prompt;
        feedback('发送失败或已取消，输入已保留。可重试，或手动复制下方请求。', true);
      } else manualCopy(prompt);
    }
    pending = false; enabled.forEach(input => { input.disabled = false; });
  }

  get('title').textContent = card.title;
  get('context').textContent = card.context; get('context').hidden = !card.context;
  const observed = new Date(card.source?.observedAt);
  get('source').textContent = `${card.source?.label || '本次读取'}${Number.isNaN(observed.getTime()) ? '' : ` · 读取于 ${observed.toLocaleString('zh-CN')}`}`;
  if (card.kind === 'action') {
    if (form) actionForm();
    else { get('form').hidden = true; feedback('历史内容只读，请先定位当前稿。'); }
  }
  else {
    if (card.kind === 'compare') comparison();
    sections(get('reading-zone'));
  }
  for (const [role, descriptor, useForm] of [['primary', card.primary, card.kind === 'action'], ['secondary', card.secondary, false]]) {
    if (!descriptor) continue;
    if (snapshot.historical && ['change', 'continue-run', 'export-module'].includes(descriptor.intent)) continue;
    const control = get(role); control.hidden = false; control.textContent = actionLabel(descriptor);
    control.dataset.actionId = descriptor.intent;
    control.addEventListener('click', () => execute(descriptor, useForm));
    get('action-zone').hidden = false;
  }
  restore(window.openai?.widgetState);
  window.addEventListener('openai:set_globals', event => restore(event.detail?.globals?.widgetState));
})();
