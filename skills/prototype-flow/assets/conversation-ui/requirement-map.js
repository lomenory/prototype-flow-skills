(() => {
  'use strict';
  const root = document.getElementById('__ROOT_ID__');
  if (!root) return;
  const get = role => root.querySelector(`[data-role="${role}"]`);
  const contract = 'prototype-flow.requirement-map/1';
  const stateContract = 'prototype-flow.requirement-map-view/1';
  const statuses = {
    'not-generated': ['未生成', 'neutral'], generating: ['生成中', 'blue'], blocked: ['受阻', 'red'],
    partial: ['部分生成', 'orange'], generated: ['待验证', 'blue'], verified: ['已验证', 'green'],
    stale: ['需更新', 'orange'], unknown: ['待核对', 'neutral']
  };
  const acceptanceStatuses = { generated: ['待验证', 'blue'], verified: ['已验证', 'green'], missing: ['未生成', 'neutral'], stale: ['需更新', 'orange'], unknown: ['待核对', 'neutral'] };
  const text = value => ['string', 'number'].includes(typeof value) ? String(value) : '';
  const list = value => Array.isArray(value) ? value : [];
  const el = (tag, value, className) => {
    const element = document.createElement(tag);
    if (value !== undefined) element.textContent = text(value);
    if (className) element.className = className;
    return element;
  };
  const idPresent = value => typeof value === 'string' && value.length > 0;
  let payload, modules = [], byId = new Map(), moduleById = new Map(), frame = 0, disposed = false, moduleSequence = 0;
  let lastUpdate = { applied: false, reason: 'not-initialized' };
  const moduleNodes = new Map(), requirementNodes = new Map();
  const state = { selected: null, collapsed: new Set(), detailOpen: true };

  function validate(candidate) {
    const snapshot = candidate?.snapshot, model = candidate?.requirementMap;
    if (snapshot?.schemaVersion !== 1 || !idPresent(snapshot.project?.id) || !idPresent(snapshot.versionId)
      || !Number.isInteger(snapshot.project.storedRevision) || snapshot.project.storedRevision < 0
      || !idPresent(snapshot.snapshotId) || !idPresent(snapshot.observedAt) || typeof snapshot.historical !== 'boolean'
      || model?.contract !== contract || !idPresent(model.scopeKey) || !Array.isArray(model.modules)) return false;
    if (model.sequence !== undefined && (!Number.isInteger(model.sequence) || model.sequence < 0)) return false;
    const moduleIds = new Set(), requirementIds = new Set();
    for (const module of model.modules) {
      if (!idPresent(module?.id) || moduleIds.has(module.id) || !Array.isArray(module.requirements)) return false;
      moduleIds.add(module.id);
      for (const item of module.requirements) {
        if (!idPresent(item?.id) || requirementIds.has(item.id) || !item.coverage || typeof item.coverage !== 'object') return false;
        requirementIds.add(item.id);
        const coverage = item.coverage;
        if (!Object.hasOwn(statuses, coverage.state) || typeof coverage.known !== 'boolean'
          || !Number.isInteger(coverage.generated) || coverage.generated < 0
          || !Number.isInteger(coverage.verified) || coverage.verified < 0 || coverage.verified > coverage.generated) return false;
        if (coverage.known && (!Number.isInteger(coverage.total) || coverage.total < coverage.generated || coverage.total < 0)) return false;
        if (!coverage.known && coverage.total !== null && coverage.total !== undefined) return false;
        if (item.acceptance !== undefined && (!Array.isArray(item.acceptance)
          || item.acceptance.some(entry => !entry || typeof entry !== 'object'))) return false;
        if (item.businessAcceptance !== undefined && (!Array.isArray(item.businessAcceptance)
          || item.businessAcceptance.some(entry => typeof entry !== 'string'))) return false;
        for (const key of ['pages', 'sources']) if (item[key] !== undefined && (!Array.isArray(item[key]) || item[key].some(entry => !entry || typeof entry !== 'object'))) return false;
      }
    }
    return true;
  }
  function index() {
    modules = payload.requirementMap.modules;
    moduleById = new Map(modules.map(module => [module.id, module]));
    byId = new Map(modules.flatMap(module => module.requirements.map(item => [item.id, { item, module }])));
  }
  function presentation(item) {
    const coverage = item.coverage, fallback = statuses[coverage.state] || statuses.unknown;
    return { ...coverage, label: text(coverage.label) || fallback[0], tone: fallback[1] };
  }
  function fullyGenerated(item) {
    const value = item.coverage;
    return value.known && value.total > 0 && value.generated === value.total && value.state !== 'stale';
  }
  function fullyVerified(item) { return fullyGenerated(item) && item.coverage.verified === item.coverage.total && item.coverage.state === 'verified'; }
  function persist() {
    if (typeof window.openai?.setWidgetState !== 'function') return;
    const selected = byId.get(state.selected), value = selected && presentation(selected.item);
    const saved = {
      modelContent: { projectId: payload.snapshot.project.id, snapshotId: payload.snapshot.snapshotId,
        requirementId: selected?.item.id || null, requirementTitle: selected?.item.title || null,
        demoStatus: value?.state || null, generated: value?.generated ?? null, verified: value?.verified ?? null, total: value?.known ? value.total : null },
      privateContent: { contract: stateContract, projectId: payload.snapshot.project.id, versionId: payload.snapshot.versionId,
        scopeKey: payload.requirementMap.scopeKey, selected: state.selected, collapsed: [...state.collapsed], detailOpen: state.detailOpen }
    };
    const encoded = JSON.stringify(saved);
    if (new TextEncoder().encode(encoded).length >= 16 * 1024) return;
    try { Promise.resolve(window.openai.setWidgetState(saved)).catch(() => {}); } catch (_) { /* View state is optional. */ }
  }
  function restore(saved) {
    const value = saved?.privateContent;
    if (value?.contract !== stateContract || value.projectId !== payload.snapshot.project.id
      || value.versionId !== payload.snapshot.versionId || value.scopeKey !== payload.requirementMap.scopeKey) return false;
    if (byId.has(value.selected)) state.selected = value.selected;
    state.collapsed = new Set(list(value.collapsed).filter(id => moduleById.has(id)));
    if (typeof value.detailOpen === 'boolean') state.detailOpen = value.detailOpen;
    return true;
  }
  // Move only changed rows: a progress update must not replace the focused node.
  function reconcile(parent, children) {
    const wanted = new Set(children);
    for (const child of [...parent.children]) if (!wanted.has(child)) child.remove();
    children.forEach((child, position) => { if (parent.children[position] !== child) parent.insertBefore(child, parent.children[position] || null); });
  }
  function createModule(module) {
    const section = el('section', undefined, 'rm-branch'), button = el('button', undefined, 'rm-module cursor-interaction');
    button.type = 'button'; button.dataset.moduleToggle = module.id;
    const kicker = el('span', '模块 ', 'rm-kicker'), fold = el('span'); fold.dataset.role = 'fold-symbol'; fold.setAttribute('aria-hidden', 'true'); kicker.append(fold);
    const title = el('strong'), summary = el('span', undefined, 'rm-small'), leaves = el('ul', undefined, 'rm-leaves');
    leaves.id = root.id + '-leaves-' + (++moduleSequence);
    button.setAttribute('aria-controls', leaves.id);
    button.append(kicker, title, summary); section.append(button, leaves);
    button.addEventListener('click', () => {
      state.collapsed.has(module.id) ? state.collapsed.delete(module.id) : state.collapsed.add(module.id);
      render(); persist();
    });
    return { section, button, title, summary, leaves, fold };
  }
  function createRequirement(item) {
    const row = el('li'), button = el('button', undefined, 'rm-node cursor-interaction');
    button.type = 'button'; button.dataset.requirement = item.id; button.setAttribute('aria-controls', root.id + '-inspector');
    const title = el('strong'), meta = el('span', undefined, 'rm-node-meta'), status = el('span'), coverage = el('span');
    status.dataset.nodeStatus = ''; coverage.dataset.nodeCoverage = ''; meta.append(status, coverage); button.append(title, meta); row.append(button);
    button.addEventListener('click', () => {
      if (state.selected !== item.id) get('sources-section').open = false;
      state.selected = item.id; state.detailOpen = true; render(true); persist();
      if (root.getBoundingClientRect().width <= 720 && typeof get('inspector').scrollIntoView === 'function') get('inspector').scrollIntoView({ block: 'nearest', behavior: 'auto' });
    });
    return { row, button, title, status, coverage };
  }
  function renderMap() {
    for (const [id, nodes] of moduleNodes) if (!moduleById.has(id)) { nodes.section.remove(); moduleNodes.delete(id); }
    for (const [id, nodes] of requirementNodes) if (!byId.has(id)) { nodes.row.remove(); requirementNodes.delete(id); }
    for (const module of modules) {
      let nodes = moduleNodes.get(module.id);
      if (!nodes) { nodes = createModule(module); moduleNodes.set(module.id, nodes); }
      const collapsed = state.collapsed.has(module.id), selected = byId.get(state.selected);
      nodes.title.textContent = text(module.title) || module.id;
      const unknown = module.requirements.filter(item => !item.coverage.known).length;
      nodes.summary.textContent = unknown === module.requirements.length && unknown > 0 ? `${unknown} 项覆盖待明确`
        : `${module.requirements.filter(fullyGenerated).length}/${module.requirements.length} 完整生成` + (unknown ? ` · 待明确 ${unknown}` : '');
      nodes.button.setAttribute('aria-expanded', String(!collapsed));
      nodes.button.setAttribute('aria-label', `${collapsed ? '展开' : '收起'}${text(module.title)}的 ${module.requirements.length} 个需求`);
      nodes.button.dataset.active = String(state.detailOpen && selected?.module.id === module.id);
      nodes.fold.textContent = collapsed ? '+' : '−'; nodes.leaves.hidden = collapsed;
      nodes.leaves.setAttribute('aria-label', `${text(module.title)}需求`);
      const rows = module.requirements.map(item => {
        let node = requirementNodes.get(item.id);
        if (!node) { node = createRequirement(item); requirementNodes.set(item.id, node); }
        const coverage = presentation(item);
        node.title.textContent = text(item.title) || item.id;
        node.button.setAttribute('aria-pressed', String(state.detailOpen && state.selected === item.id));
        node.button.dataset.demoStatus = coverage.state;
        node.status.textContent = coverage.label; node.status.dataset.tone = coverage.tone;
        node.coverage.textContent = coverage.known ? `${coverage.generated}/${coverage.total}` : '范围未声明';
        node.button.setAttribute('aria-label', `${text(item.title)}，${coverage.label}，${coverage.known ? coverage.total + ' 个页面状态，' : '覆盖范围未声明，'}已生成 ${coverage.generated} 个，已验证 ${coverage.verified} 个。查看详情`);
        return node.row;
      });
      reconcile(nodes.leaves, rows);
    }
    reconcile(get('branches'), modules.map(module => moduleNodes.get(module.id).section));
    get('empty').hidden = byId.size > 0; get('map').hidden = byId.size === 0;
  }
  function renderDetails() {
    const selected = byId.get(state.selected);
    get('inspector').hidden = !state.detailOpen;
    get('body').classList.toggle('rm-detail-closed', !state.detailOpen);
    get('detail-content').hidden = !selected; get('detail-empty').hidden = Boolean(selected);
    if (!selected) {
      get('detail-context').textContent = '需求详情';
      get('detail-title').textContent = state.selected ? '此需求已移出当前范围' : '选择一个需求';
      get('detail-empty').textContent = state.selected ? '需求清单已经更新，请在图中选择其他需求。' : '整理需求后，可在图中查看说明和 Demo 覆盖。';
      return;
    }
    const { item, module } = selected, coverage = presentation(item);
    get('detail-context').textContent = `${text(module.title)} · 需求详情`;
    get('detail-title').textContent = text(item.title);
    get('detail-status').textContent = coverage.label; get('detail-status').dataset.tone = coverage.tone;
    get('requirement-status').textContent = text(item.statusLabel);
    get('description').textContent = text(item.description) || '尚未提供需求说明。';
    get('business-acceptance').replaceChildren(...list(item.businessAcceptance).map(value => el('li', value)));
    get('business-acceptance-section').hidden = !list(item.businessAcceptance).length;
    get('generated-count').textContent = coverage.known ? `${coverage.generated}/${coverage.total}` : String(coverage.generated);
    get('verified-count').textContent = coverage.known ? `${coverage.verified}/${coverage.total}` : String(coverage.verified);
    const bar = get('coverage-bar'); bar.hidden = !coverage.known || coverage.total === 0;
    bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', String(coverage.total || 0)); bar.setAttribute('aria-valuenow', String(coverage.generated));
    bar.setAttribute('aria-valuetext', coverage.known ? `${coverage.total} 个页面状态，已生成 ${coverage.generated} 个，已验证 ${coverage.verified} 个` : '覆盖范围未声明');
    get('coverage-fill').style.width = coverage.known && coverage.total > 0 ? (coverage.generated / coverage.total * 100) + '%' : '0%';
    get('coverage-unknown').hidden = coverage.known;
    get('gap').textContent = text(coverage.summary); get('gap').hidden = !text(coverage.summary);
    get('criteria').replaceChildren(...list(item.acceptance).map((entry, position) => {
      const row = el('li', undefined, 'rm-criterion'), line = el('div', undefined, 'rm-criterion-line');
      row.dataset.criterion = text(entry.id) || String(position);
      const status = acceptanceStatuses[entry.state] || acceptanceStatuses.unknown;
      const label = el('span', text(entry.label) || status[0]); label.dataset.tone = status[1];
      line.append(el('span', text(entry.text) || text(entry.title)), label); row.append(line);
      if (entry.detail || entry.rule) row.append(el('p', text(entry.detail) || text(entry.rule)));
      return row;
    }));
    get('task-section').hidden = !item.task;
    get('task-status').textContent = text(item.task?.label);
    get('task-summary').textContent = text(item.task?.summary); get('task-summary').hidden = !text(item.task?.summary);
    get('pages-title').textContent = coverage.state === 'stale' ? '待更新的关联页面' : '关联页面';
    const pages = list(item.pages).map(page => {
      const row = el('li', undefined, 'rm-page'); row.dataset.page = text(page.id);
      row.append(el('span', text(page.title) || text(page.id)), el('span', page.label)); return row;
    });
    get('pages').replaceChildren(...(pages.length ? pages : [el('li', '尚未关联 Demo 页面', 'rm-small')]));
    const sources = list(item.sources);
    get('sources').replaceChildren(...(sources.length ? sources.map(source => {
      const section = el('section'); if (source.title) section.append(el('p', source.title));
      if (source.excerpt) section.append(el('p', source.excerpt)); return section;
    }) : [el('p', '尚未关联来源资料。')]));
  }
  function scheduleDraw() {
    if (disposed || typeof window.requestAnimationFrame !== 'function') return;
    if (frame) window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(draw);
  }
  function draw() {
    frame = 0;
    const svg = get('connections'), bounds = get('map').getBoundingClientRect();
    if (!bounds.width || !bounds.height) { svg.replaceChildren(); return; }
    svg.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
    const box = node => { const b = node.getBoundingClientRect(); return { left: b.left - bounds.left, right: b.right - bounds.left, top: b.top - bounds.top, bottom: b.bottom - bounds.top, cy: b.top - bounds.top + b.height / 2 }; };
    const project = box(get('project-node')), paths = [], selected = byId.get(state.selected);
    const path = (d, active) => { const node = document.createElementNS('http://www.w3.org/2000/svg', 'path'); node.setAttribute('d', d); node.setAttribute('class', 'rm-link'); node.dataset.active = String(active); paths.push(node); };
    for (const module of modules) {
      const bounds = box(moduleNodes.get(module.id).button), active = state.detailOpen && selected?.module.id === module.id;
      if (bounds.left > project.right) { const x = (project.right + bounds.left) / 2; path(`M ${project.right} ${project.cy} H ${x} V ${bounds.cy} H ${bounds.left}`, active); }
      else { const x = project.left + 8; path(`M ${x} ${project.bottom} V ${bounds.cy} H ${bounds.left}`, active); }
      if (state.collapsed.has(module.id)) continue;
      for (const item of module.requirements) {
        const leaf = box(requirementNodes.get(item.id).button), x = (bounds.right + leaf.left) / 2;
        path(`M ${bounds.right} ${bounds.cy} H ${x} V ${leaf.cy} H ${leaf.left}`, state.detailOpen && state.selected === item.id);
      }
    }
    svg.replaceChildren(...paths);
  }
  function render(announce = false) {
    const model = payload.requirementMap, snapshot = payload.snapshot, all = [...byId.values()].map(value => value.item);
    get('title').textContent = text(model.title) || '需求地图';
    get('context').textContent = text(model.context) || text(snapshot.project.name);
    get('source-label').textContent = text(model.sourceLabel) || (snapshot.historical ? '历史稿 · 只读' : '当前稿');
    const unknown = all.filter(item => !item.coverage.known).length;
    get('summary').textContent = unknown === all.length && unknown > 0 ? `${all.length} 个需求 · 覆盖待明确 ${unknown} 项`
      : `${all.length} 个需求 · 完整生成 ${all.filter(fullyGenerated).length}/${all.length} · 已验证 ${all.filter(fullyVerified).length}/${all.length}` + (unknown ? ` · 覆盖待明确 ${unknown} 项` : '');
    get('revision').textContent = snapshot.historical ? '历史版本 ' + snapshot.versionId : '修订 R' + snapshot.project.storedRevision;
    get('project-title').textContent = text(snapshot.project.name);
    get('project-summary').textContent = `${modules.length} 个模块 · ${all.length} 个需求`;
    renderMap(); renderDetails();
    get('footer-status').textContent = state.detailOpen && byId.has(state.selected) ? '正在查看「' + text(byId.get(state.selected).item.title) + '」' : state.detailOpen ? '请选择需求' : '详情已收起';
    const observed = new Date(snapshot.observedAt);
    get('observed-at').textContent = Number.isNaN(observed.valueOf()) ? '' : '数据更新于 ' + observed.toLocaleString('zh-CN', { hour12: false });
    if (announce) {
      const selected = byId.get(state.selected);
      get('announcer').textContent = selected ? `${text(selected.item.title)}：${presentation(selected.item).label}。` : '需求清单已更新。';
    }
    scheduleDraw();
  }
  function updateSnapshot(candidate) {
    const reject = reason => { lastUpdate = { applied: false, reason }; return false; };
    if (disposed || !validate(candidate)) return reject('invalid-snapshot');
    if (payload) {
      if (candidate.snapshot.project.id !== payload.snapshot.project.id || candidate.snapshot.versionId !== payload.snapshot.versionId
        || candidate.snapshot.historical !== payload.snapshot.historical || candidate.requirementMap.scopeKey !== payload.requirementMap.scopeKey) return reject('scope-mismatch');
      if (candidate.snapshot.project.storedRevision < payload.snapshot.project.storedRevision) return reject('older-revision');
      const previousSequence = payload.requirementMap.sequence, nextSequence = candidate.requirementMap.sequence;
      if (Number.isInteger(previousSequence) && Number.isInteger(nextSequence) && nextSequence < previousSequence) return reject('older-sequence');
    }
    let next;
    try { next = JSON.parse(JSON.stringify(candidate)); } catch (_) { return reject('invalid-snapshot'); }
    const initial = !payload, focused = root.contains(document.activeElement) ? document.activeElement : null;
    payload = next; index();
    state.collapsed = new Set([...state.collapsed].filter(id => moduleById.has(id)));
    if (initial) {
      state.selected = byId.has(payload.snapshot.scope?.requirementId) ? payload.snapshot.scope.requirementId : byId.keys().next().value || null;
      restore(window.openai?.widgetState);
    }
    get('body').hidden = false;
    render(!initial);
    if (focused && !focused.isConnected && state.detailOpen && !byId.has(state.selected)) root.querySelector('[data-action="close-detail"]').focus();
    lastUpdate = { applied: true, snapshotId: payload.snapshot.snapshotId };
    return true;
  }
  function onSnapshot(event) { updateSnapshot(event.detail); root.dispatchEvent(new CustomEvent('prototype-flow:requirement-map-updated', { detail: { ...lastUpdate } })); }
  function onGlobals(event) { if (payload && restore(event.detail?.globals?.widgetState)) render(); }
  get('inspector').querySelector('[data-action="close-detail"]').addEventListener('click', () => {
    state.detailOpen = false; render(); persist();
    const selected = byId.get(state.selected);
    if (selected) (state.collapsed.has(selected.module.id) ? moduleNodes.get(selected.module.id).button : requirementNodes.get(state.selected).button).focus();
  });
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleDraw) : null;
  root.requirementMap = Object.freeze({
    updateSnapshot,
    getState: () => ({ selected: state.selected, collapsed: [...state.collapsed], detailOpen: state.detailOpen, snapshotId: payload?.snapshot.snapshotId, lastUpdate: { ...lastUpdate } }),
    destroy: () => { disposed = true; if (frame) window.cancelAnimationFrame(frame); observer?.disconnect(); window.removeEventListener('resize', scheduleDraw); window.removeEventListener('openai:set_globals', onGlobals); root.removeEventListener('prototype-flow:requirement-map-snapshot', onSnapshot); }
  });
  root.addEventListener('prototype-flow:requirement-map-snapshot', onSnapshot);
  window.addEventListener('openai:set_globals', onGlobals); window.addEventListener('resize', scheduleDraw);
  observer?.observe(get('map')); document.fonts?.ready.then(scheduleDraw);
  let initial;
  try { initial = JSON.parse(get('payload').textContent); } catch (_) { initial = null; }
  if (!updateSnapshot(initial)) { get('summary').textContent = '需求数据格式不正确，请重新读取。'; get('body').hidden = true; }
})();
