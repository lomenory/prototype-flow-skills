(() => {
  'use strict';
  const root = document.getElementById('__ROOT_ID__');
  if (!root) return;
  const get = role => root.querySelector(`[data-role="${role}"]`);
  const action = name => root.querySelector(`[data-action="${name}"]`);
  const contract = 'prototype-flow.requirement-map/1';
  const stateContract = 'prototype-flow.requirement-map-view/2';
  const legacyStateContract = 'prototype-flow.requirement-map-view/1';
  const statuses = {
    'not-generated': ['未生成', 'neutral'], generating: ['生成中', 'blue'], blocked: ['受阻', 'red'],
    partial: ['部分生成', 'orange'], generated: ['待验证', 'blue'], verified: ['已验证', 'green'],
    stale: ['需更新', 'orange'], unknown: ['待核对', 'neutral']
  };
  const acceptanceStatuses = { generated: ['待验证', 'blue'], verified: ['已验证', 'green'], missing: ['未生成', 'neutral'], stale: ['需更新', 'orange'], unknown: ['待核对', 'neutral'] };
  const tabs = ['requirement', 'coverage', 'sources'];
  const text = value => ['string', 'number'].includes(typeof value) ? String(value) : '';
  const list = value => Array.isArray(value) ? value : [];
  const el = (tag, value, className) => {
    const element = document.createElement(tag);
    if (value !== undefined) element.textContent = text(value);
    if (className) element.className = className;
    return element;
  };
  const idPresent = value => typeof value === 'string' && value.length > 0;
  const normalize = candidate => candidate && ({ snapshot: candidate.snapshot, requirementMap: candidate.requirementMap || candidate.snapshot?.data?.requirementMap });
  const emptyPosition = () => ({ top: 0, left: 0, anchor: null });
  let payload, modules = [], byId = new Map(), moduleById = new Map(), frame = 0, disposed = false, moduleSequence = 0, persistenceFrame = 0;
  let lastUpdate = { applied: false, reason: 'not-initialized' };
  const moduleNodes = new Map(), requirementNodes = new Map(), keyedChildren = new WeakMap();
  const state = { selected: null, collapsed: new Set(), detailOpen: true, query: '', moduleFilter: '', statusFilter: '', viewMode: 'graph', activeDetailTab: 'requirement', expandedCoverage: new Set(), scroll: { map: emptyPosition(), details: {} } };
  const detailKey = () => `${state.selected || ''}::${state.activeDetailTab}`;

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
        if (item.acceptance !== undefined && (!Array.isArray(item.acceptance) || item.acceptance.some(entry => !entry || typeof entry !== 'object'))) return false;
        if (item.businessAcceptance !== undefined && (!Array.isArray(item.businessAcceptance) || item.businessAcceptance.some(entry => typeof entry !== 'string'))) return false;
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
  function fullyGenerated(item) { const value = item.coverage; return value.known && value.total > 0 && value.generated === value.total && value.state !== 'stale'; }
  function fullyVerified(item) { return fullyGenerated(item) && item.coverage.verified === item.coverage.total && item.coverage.state === 'verified'; }
  function matches(item, module) {
    const query = state.query.trim().toLocaleLowerCase();
    return (!state.moduleFilter || module.id === state.moduleFilter) && (!state.statusFilter || item.coverage.state === state.statusFilter)
      && (!query || `${item.id} ${text(item.title)}`.toLocaleLowerCase().includes(query));
  }
  function filteredModules() { return modules.map(module => ({ module, items: module.requirements.filter(item => matches(item, module)) })).filter(entry => entry.items.length); }
  function cleanPosition(value) {
    if (!value || typeof value !== 'object') return emptyPosition();
    const finite = number => typeof number === 'number' && Number.isFinite(number) && number >= 0 ? number : 0;
    return { top: finite(value.top), left: finite(value.left), anchor: idPresent(value.anchor?.key) && Number.isFinite(value.anchor.offset) ? { key: value.anchor.key, offset: value.anchor.offset } : null };
  }
  function capturePosition(region) {
    const bounds = region.getBoundingClientRect(), position = { top: region.scrollTop, left: region.scrollLeft, anchor: null };
    if (!bounds.height) return position;
    const candidates = [...region.querySelectorAll('[data-scroll-key]')].map(node => ({ node, box: node.getBoundingClientRect() }))
      .filter(entry => entry.box.height > 0 && entry.box.bottom > bounds.top + 1 && entry.box.top < bounds.bottom && !entry.node.closest('[hidden]'))
      .sort((a, b) => a.box.top - b.box.top);
    // Prefer the first readable row that starts inside the viewport. A clipped row above
    // it may grow as evidence arrives; anchoring that clipped row would push the reader's row.
    const anchor = candidates.find(entry => entry.box.top >= bounds.top - 1) || candidates[0];
    if (anchor) position.anchor = { key: anchor.node.dataset.scrollKey, offset: anchor.box.top - bounds.top };
    return position;
  }
  function rememberDetails(position) {
    const key = detailKey();
    delete state.scroll.details[key]; state.scroll.details[key] = position;
    while (Object.keys(state.scroll.details).length > 12) delete state.scroll.details[Object.keys(state.scroll.details)[0]];
  }
  function captureScrolls() {
    if (!payload) return;
    // Native toggle events can arrive after a snapshot; the visible disclosure state is authoritative.
    for (const details of get('criteria').querySelectorAll('[data-coverage-id]')) {
      const key = `${state.selected}::${details.dataset.coverageId}`;
      details.open ? state.expandedCoverage.add(key) : state.expandedCoverage.delete(key);
    }
    while (state.expandedCoverage.size > 128) state.expandedCoverage.delete(state.expandedCoverage.values().next().value);
    // A hidden mobile viewport retains its last reading position, rather than a zero-sized anchor.
    if (!(state.detailOpen && root.getBoundingClientRect().width > 0 && root.getBoundingClientRect().width < 720)) state.scroll.map = capturePosition(get('map-scroll'));
    if (state.detailOpen) rememberDetails(capturePosition(get('detail-scroll')));
  }
  function restorePosition(region, position) {
    if (!position) position = emptyPosition();
    region.scrollTop = position.top; region.scrollLeft = position.left;
    if (!position.anchor) return;
    const anchor = [...region.querySelectorAll('[data-scroll-key]')].find(node => node.dataset.scrollKey === position.anchor.key && !node.closest('[hidden]'));
    const bounds = region.getBoundingClientRect(), box = anchor?.getBoundingClientRect();
    if (box?.height > 0 && bounds.height > 0) region.scrollTop += box.top - bounds.top - position.anchor.offset;
  }
  function restoreScrolls() {
    restorePosition(get('map-scroll'), state.scroll.map);
    restorePosition(get('detail-scroll'), state.scroll.details[detailKey()]);
  }
  function boundedView() {
    return { contract: stateContract, projectId: payload.snapshot.project.id, versionId: payload.snapshot.versionId,
      scopeKey: payload.requirementMap.scopeKey, selected: state.selected, collapsed: [...state.collapsed], detailOpen: state.detailOpen,
      query: state.query, moduleFilter: state.moduleFilter, statusFilter: state.statusFilter, viewMode: state.viewMode,
      activeDetailTab: state.activeDetailTab, expandedCoverage: [...state.expandedCoverage].slice(-128), scroll: JSON.parse(JSON.stringify(state.scroll)) };
  }
  function persist() {
    if (!payload || typeof window.openai?.setWidgetState !== 'function') return;
    const selected = byId.get(state.selected), value = selected && presentation(selected.item);
    const saved = { modelContent: { projectId: payload.snapshot.project.id, snapshotId: payload.snapshot.snapshotId,
      requirementId: selected?.item.id || null, requirementTitle: selected?.item.title || null, demoStatus: value?.state || null,
      generated: value?.generated ?? null, verified: value?.verified ?? null, total: value?.known ? value.total : null }, privateContent: boundedView() };
    const size = () => new TextEncoder().encode(JSON.stringify(saved)).length;
    // View-state caches are disposable; the selected node, controls and unfolding choices have priority.
    if (size() >= 16 * 1024) saved.privateContent = { ...saved.privateContent, scroll: { map: state.scroll.map, details: {} } };
    if (size() >= 16 * 1024) saved.privateContent.expandedCoverage = saved.privateContent.expandedCoverage.slice(-32);
    if (size() >= 16 * 1024) return;
    try { Promise.resolve(window.openai.setWidgetState(saved)).catch(() => {}); } catch (_) { /* Optional host state must not interrupt reading. */ }
  }
  function schedulePersist() {
    if (persistenceFrame || disposed || typeof window.requestAnimationFrame !== 'function') return;
    persistenceFrame = window.requestAnimationFrame(() => { persistenceFrame = 0; captureScrolls(); persist(); });
  }
  function restore(saved) {
    const value = saved?.privateContent;
    if (![stateContract, legacyStateContract].includes(value?.contract) || value.projectId !== payload.snapshot.project.id
      || value.versionId !== payload.snapshot.versionId || value.scopeKey !== payload.requirementMap.scopeKey) return false;
    if (byId.has(value.selected)) state.selected = value.selected;
    state.collapsed = new Set(list(value.collapsed).filter(id => moduleById.has(id)));
    if (typeof value.detailOpen === 'boolean') state.detailOpen = value.detailOpen;
    if (value.contract === stateContract) {
      state.query = text(value.query).slice(0, 200); state.moduleFilter = typeof value.moduleFilter === 'string' ? value.moduleFilter : '';
      state.statusFilter = Object.hasOwn(statuses, value.statusFilter) ? value.statusFilter : '';
      state.viewMode = value.viewMode === 'list' ? 'list' : 'graph'; state.activeDetailTab = tabs.includes(value.activeDetailTab) ? value.activeDetailTab : 'requirement';
      state.expandedCoverage = new Set(list(value.expandedCoverage).filter(idPresent).slice(-128));
      state.scroll.map = cleanPosition(value.scroll?.map);
      state.scroll.details = Object.fromEntries(Object.entries(value.scroll?.details || {}).slice(-12).map(([key, position]) => [key, cleanPosition(position)]));
    }
    return true;
  }
  // Reconcile stable rows without replacing keyboard focus or native <details> state.
  function reconcile(parent, children) {
    const wanted = new Set(children);
    for (const child of [...parent.children]) if (!wanted.has(child)) child.remove();
    children.forEach((child, position) => { if (parent.children[position] !== child) parent.insertBefore(child, parent.children[position] || null); });
  }
  function keyed(parent, entries, keyFor, create, update) {
    let cache = keyedChildren.get(parent);
    if (!cache) { cache = new Map(); keyedChildren.set(parent, cache); }
    const wanted = new Set();
    const children = entries.map((entry, position) => {
      const key = keyFor(entry, position); wanted.add(key);
      let node = cache.get(key);
      if (!node) { node = create(entry, key, position); cache.set(key, node); }
      update(node, entry, key, position); return node.element || node;
    });
    for (const key of cache.keys()) if (!wanted.has(key)) cache.delete(key);
    reconcile(parent, children);
  }
  function transact(change, { announce = false, preserve = true } = {}) {
    captureScrolls(); change(); render(announce); if (preserve) restoreScrolls(); persist();
  }
  function createModule(module) {
    const section = el('section', undefined, 'rm-branch'), button = el('button', undefined, 'rm-module cursor-interaction');
    button.type = 'button'; button.dataset.moduleToggle = module.id; button.dataset.scrollKey = `module:${module.id}`;
    const kicker = el('span', undefined, 'rm-kicker'), kind = el('span', '模块'), fold = el('span'); fold.setAttribute('aria-hidden', 'true'); kicker.append(kind, fold);
    const title = el('strong'), summary = el('span', undefined, 'rm-small'), leaves = el('ul', undefined, 'rm-leaves');
    leaves.id = root.id + '-leaves-' + (++moduleSequence); button.setAttribute('aria-controls', leaves.id);
    button.append(kicker, title, summary); section.append(button, leaves);
    button.addEventListener('click', () => transact(() => { state.collapsed.has(module.id) ? state.collapsed.delete(module.id) : state.collapsed.add(module.id); }));
    return { section, button, title, summary, leaves, fold };
  }
  function createRequirement(item) {
    const row = el('li'), button = el('button', undefined, 'rm-node cursor-interaction');
    button.type = 'button'; button.dataset.requirement = item.id; button.dataset.scrollKey = `requirement:${item.id}`; button.setAttribute('aria-controls', root.id + '-inspector');
    const title = el('strong'), meta = el('span', undefined, 'rm-node-meta'), status = el('span'), coverage = el('span');
    status.dataset.nodeStatus = ''; coverage.dataset.nodeCoverage = ''; meta.append(status, coverage); button.append(title, meta); row.append(button);
    button.addEventListener('click', () => {
      transact(() => { state.selected = item.id; state.detailOpen = true; }, { announce: true });
      if (root.getBoundingClientRect().width > 0 && root.getBoundingClientRect().width < 720) get('detail-scroll').focus({ preventScroll: true });
    });
    return { row, button, title, status, coverage };
  }
  function renderMap() {
    const filtered = filteredModules(), shown = new Map(filtered.map(entry => [entry.module.id, entry.items]));
    for (const [id, nodes] of moduleNodes) if (!moduleById.has(id)) { nodes.section.remove(); moduleNodes.delete(id); }
    for (const [id, nodes] of requirementNodes) if (!byId.has(id)) { nodes.row.remove(); requirementNodes.delete(id); }
    for (const module of modules) {
      let nodes = moduleNodes.get(module.id);
      if (!nodes) { nodes = createModule(module); moduleNodes.set(module.id, nodes); }
      const items = shown.get(module.id) || [], collapsed = state.collapsed.has(module.id), selected = byId.get(state.selected);
      nodes.section.hidden = !items.length; nodes.title.textContent = text(module.title) || module.id;
      const unknown = module.requirements.filter(item => !item.coverage.known).length;
      nodes.summary.textContent = unknown === module.requirements.length && unknown > 0 ? `${unknown} 项覆盖待明确`
        : `${module.requirements.length} 项 · ${module.requirements.filter(fullyGenerated).length} 完整生成` + (unknown ? ` · ${unknown} 待明确` : '');
      nodes.button.setAttribute('aria-expanded', String(!collapsed));
      nodes.button.setAttribute('aria-label', `${collapsed ? '展开' : '收起'}${text(module.title)}的 ${items.length} 个需求`);
      nodes.button.dataset.active = String(state.detailOpen && selected?.module.id === module.id);
      nodes.fold.textContent = collapsed ? '+' : '−'; nodes.leaves.hidden = collapsed; nodes.leaves.setAttribute('aria-label', `${text(module.title)}需求`);
      const rows = module.requirements.map(item => {
        let node = requirementNodes.get(item.id);
        if (!node) { node = createRequirement(item); requirementNodes.set(item.id, node); }
        const coverage = presentation(item);
        node.row.hidden = !matches(item, module); node.title.textContent = text(item.title) || item.id;
        node.button.setAttribute('aria-pressed', String(state.detailOpen && state.selected === item.id)); node.button.dataset.demoStatus = coverage.state;
        node.status.textContent = coverage.label; node.status.dataset.tone = coverage.tone;
        node.coverage.textContent = coverage.known ? `${coverage.generated}/${coverage.total}` : '范围未声明';
        node.button.setAttribute('aria-label', `${text(item.title)}，${item.id}，${coverage.label}，${coverage.known ? coverage.total + ' 个页面状态，' : '覆盖范围未声明，'}已生成 ${coverage.generated} 个，已验证 ${coverage.verified} 个。查看详情`);
        return node.row;
      });
      reconcile(nodes.leaves, rows);
    }
    reconcile(get('branches'), modules.map(module => moduleNodes.get(module.id).section));
    const count = filtered.reduce((total, entry) => total + entry.items.length, 0);
    get('result-count').textContent = `显示 ${count}/${byId.size}`;
    get('result-count').hidden = !state.query && !state.moduleFilter && !state.statusFilter;
    get('empty').hidden = count > 0; get('empty').textContent = byId.size ? '没有符合筛选条件的需求。调整搜索或筛选后继续核对。' : '当前范围尚未整理需求。'; get('map').hidden = count === 0;
  }
  function renderPage(parent, pages, keyPrefix) {
    keyed(parent, pages, (page, position) => keyPrefix + ':' + (text(page.id) || position), () => {
      const element = el('li', undefined, 'rm-page'), line = el('div', undefined, 'rm-page-line'), title = el('span'), status = el('span'), evidence = el('p'), route = el('p');
      line.append(title, status); element.append(line, route, evidence); return { element, title, status, evidence, route };
    }, (node, page) => {
      node.element.dataset.page = text(page.id); node.title.textContent = text(page.title) || text(page.id); node.status.textContent = text(page.label);
      node.route.textContent = [text(page.screenId), text(page.stateId), text(page.fixtureId)].filter(Boolean).join(' / ') || text(page.route); node.route.hidden = !node.route.textContent;
      const evidence = typeof page.evidence === 'string' ? page.evidence : page.evidence && typeof page.evidence === 'object' ? Object.entries(page.evidence).filter(([, value]) => ['string', 'number'].includes(typeof value)).map(([key, value]) => `${key}: ${text(value)}`).join('\n') : '';
      node.evidence.textContent = evidence || (text(page.verificationStatus) ? '验证记录：' + text(page.verificationStatus) : '尚无验证依据。');
    });
  }
  function matchesPage(entry, page) {
    if (list(entry.bindingIds).includes(page.id)) return true;
    return idPresent(entry.screenId) && idPresent(entry.stateId) && entry.screenId === page.screenId && entry.stateId === page.stateId
      && (!Object.hasOwn(entry, 'fixtureId') || entry.fixtureId === page.fixtureId);
  }
  function renderDetails() {
    const selected = byId.get(state.selected);
    get('inspector').hidden = !state.detailOpen; get('body').classList.toggle('rm-detail-closed', !state.detailOpen);
    action('open-detail').hidden = state.detailOpen || !selected; action('locate-current').disabled = !selected;
    get('detail-content').hidden = !selected; get('detail-empty').hidden = Boolean(selected); get('detail-tabs').hidden = !selected;
    get('filter-notice').hidden = !selected || matches(selected.item, selected.module);
    if (!selected) {
      get('detail-context').textContent = '需求详情'; get('detail-title').textContent = state.selected ? '此需求已移出当前范围' : '选择一个需求';
      get('detail-empty').textContent = state.selected ? '需求清单已经更新，请在图中选择其他需求。' : '整理需求后，可在图中查看说明和 Demo 覆盖。'; get('full-title').hidden = true;
      return;
    }
    const { item, module } = selected, coverage = presentation(item);
    get('detail-context').textContent = `${text(module.title)} · ${item.id}`; get('detail-title').textContent = text(item.title);
    get('full-title-text').textContent = text(item.title); get('full-title').hidden = text(item.title).length <= 32;
    get('detail-status').textContent = coverage.label; get('detail-status').dataset.tone = coverage.tone; get('requirement-status').textContent = text(item.statusLabel);
    get('description').textContent = text(item.description) || '尚未提供需求说明。';
    keyed(get('business-acceptance'), list(item.businessAcceptance), (value, position) => item.id + ':' + position, () => el('li'), (node, value) => { node.textContent = text(value); });
    get('business-acceptance-section').hidden = !list(item.businessAcceptance).length;
    get('generated-count').textContent = coverage.known ? `${coverage.generated}/${coverage.total}` : String(coverage.generated); get('verified-count').textContent = coverage.known ? `${coverage.verified}/${coverage.total}` : String(coverage.verified);
    const bar = get('coverage-bar'); bar.hidden = !coverage.known || coverage.total === 0;
    bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', String(coverage.total || 0)); bar.setAttribute('aria-valuenow', String(coverage.generated));
    bar.setAttribute('aria-valuetext', coverage.known ? `${coverage.total} 个页面状态，已生成 ${coverage.generated} 个，已验证 ${coverage.verified} 个` : '覆盖范围未声明');
    get('coverage-fill').style.width = coverage.known && coverage.total > 0 ? (coverage.generated / coverage.total * 100) + '%' : '0%';
    get('coverage-unknown').hidden = coverage.known; get('gap').textContent = text(coverage.summary); get('gap').hidden = !text(coverage.summary);
    const usedPages = new Set();
    keyed(get('criteria'), list(item.acceptance), (entry, position) => `${item.id}::${text(entry.id) || position}`, (entry, key) => {
      const element = el('li', undefined, 'rm-criterion'), details = el('details'), summary = el('summary'), name = el('span', undefined, 'rm-criterion-name'), status = el('span', undefined, 'rm-criterion-status'), body = el('div', undefined, 'rm-criterion-body'), rule = el('p'), pages = el('ul', undefined, 'rm-pages'), empty = el('p');
      summary.append(name, status); body.append(rule, pages, empty); details.append(summary, body); element.append(details);
      details.addEventListener('toggle', () => { if (disposed || !details.isConnected) return; details.open ? state.expandedCoverage.add(key) : state.expandedCoverage.delete(key); while (state.expandedCoverage.size > 128) state.expandedCoverage.delete(state.expandedCoverage.values().next().value); schedulePersist(); });
      return { element, details, name, status, rule, pages, empty };
    }, (node, entry, key, position) => {
      node.element.dataset.criterion = text(entry.id) || String(position); node.element.dataset.scrollKey = `coverage:${text(entry.id) || position}`; node.details.dataset.coverageId = text(entry.id) || String(position);
      const status = acceptanceStatuses[entry.state] || acceptanceStatuses.unknown;
      node.name.textContent = text(entry.text) || text(entry.title); node.status.textContent = text(entry.label) || status[0]; node.status.dataset.tone = status[1];
      node.rule.textContent = text(entry.detail) || text(entry.rule); node.rule.hidden = !node.rule.textContent;
      const pages = list(item.pages).filter(page => matchesPage(entry, page)); pages.forEach(page => usedPages.add(page.id)); renderPage(node.pages, pages, key);
      node.empty.textContent = entry.state === 'missing' ? '此页面状态尚未生成，暂无关联页面或验证记录。' : '尚未关联此页面状态的详细页面记录。'; node.empty.hidden = pages.length > 0;
      node.details.open = state.expandedCoverage.has(key);
    });
    get('task-section').hidden = !item.task; get('task-status').textContent = text(item.task?.label); get('task-summary').textContent = text(item.task?.summary); get('task-summary').hidden = !text(item.task?.summary);
    const otherPages = list(item.pages).filter(page => !usedPages.has(page.id));
    get('pages-title').textContent = coverage.state === 'stale' ? '待更新的其他关联页面' : '其他关联页面'; renderPage(get('pages'), otherPages, item.id + ':other');
    get('pages-section').hidden = !otherPages.length;
    keyed(get('sources'), list(item.sources), (source, position) => item.id + ':' + (text(source.id) || position), () => {
      const element = el('section'), title = el('p'), excerpt = el('p'); element.append(title, excerpt); return { element, title, excerpt };
    }, (node, source, key, position) => { node.element.dataset.scrollKey = 'source:' + (text(source.id) || position); node.title.textContent = text(source.title); node.title.hidden = !node.title.textContent; node.excerpt.textContent = text(source.excerpt); node.excerpt.hidden = !node.excerpt.textContent; });
    if (!list(item.sources).length) keyed(get('sources'), [{ title: '尚未关联来源资料。' }], () => item.id + ':empty', () => el('p'), (node, source) => { node.textContent = source.title; });
    tabs.forEach(tab => {
      const button = root.querySelector(`[data-detail-tab="${tab}"]`), active = state.activeDetailTab === tab;
      button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; get('tab-' + tab).hidden = !active;
    });
  }
  function renderControls() {
    get('search').value = state.query;
    keyed(get('module-filter'), [{ id: '', title: '全部模块' }, ...modules], module => module.id, () => el('option'), (node, module) => { node.value = module.id; node.textContent = text(module.title) || module.id; });
    // A removed module is kept as an explicit empty filter until the user changes it.
    if (state.moduleFilter && !moduleById.has(state.moduleFilter)) { const option = el('option', '原模块已移出范围'); option.value = state.moduleFilter; get('module-filter').append(option); }
    get('module-filter').value = state.moduleFilter; get('status-filter').value = state.statusFilter;
    root.dataset.viewMode = state.viewMode;
    action('view-graph').setAttribute('aria-pressed', String(state.viewMode === 'graph')); action('view-list').setAttribute('aria-pressed', String(state.viewMode === 'list'));
  }
  function scheduleDraw() {
    if (disposed || typeof window.requestAnimationFrame !== 'function') return;
    if (frame) window.cancelAnimationFrame(frame); frame = window.requestAnimationFrame(draw);
  }
  function draw() {
    frame = 0; const svg = get('connections'), bounds = get('map').getBoundingClientRect();
    if (!bounds.width || !bounds.height || state.viewMode === 'list') { svg.replaceChildren(); return; }
    svg.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
    const box = node => { const b = node.getBoundingClientRect(); return { left: b.left - bounds.left, right: b.right - bounds.left, top: b.top - bounds.top, bottom: b.bottom - bounds.top, cy: b.top - bounds.top + b.height / 2 }; };
    const project = box(get('project-node')), paths = [], selected = byId.get(state.selected);
    const path = (d, active) => { const node = document.createElementNS('http://www.w3.org/2000/svg', 'path'); node.setAttribute('d', d); node.setAttribute('class', 'rm-link'); node.dataset.active = String(active); paths.push(node); };
    for (const { module, items } of filteredModules()) {
      const b = box(moduleNodes.get(module.id).button), active = state.detailOpen && selected?.module.id === module.id;
      if (b.left > project.right) { const x = (project.right + b.left) / 2; path(`M ${project.right} ${project.cy} H ${x} V ${b.cy} H ${b.left}`, active); }
      else { const x = project.left + 8; path(`M ${x} ${project.bottom} V ${b.cy} H ${b.left}`, active); }
      if (state.collapsed.has(module.id)) continue;
      for (const item of items) { const leaf = box(requirementNodes.get(item.id).button), x = (b.right + leaf.left) / 2; path(`M ${b.right} ${b.cy} H ${x} V ${leaf.cy} H ${leaf.left}`, state.detailOpen && state.selected === item.id); }
    }
    svg.replaceChildren(...paths);
  }
  function render(announce = false) {
    const model = payload.requirementMap, snapshot = payload.snapshot, all = [...byId.values()].map(value => value.item);
    get('title').textContent = text(snapshot.project.name) || text(model.context) || '需求地图'; get('context').textContent = text(model.title) || '需求地图';
    get('source-label').textContent = text(model.sourceLabel) || (snapshot.historical ? '历史稿 · 只读' : '当前稿');
    const unknown = all.filter(item => !item.coverage.known).length;
    get('summary').textContent = unknown === all.length && unknown > 0 ? `${all.length} 个需求 · 覆盖待明确 ${unknown} 项`
      : `${all.length} 个需求 · 完整生成 ${all.filter(fullyGenerated).length}/${all.length} · 已验证 ${all.filter(fullyVerified).length}/${all.length}` + (unknown ? ` · 覆盖待明确 ${unknown} 项` : '');
    get('compact-summary').textContent = unknown === all.length && unknown > 0 ? `${all.length} 个需求 · 覆盖待明确` : `${all.length} 个需求 · 已验证 ${all.filter(fullyVerified).length}/${all.length}`;
    get('revision').textContent = snapshot.historical ? '历史稿' : 'R' + snapshot.project.storedRevision;
    get('revision').title = snapshot.historical ? '历史版本 ' + snapshot.versionId : '当前工作稿 · 修订 R' + snapshot.project.storedRevision;
    get('project-title').textContent = text(snapshot.project.name); get('project-summary').textContent = `${modules.length} 个模块 · ${all.length} 个需求`;
    root.dataset.selectedRequirement = state.selected || ''; root.dataset.activeDetailTab = state.activeDetailTab;
    renderControls(); renderMap(); renderDetails();
    const current = byId.get(state.selected);
    get('footer-status').textContent = state.detailOpen && current ? matches(current.item, current.module) ? '正在查看「' + text(current.item.title) + '」' : '当前需求不在筛选结果中 · 详情保留' : state.detailOpen ? '请选择需求' : '详情已收起';
    const observed = new Date(snapshot.observedAt); get('observed-at').textContent = Number.isNaN(observed.valueOf()) ? '' : '数据更新于 ' + observed.toLocaleString('zh-CN', { hour12: false });
    if (announce) { const selected = byId.get(state.selected); get('announcer').textContent = selected ? `${text(selected.item.title)}：${presentation(selected.item).label}。` : '需求清单已更新。'; }
    scheduleDraw();
  }
  function updateSnapshot(candidate) {
    const reject = reason => { lastUpdate = { applied: false, reason }; return false; };
    candidate = normalize(candidate);
    if (disposed || !validate(candidate)) return reject('invalid-snapshot');
    if (payload) {
      if (candidate.snapshot.project.id !== payload.snapshot.project.id || candidate.snapshot.versionId !== payload.snapshot.versionId
        || candidate.snapshot.historical !== payload.snapshot.historical || candidate.requirementMap.scopeKey !== payload.requirementMap.scopeKey) return reject('scope-mismatch');
      if (candidate.snapshot.project.storedRevision < payload.snapshot.project.storedRevision) return reject('older-revision');
      const previousSequence = payload.requirementMap.sequence, nextSequence = candidate.requirementMap.sequence;
      if (Number.isInteger(previousSequence) && Number.isInteger(nextSequence) && nextSequence < previousSequence) return reject('older-sequence');
    }
    let next; try { next = JSON.parse(JSON.stringify(candidate)); } catch (_) { return reject('invalid-snapshot'); }
    const initial = !payload, focused = root.contains(document.activeElement) ? document.activeElement : null;
    if (!initial) captureScrolls();
    const previousModules = new Set(moduleById.keys()); payload = next; index();
    state.collapsed = new Set([...state.collapsed].filter(id => moduleById.has(id)));
    if (initial) {
      state.selected = byId.has(payload.snapshot.scope?.requirementId) ? payload.snapshot.scope.requirementId : byId.keys().next().value || null;
      const selectedModule = byId.get(state.selected)?.module.id;
      state.collapsed = new Set(modules.filter(module => module.id !== selectedModule).map(module => module.id)); restore(window.openai?.widgetState);
    } else for (const module of modules) if (!previousModules.has(module.id)) state.collapsed.add(module.id);
    get('body').hidden = false; render(!initial); restoreScrolls();
    if (focused && !focused.isConnected && state.detailOpen && !byId.has(state.selected)) action('close-detail').focus({ preventScroll: true });
    lastUpdate = { applied: true, snapshotId: payload.snapshot.snapshotId }; return true;
  }
  function onSnapshot(event) { updateSnapshot(event.detail); root.dispatchEvent(new CustomEvent('prototype-flow:requirement-map-updated', { detail: { ...lastUpdate } })); }
  function onGlobals(event) { if (payload && restore(event.detail?.globals?.widgetState)) { render(); restoreScrolls(); } }
  function changeFilter() {
    transact(() => {
      state.query = get('search').value.slice(0, 200); state.moduleFilter = get('module-filter').value; state.statusFilter = get('status-filter').value;
      // Revealing matches is an explicit user filter action; later data updates never unfold modules.
      if (state.query || state.moduleFilter || state.statusFilter) for (const { module } of filteredModules()) state.collapsed.delete(module.id);
      state.scroll.map = emptyPosition();
    });
  }
  function activateTab(tab, focus = false) {
    if (!tabs.includes(tab) || state.activeDetailTab === tab) return;
    transact(() => { state.activeDetailTab = tab; });
    if (focus) root.querySelector(`[data-detail-tab="${tab}"]`).focus({ preventScroll: true });
  }
  const toolsTrigger = action('more-tools'), toolsMenu = get('tool-menu');
  const menuItems = () => [...toolsMenu.querySelectorAll('[role="menuitem"]')].filter(node => !node.disabled && !node.hidden);
  function closeTools(focus = false) {
    toolsMenu.hidden = true; toolsTrigger.setAttribute('aria-expanded', 'false');
    if (focus) toolsTrigger.focus({ preventScroll: true });
  }
  function openTools(last = false) {
    toolsMenu.hidden = false; toolsTrigger.setAttribute('aria-expanded', 'true');
    const items = menuItems(); (last ? items.at(-1) : items[0])?.focus({ preventScroll: true });
  }
  function onOutsideTools(event) {
    if (!toolsMenu.hidden && !toolsMenu.contains(event.target) && !toolsTrigger.contains(event.target)) closeTools();
  }
  toolsTrigger.addEventListener('click', () => toolsMenu.hidden ? openTools() : closeTools(true));
  toolsTrigger.addEventListener('keydown', event => {
    if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); openTools(event.key === 'ArrowUp'); }
    else if (event.key === 'Escape') { event.preventDefault(); closeTools(true); }
  });
  toolsMenu.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); closeTools(true); return; }
    if (event.key === 'Tab') { closeTools(true); return; }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); const items = menuItems(), position = items.indexOf(document.activeElement);
    const target = event.key === 'Home' ? items[0] : event.key === 'End' ? items.at(-1) : items[(position + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length];
    target?.focus({ preventScroll: true });
  });
  document.addEventListener('pointerdown', onOutsideTools);
  get('search').addEventListener('input', changeFilter); get('module-filter').addEventListener('change', changeFilter); get('status-filter').addEventListener('change', changeFilter);
  for (const [name, label] of Object.entries(statuses)) { const option = el('option', label[0]); option.value = name; get('status-filter').append(option); }
  tabs.forEach(tab => {
    const button = root.querySelector(`[data-detail-tab="${tab}"]`);
    button.addEventListener('click', () => activateTab(tab));
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); const position = tabs.indexOf(state.activeDetailTab);
      activateTab(event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[tabs.length - 1] : tabs[(position + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length], true);
    });
  });
  for (const mode of ['graph', 'list']) action('view-' + mode).addEventListener('click', () => transact(() => { state.viewMode = mode; }));
  action('expand-all').addEventListener('click', () => { transact(() => { for (const { module } of filteredModules()) state.collapsed.delete(module.id); }); closeTools(true); });
  action('collapse-all').addEventListener('click', () => { transact(() => { for (const { module } of filteredModules()) state.collapsed.add(module.id); }); closeTools(true); });
  action('open-detail').addEventListener('click', () => transact(() => { state.detailOpen = true; }));
  action('close-detail').addEventListener('click', () => {
    transact(() => { state.detailOpen = false; }); const selected = byId.get(state.selected);
    if (selected && matches(selected.item, selected.module)) (state.collapsed.has(selected.module.id) ? moduleNodes.get(selected.module.id).button : requirementNodes.get(state.selected).button).focus({ preventScroll: true });
    else get('search').focus({ preventScroll: true });
  });
  action('locate-current').addEventListener('click', () => {
    closeTools();
    const selected = byId.get(state.selected); if (!selected) return;
    transact(() => { if (!matches(selected.item, selected.module)) { state.query = ''; state.moduleFilter = ''; state.statusFilter = ''; } state.collapsed.delete(selected.module.id); if (root.getBoundingClientRect().width < 720) state.detailOpen = false; });
    const region = get('map-scroll'), node = requirementNodes.get(state.selected).button, bounds = region.getBoundingClientRect(), target = node.getBoundingClientRect();
    region.scrollTop += target.top - bounds.top - 16; node.focus({ preventScroll: true }); state.scroll.map = capturePosition(region); persist();
  });
  get('map-scroll').addEventListener('scroll', schedulePersist, { passive: true }); get('detail-scroll').addEventListener('scroll', schedulePersist, { passive: true });
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleDraw) : null;
  root.requirementMap = Object.freeze({
    updateSnapshot,
    getState: () => { captureScrolls(); return { selected: state.selected, collapsed: [...state.collapsed], detailOpen: state.detailOpen, query: state.query, moduleFilter: state.moduleFilter, statusFilter: state.statusFilter, viewMode: state.viewMode, activeDetailTab: state.activeDetailTab, expandedCoverage: [...state.expandedCoverage], scroll: JSON.parse(JSON.stringify(state.scroll)), snapshotId: payload?.snapshot.snapshotId, lastUpdate: { ...lastUpdate } }; },
    destroy: () => { disposed = true; closeTools(); if (frame) window.cancelAnimationFrame(frame); if (persistenceFrame) window.cancelAnimationFrame(persistenceFrame); observer?.disconnect(); document.removeEventListener('pointerdown', onOutsideTools); window.removeEventListener('resize', scheduleDraw); window.removeEventListener('openai:set_globals', onGlobals); root.removeEventListener('prototype-flow:requirement-map-snapshot', onSnapshot); }
  });
  root.addEventListener('prototype-flow:requirement-map-snapshot', onSnapshot); window.addEventListener('openai:set_globals', onGlobals); window.addEventListener('resize', scheduleDraw);
  observer?.observe(get('map')); document.fonts?.ready.then(scheduleDraw);
  let initial; try { initial = JSON.parse(get('payload').textContent); } catch (_) { initial = null; }
  if (!updateSnapshot(initial)) { get('summary').textContent = '需求数据格式不正确，请重新读取。'; get('body').hidden = true; }
})();
