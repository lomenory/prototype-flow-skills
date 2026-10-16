/* Self-contained runtime for prototype-flow's single HTML demo export. */
(function () {
  'use strict';

  function createTools(bundle, options) {
    const files = bundle.files || {};
    const origin = 'https://prototype-flow.invalid/';
    const textCache = new Map();
    const urlCache = new Map();
    const blobURLs = [];
    const configuration = options || {};
    const safe = /^(?:data:|blob:|#)/i;

    function reference(value, base) {
      const raw = String(value == null ? '' : value).trim();
      if (!raw || safe.test(raw)) return { raw, passthrough: true };
      if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(raw)) {
        throw new Error('演示资源不能访问外部地址：' + raw);
      }
      const url = new URL(raw, origin + base);
      let path;
      try { path = decodeURIComponent(url.pathname.slice(1)); }
      catch (_) { throw new Error('演示资源路径编码无效：' + raw); }
      if (!Object.prototype.hasOwnProperty.call(files, path)) {
        throw new Error('单 HTML 演示缺少资源：' + path + '（引用位置：' + base + '）');
      }
      return { raw, path, hash: url.hash, search: url.search, file: files[path] };
    }

    function text(path) {
      if (!textCache.has(path)) {
        const file = files[path];
        if (!file) throw new Error('单 HTML 演示缺少资源：' + path);
        const bytes = Uint8Array.from(atob(file.base64), c => c.charCodeAt(0));
        textCache.set(path, new TextDecoder().decode(bytes));
      }
      return textCache.get(path);
    }

    function asset(value, base) {
      const ref = reference(value, base);
      if (ref.passthrough) return ref.raw;
      if (!urlCache.has(ref.path)) {
        const file = ref.file;
        const isCSS = /^text\/css(?:;|$)/i.test(file.mime);
        const isSVG = /^image\/svg\+xml(?:;|$)/i.test(file.mime) || /\.svg$/i.test(ref.path);
        if (!isSVG && typeof configuration.createObjectURL === 'function') {
          const body = isCSS ? css(text(ref.path), ref.path, [ref.path]) : Uint8Array.from(atob(file.base64), c => c.charCodeAt(0));
          const BlobType = configuration.Blob || Blob;
          const url = configuration.createObjectURL(new BlobType([body], { type: isCSS ? 'text/css;charset=utf-8' : file.mime }));
          urlCache.set(ref.path, url);
          blobURLs.push(url);
        } else {
          urlCache.set(ref.path, isCSS
            ? 'data:text/css;charset=utf-8,' + encodeURIComponent(css(text(ref.path), ref.path, [ref.path]))
            : 'data:' + file.mime + ';base64,' + file.base64);
        }
      }
      return urlCache.get(ref.path) + ref.hash;
    }

    function css(source, base, stack) {
      const seen = stack || [];
      let result = String(source).replace(/@import\s+(?:url\(\s*(?:(['"])(.*?)\1|([^\s)'";]+))\s*\)|(['"])(.*?)\4)\s*([^;]*);/gi, (_, quote, quoted, unquoted, directQuote, direct, media) => {
        const url = quoted === undefined ? (unquoted === undefined ? direct : unquoted) : quoted;
        const ref = reference(url, base);
        if (ref.passthrough) throw new Error('不支持内嵌地址的 CSS @import：' + base);
        if (seen.includes(ref.path)) throw new Error('CSS @import 循环：' + ref.path);
        const imported = css(text(ref.path), ref.path, seen.concat(ref.path));
        return media.trim() ? '@media ' + media.trim() + '{' + imported + '}' : imported;
      });
      // Original asset selectors must continue to match after src becomes a data URL.
      result = result.replace(/\[\s*src(\s*[*^$|~]?=\s*)(['"])(.*?)\2(\s*[isIS])?\s*\]/g,
        (all, operator, quote, value, flags) => safe.test(value) ? all : '[data-pf-src' + operator + quote + value + quote + (flags || '') + ']');
      result = result.replace(/url\(\s*(?:(['"])(.*?)\1|([^'"\s][^)]*?))\s*\)/gi,
        (_, quote, quoted, unquoted) => 'url("' + asset(quoted === undefined ? unquoted.trim() : quoted, base).replace(/"/g, '%22') + '")');
      return result;
    }

    function srcset(value, base) {
      if (/^\s*(?:data:|blob:)/i.test(value)) return value;
      return String(value).split(',').map(part => {
        const match = part.trim().match(/^(\S+)(\s+.*)?$/);
        return match ? asset(match[1], base) + (match[2] || '') : '';
      }).join(', ');
    }
    function shareURL(value, base, outerURL) {
      const string = String(value);
      if (!/^about:srcdoc(?:#|$)/i.test(string)) return value;
      const outer = new URL(outerURL);
      const hashIndex = string.indexOf('#');
      const route = hashIndex < 0 ? '' : string.slice(hashIndex);
      outer.hash = '#pf-demo=' + encodeURIComponent(base) + '&route=' + encodeURIComponent(route);
      return outer.href;
    }
    function dispose() {
      if (typeof configuration.revokeObjectURL === 'function') {
        for (const url of blobURLs.splice(0)) configuration.revokeObjectURL(url);
      }
    }
    return { files, reference, text, asset, css, srcset, shareURL, dispose };
  }

  // Pure helpers are available to the Node regression tests; the browser has no dependency.
  if (typeof module !== 'undefined' && module.exports) module.exports = { createTools };
  if (typeof window === 'undefined' || !window.document) return;

  const bundleNode = document.getElementById('pf-demo-bundle');
  const runtimeNode = document.currentScript;
  let bundle, tools, activePath, switcher, errorPanel;
  const frames = new Map();
  const originalSetAttribute = Element.prototype.setAttribute;
  const originalInnerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');

  function fail(error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('[prototype-flow 单 HTML]', error);
    if (!errorPanel) {
      errorPanel = document.createElement('div');
      errorPanel.setAttribute('role', 'alert');
      errorPanel.style.cssText = 'position:fixed;z-index:2147483647;bottom:12px;left:12px;right:12px;padding:14px 18px;border:1px solid #b42318;border-radius:8px;background:#fff1f0;color:#851a10;font:14px/1.5 system-ui;white-space:pre-wrap;max-height:35vh;overflow:auto';
      document.body.appendChild(errorPanel);
    }
    errorPanel.textContent = '演示资源加载失败\n' + message;
    return error;
  }

  function rewriteElement(node, base) {
    if (!node || node.nodeType !== 1) return;
    const tag = node.localName.toLowerCase();
    if (tag === 'base') { node.remove(); return; }
    if (tag === 'meta' && /^(?:refresh|content-security-policy)$/i.test(node.getAttribute('http-equiv') || '')) {
      node.remove(); return;
    }
    if (tag === 'link' && /\bstylesheet\b/i.test(node.getAttribute('rel') || '')) node.removeAttribute('integrity');
    for (const attr of Array.from(node.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value;
      if (name === 'style') originalSetAttribute.call(node, name, tools.css(value, base));
      else if (name === 'srcset') originalSetAttribute.call(node, name, tools.srcset(value, base));
      else if (name === 'src' || name === 'poster' || (name === 'data' && tag === 'object') ||
          ((name === 'href' || name === 'xlink:href') && !['a', 'area', 'base'].includes(tag))) {
        if (name === 'src' && !/^(?:data:|blob:)/i.test(value)) originalSetAttribute.call(node, 'data-pf-src', value);
        originalSetAttribute.call(node, name, tools.asset(value, base));
      } else if (name === 'href' && ['a', 'area'].includes(tag) && value && !/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(value)) {
        const ref = tools.reference(value, base);
        if (ref.path && /\.html?$/i.test(ref.path)) {
          originalSetAttribute.call(node, 'data-pf-page', ref.path);
          originalSetAttribute.call(node, 'data-pf-hash', ref.hash);
          originalSetAttribute.call(node, 'href', '#' + ref.hash.slice(1));
        } else originalSetAttribute.call(node, 'href', tools.asset(value, base));
      }
    }
    if (tag === 'style') node.textContent = tools.css(node.textContent, base);
  }

  function rewriteTree(root, base) {
    if (!root || ![1, 9, 11].includes(root.nodeType)) return root;
    const nodes = root.nodeType === 1 ? [root, ...root.querySelectorAll('*')] : Array.from(root.querySelectorAll('*'));
    // Keep stylesheet links so media/disabled/load events and parser blocking remain native.
    // asset() rewrites the CSS before generating its self-contained data URL.
    for (const node of nodes) rewriteElement(node, base);
    return root;
  }

  function fragment(source, base) {
    const template = document.createElement('template');
    originalInnerHTML.set.call(template, String(source));
    rewriteTree(template.content, base);
    return originalInnerHTML.get.call(template);
  }

  function pageHTML(path, hash) {
    const parsed = new DOMParser().parseFromString(tools.text(path), 'text/html');
    rewriteTree(parsed, path);
    const bootstrap = parsed.createElement('script');
    bootstrap.textContent = 'parent.__PF_SINGLE_HTML__.install(window,' + JSON.stringify(path) + ',' + JSON.stringify(hash || '') + ');';
    parsed.head.insertBefore(bootstrap, parsed.head.firstChild);
    return '<!doctype html>\n' + parsed.documentElement.outerHTML;
  }

  function encodeState(path, hash) { return '#pf-demo=' + encodeURIComponent(path) + '&route=' + encodeURIComponent(hash || ''); }
  function saveState(path, hash) {
    try { history.replaceState(null, '', encodeState(path, hash)); } catch (_) { /* file URL storage varies by browser */ }
  }

  function showPage(path, hash) {
    if (!tools.files[path] || !/\.html?$/i.test(path)) throw fail(new Error('单 HTML 演示缺少页面：' + path));
    let frame = frames.get(path);
    if (!frame) {
      frame = document.createElement('iframe');
      frame.title = (bundle.entries.find(entry => entry.path === path) || {}).title || bundle.title || '演示';
      frame.setAttribute('data-pf-entry', path);
      frame.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border:0;display:none;background:white';
      frame.srcdoc = pageHTML(path, hash);
      frames.set(path, frame);
      document.body.appendChild(frame);
    } else if (hash !== undefined && frame.contentWindow) {
      try {
        if (frame.contentWindow.location.hash !== hash) frame.contentWindow.location.hash = hash;
      } catch (error) { throw fail(error); }
    }
    for (const [entryPath, child] of frames) child.style.display = entryPath === path ? 'block' : 'none';
    activePath = path;
    if (switcher) switcher.value = path;
    saveState(path, hash === undefined && frame.contentWindow ? frame.contentWindow.location.hash : hash);
  }

  function install(child, base, initialHash) {
    const doc = child.document;
    const nativeSet = child.Element.prototype.setAttribute;
    const nativeInner = Object.getOwnPropertyDescriptor(child.Element.prototype, 'innerHTML');
    const nativeOuter = Object.getOwnPropertyDescriptor(child.Element.prototype, 'outerHTML');
    const guard = fn => function () { try { return fn.apply(this, arguments); } catch (error) { fail(error); throw error; } };

    function setAttribute(name, value) {
      const lower = String(name).toLowerCase();
      const tag = this.localName.toLowerCase();
      let mapped = value;
      if (lower === 'style') mapped = tools.css(value, base);
      else if (lower === 'srcset') mapped = tools.srcset(value, base);
      else if (lower === 'src' || lower === 'poster' || (lower === 'data' && tag === 'object') ||
          ((lower === 'href' || lower === 'xlink:href') && !['a', 'area', 'base'].includes(tag))) {
        if (tag === 'link' && lower === 'href' && /\bstylesheet\b/i.test(this.getAttribute('rel') || '')) this.removeAttribute('integrity');
        if (lower === 'src' && !/^(?:data:|blob:)/i.test(value)) nativeSet.call(this, 'data-pf-src', value);
        else if (lower === 'src') this.removeAttribute('data-pf-src');
        mapped = tools.asset(value, base);
      } else if (lower === 'href' && ['a', 'area'].includes(tag)) {
        this.removeAttribute('data-pf-page');
        this.removeAttribute('data-pf-hash');
        if (value && !/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(value)) {
          const ref = tools.reference(value, base);
          if (ref.path && /\.html?$/i.test(ref.path)) {
            nativeSet.call(this, 'data-pf-page', ref.path);
            nativeSet.call(this, 'data-pf-hash', ref.hash);
            mapped = '#' + ref.hash.slice(1);
          } else mapped = tools.asset(value, base);
        }
      }
      return nativeSet.call(this, name, mapped);
    }
    child.Element.prototype.setAttribute = guard(setAttribute);
    const nativeSetNS = child.Element.prototype.setAttributeNS;
    child.Element.prototype.setAttributeNS = guard(function (ns, name, value) {
      if (!ns) return this.setAttribute(name, value);
      if (ns === 'http://www.w3.org/1999/xlink' && /(?:^|:)href$/i.test(name)) return nativeSetNS.call(this, ns, name, tools.asset(value, base));
      return nativeSetNS.call(this, ns, name, value);
    });
    for (const [property, descriptor] of [['innerHTML', nativeInner], ['outerHTML', nativeOuter]]) {
      if (descriptor && descriptor.set) Object.defineProperty(child.Element.prototype, property, {
        configurable: descriptor.configurable, enumerable: descriptor.enumerable, get: descriptor.get,
        set: guard(function (value) { descriptor.set.call(this, fragment(value, base)); })
      });
    }
    const nativeAdjacent = child.Element.prototype.insertAdjacentHTML;
    child.Element.prototype.insertAdjacentHTML = guard(function (position, value) { return nativeAdjacent.call(this, position, fragment(value, base)); });

    // Property setters bypass setAttribute in browser internals, so patch their descriptors too.
    const properties = {
      HTMLImageElement: ['src', 'srcset'], HTMLScriptElement: ['src'], HTMLLinkElement: ['href'],
      HTMLSourceElement: ['src', 'srcset'], HTMLMediaElement: ['src'], HTMLVideoElement: ['poster'],
      HTMLInputElement: ['src'], HTMLIFrameElement: ['src'], HTMLObjectElement: ['data'],
      HTMLAnchorElement: ['href'], HTMLAreaElement: ['href']
    };
    for (const [constructorName, names] of Object.entries(properties)) {
      const constructor = child[constructorName];
      if (!constructor) continue;
      for (const name of names) {
        const descriptor = Object.getOwnPropertyDescriptor(constructor.prototype, name);
        if (!descriptor || !descriptor.set) continue;
        Object.defineProperty(constructor.prototype, name, {
          configurable: descriptor.configurable, enumerable: descriptor.enumerable, get: descriptor.get,
          set: guard(function (value) { this.setAttribute(name, value); })
        });
      }
    }
    for (const name of ['appendChild', 'insertBefore', 'replaceChild']) {
      const native = child.Node.prototype[name];
      child.Node.prototype[name] = guard(function (node) { rewriteTree(node, base); return native.apply(this, arguments); });
    }
    // Element.append/prepend and ChildNode.before/after bypass appendChild overrides.
    for (const prototype of [child.Element.prototype, child.Document.prototype, child.DocumentFragment.prototype]) {
      for (const name of ['append', 'prepend', 'replaceChildren', 'before', 'after', 'replaceWith']) {
        const native = prototype[name];
        if (!Object.prototype.hasOwnProperty.call(prototype, name) || typeof native !== 'function') continue;
        prototype[name] = guard(function () {
          for (const node of arguments) if (typeof node !== 'string') rewriteTree(node, base);
          return native.apply(this, arguments);
        });
      }
    }
    const declaration = child.CSSStyleDeclaration && child.CSSStyleDeclaration.prototype;
    if (declaration) {
      const nativeProperty = declaration.setProperty;
      declaration.setProperty = guard(function (name, value, priority) { return nativeProperty.call(this, name, tools.css(value, base), priority); });
      for (const name of ['cssText', 'background', 'backgroundImage', 'mask', 'maskImage', 'webkitMask', 'webkitMaskImage', 'content', 'cursor', 'listStyle', 'listStyleImage', 'borderImage', 'borderImageSource']) {
        const descriptor = Object.getOwnPropertyDescriptor(declaration, name);
        if (descriptor && descriptor.set && descriptor.configurable) Object.defineProperty(declaration, name, {
          configurable: true, enumerable: descriptor.enumerable, get: descriptor.get,
          set: guard(function (value) { descriptor.set.call(this, tools.css(value, base)); })
        });
      }
    }
    if (child.CSSStyleSheet) {
      const nativeRule = child.CSSStyleSheet.prototype.insertRule;
      child.CSSStyleSheet.prototype.insertRule = guard(function (rule, index) { return nativeRule.call(this, tools.css(rule, base), index); });
    }
    if (child.Range && child.Range.prototype.createContextualFragment) {
      const nativeFragment = child.Range.prototype.createContextualFragment;
      child.Range.prototype.createContextualFragment = guard(function (source) { return nativeFragment.call(this, fragment(source, base)); });
    }
    if (child.fetch) {
      const nativeFetch = child.fetch.bind(child);
      child.fetch = guard(function (input, options) {
        const value = typeof input === 'string' || input instanceof child.URL ? String(input) : input.url;
        const method = (options && options.method || input && input.method || 'GET').toUpperCase();
        if (/^(?:data:|blob:)/i.test(value)) return nativeFetch(input, options);
        if (!['GET', 'HEAD'].includes(method)) return Promise.reject(fail(new Error('单 HTML 演示不支持资源写入请求：' + value)));
        const ref = tools.reference(value, base);
        if (ref.passthrough) return Promise.reject(fail(new Error('无法读取演示资源：' + value)));
        const bytes = Uint8Array.from(atob(ref.file.base64), c => c.charCodeAt(0));
        return Promise.resolve(new child.Response(method === 'HEAD' ? null : bytes, { status: 200, headers: { 'Content-Type': ref.file.mime } }));
      });
    }
    const nativeOpen = child.open.bind(child);
    child.open = guard(function (url, target, features) {
      if (url && !/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(url)) {
        const ref = tools.reference(url, base);
        if (/\.html?$/i.test(ref.path)) { showPage(ref.path, ref.hash); return child; }
        return nativeOpen(tools.asset(url, base), target, features);
      }
      return nativeOpen(url, target, features);
    });
    const shareValue = value => tools.shareURL(value, base, window.location.href);
    // srcdoc's synthetic URL must never escape into copied demo deep links.
    const clipboard = child.navigator.clipboard;
    if (clipboard && typeof clipboard.writeText === 'function') {
      const nativeWrite = clipboard.writeText.bind(clipboard);
      try { clipboard.writeText = value => nativeWrite(shareValue(value)); }
      catch (_) { /* The input fallback below also works when clipboard access is unavailable. */ }
    }
    for (const constructor of [child.HTMLInputElement, child.HTMLTextAreaElement]) {
      const descriptor = Object.getOwnPropertyDescriptor(constructor.prototype, 'value');
      if (descriptor && descriptor.set && descriptor.configurable) Object.defineProperty(constructor.prototype, 'value', {
        configurable: true, enumerable: descriptor.enumerable, get: descriptor.get,
        set(value) { descriptor.set.call(this, typeof value === 'string' ? shareValue(value) : value); }
      });
    }
    doc.addEventListener('copy', event => {
      if (!event.clipboardData) return;
      const focused = doc.activeElement;
      const selected = focused && /^(?:input|textarea)$/.test(focused.localName) && typeof focused.selectionStart === 'number'
        ? focused.value.slice(focused.selectionStart, focused.selectionEnd) : String(child.getSelection() || '');
      const mapped = shareValue(selected);
      if (mapped !== selected) { event.clipboardData.setData('text/plain', mapped); event.preventDefault(); }
    });
    doc.addEventListener('click', guard(function (event) {
      const anchor = event.target.closest && event.target.closest('a[data-pf-page],area[data-pf-page]');
      if (anchor && !anchor.hasAttribute('download')) {
        event.preventDefault();
        showPage(anchor.getAttribute('data-pf-page'), anchor.getAttribute('data-pf-hash') || '');
      }
    }), true);
    for (const name of ['pushState', 'replaceState']) {
      const native = child.history[name].bind(child.history);
      child.history[name] = guard(function (state, title, url) {
        let route = child.location.hash;
        if (url !== undefined && url !== null) {
          const value = String(url);
          route = value.includes('#') ? value.slice(value.indexOf('#')) : '';
        }
        // about:srcdoc has no pathname that can resolve the original relative history URLs.
        const result = native(state, title, 'about:srcdoc' + route);
        if (activePath === base) saveState(base, route);
        return result;
      });
    }
    child.addEventListener('hashchange', () => { if (activePath === base) saveState(base, child.location.hash); });
    child.addEventListener('error', event => {
      if (event.target && event.target !== child && event.target.localName) fail(new Error('演示资源加载失败：' + (event.target.getAttribute('data-pf-src') || event.target.localName)));
      else if (event.message) fail(event.error || new Error(event.message));
    }, true);
    child.addEventListener('unhandledrejection', event => { fail(event.reason || new Error('演示初始化失败')); });
    if (initialHash) child.history.replaceState(null, '', initialHash);
  }

  try {
    bundle = JSON.parse(bundleNode.textContent);
    // The payload stays in the closure; keep its large serialized source out of the live DOM.
    bundleNode.remove();
    if (runtimeNode) runtimeNode.remove();
    if (bundle.schemaVersion !== 1 || !Array.isArray(bundle.entries) || !bundle.entries.length) throw new Error('单 HTML 演示包格式无效');
    tools = createTools(bundle, {
      createObjectURL: typeof URL.createObjectURL === 'function' ? blob => URL.createObjectURL(blob) : null,
      revokeObjectURL: typeof URL.revokeObjectURL === 'function' ? url => URL.revokeObjectURL(url) : null,
      Blob
    });
    window.addEventListener('beforeunload', () => tools.dispose());
    document.title = bundle.title || document.title || '演示';
    document.documentElement.style.cssText = 'height:100%;overflow:hidden';
    document.body.style.cssText = 'margin:0;height:100%;overflow:hidden;background:#fff';
    window.__PF_SINGLE_HTML__ = {
      install(child, base, hash) { try { return install(child, base, hash); } catch (error) { fail(error); throw error; } }
    };
    if (bundle.entries.length > 1) {
      const menu = document.createElement('details');
      menu.style.cssText = 'position:fixed;right:12px;top:10px;z-index:2147483646;font:12px/1.5 system-ui;color:#333;background:#fffffff0;border:1px solid #d8d8d8;border-radius:7px;padding:4px 8px;box-shadow:0 2px 8px #0001';
      menu.innerHTML = '<summary style="cursor:pointer;user-select:none">演示页面</summary><label style="display:block;padding:7px 0 3px">切换页面 <select aria-label="切换演示页面" style="font:inherit;max-width:220px"></select></label>';
      switcher = menu.querySelector('select');
      for (const entry of bundle.entries) {
        const option = document.createElement('option');
        option.value = entry.path;
        option.textContent = entry.title || entry.path.split('/').pop();
        switcher.appendChild(option);
      }
      switcher.addEventListener('change', () => { try { showPage(switcher.value); menu.open = false; } catch (_) { /* fail already displayed */ } });
      document.body.appendChild(menu);
    }
    const state = new URLSearchParams(location.hash.slice(1));
    const requested = state.get('pf-demo');
    const initial = bundle.entries.some(entry => entry.path === requested) ? requested : bundle.entries[0].path;
    showPage(initial, requested === initial ? state.get('route') || '' : '');
  } catch (error) { fail(error); }
})();
