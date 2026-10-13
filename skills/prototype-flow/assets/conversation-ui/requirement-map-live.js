/* Local server only. This transport is never included in an inline fragment. */
(() => {
  'use strict';
  const root = document.querySelector('.pf-requirement-map');
  const token = document.querySelector('meta[name="pf-token"]')?.content;
  const bridge = root?.requirementMap;
  if (!root || !token || !bridge) return;
  const status = root.querySelector('[data-role="connection-status"]');
  const retry = root.querySelector('[data-action="retry-sync"]');
  const initial = JSON.parse(root.querySelector('[data-role="payload"]').textContent);
  const query = new URLSearchParams();
  for (const key of ['module', 'requirement', 'version']) {
    const value = new URLSearchParams(location.search).get(key);
    if (value) query.set(key, value);
  }
  const show = (message, failed = false) => {
    if (status) { status.textContent = message; status.dataset.connection = failed ? 'disconnected' : 'connected'; }
    if (retry) retry.hidden = !failed;
  };
  if (initial.snapshot.historical) { show('历史版本 · 固定快照'); return; }
  let busy = false, stopped = false, initialized = false, timer, controller;
  let stateToken, externalToken, lastFullCheck = 0, generation = 0;
  const initialModel = initial.requirementMap || initial.snapshot.data?.requirementMap;
  let sequence = initialModel?.sequence || 0;
  let fingerprint = initial.snapshot.sourceFingerprint;
  async function request(path) {
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(path, { headers: { 'X-Prototype-Flow-Token': token },
        cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || '无法读取最新数据');
      return value;
    } finally { clearTimeout(timeout); controller = null; }
  }
  async function check(force = false) {
    if (busy || stopped || (!force && document.visibilityState === 'hidden')) return;
    busy = true;
    const started = generation;
    try {
      const full = force || !initialized || Date.now() - lastFullCheck >= 30000;
      const revision = await request('/api/revision?scope=' + (full ? 'all' : 'active'));
      if (stopped || started !== generation) return;
      if (full) lastFullCheck = Date.now();
      const nextToken = revision.stateRevisionToken ?? revision.revisionToken;
      const externalChanged = revision.externalRevisionToken !== undefined && revision.externalRevisionToken !== externalToken;
      if (force || !initialized || nextToken !== stateToken || externalChanged) {
        const next = await request('/api/requirement-map?' + query.toString());
        if (stopped || started !== generation) return;
        if (!initialized || next.snapshot.sourceFingerprint !== fingerprint) {
          next.requirementMap.sequence = ++sequence;
          if (!bridge.updateSnapshot(next)) throw new Error('数据范围已变化，请重新打开需求图');
          fingerprint = next.snapshot.sourceFingerprint;
        }
      }
      // Commit the observation only after the corresponding snapshot was applied.
      stateToken = nextToken;
      if (revision.externalRevisionToken !== undefined) externalToken = revision.externalRevisionToken;
      initialized = true;
      show('已连接 · 自动更新');
    } catch (error) {
      if (!stopped && started === generation) show('更新暂停 · 保留上次内容：' + error.message, true);
    } finally { busy = false; }
  }
  const resume = () => { if (document.visibilityState !== 'hidden') check(true); };
  const stop = () => { stopped = true; generation++; clearInterval(timer); controller?.abort(); };
  retry?.addEventListener('click', () => check(true));
  window.addEventListener('focus', resume);
  window.addEventListener('online', resume);
  document.addEventListener('visibilitychange', resume);
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', event => {
    if (event.persisted) { stopped = false; timer = setInterval(() => check(), 2000); check(true); }
  });
  show('正在连接最新数据…');
  timer = setInterval(() => check(), 2000);
  check(true);
})();
