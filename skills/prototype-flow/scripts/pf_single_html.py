"""Read-only, self-contained presentation export of a declared Demo runtime."""
from __future__ import annotations

import base64
import html
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

from pf_core import FlowError


def _unsupported(path, reason):
    raise FlowError('无法导出完整的单 HTML 演示版：' + path + '（' + reason + '）。可继续使用工程包导出。', 409)


def _check_javascript(path, source):
    # Ignore comments and literals when detecting server/module-only APIs. The
    # manifest remains the authority for dynamic resource completeness.
    code = re.sub(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|/\*[\s\S]*?\*/|//[^\n]*''',
                  lambda match: ' ' if match.group(1) else '', source)
    patterns = [
        (r'\bimport\s*(?:\(|\.\s*meta\b)|(?m:^\s*(?:import\s*(?:;|$)|import\s+[\w{*]|export\s+(?:default|const|let|var|function|class|\{)))', 'ES module'),
        (r'\b(?:Worker|SharedWorker|XMLHttpRequest|WebSocket|EventSource)\s*\(', 'Worker 或服务器连接'),
        (r'\bserviceWorker\s*\.|\bimportScripts\s*\(', 'Service Worker 或 importScripts'),
    ]
    for pattern, reason in patterns:
        if re.search(pattern, code):
            _unsupported(path, reason)
    # Network-backed fetch cannot be made offline by merely embedding files.
    if re.search(r'''\bfetch\s*\(\s*['"](?:https?:)?//''', source):
        _unsupported(path, '在线 fetch 依赖')


class _Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.title = ''
        self.in_title = False
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.in_title = tag == 'title'
        self.in_script = tag == 'script' and attrs.get('type', '').lower() not in ('application/json', 'application/ld+json')
        if tag == 'base':
            _unsupported(self.path, 'base 改变资源路径')
        if tag in ('iframe', 'object', 'embed'):
            _unsupported(self.path, '嵌套页面或插件资源尚不支持转换')
        if tag == 'script' and attrs.get('type', '').lower() in ('module', 'importmap'):
            _unsupported(self.path, 'ES module 或 importmap')
        if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'content-security-policy':
            _unsupported(self.path, '页面 CSP 尚不支持转换')
        urls = [attrs.get(key, '') for key in ('src', 'poster')]
        if tag == 'link' and any(value in attrs.get('rel', '').lower().split() for value in ('stylesheet', 'preload', 'modulepreload')):
            urls.append(attrs.get('href', ''))
        for value in urls:
            parsed = urlsplit(value)
            if parsed.netloc or parsed.scheme.lower() in ('http', 'https', 'file'):
                _unsupported(self.path, '需要外部资源 ' + value)
        if tag == 'form' and attrs.get('action'):
            _unsupported(self.path, '表单提交需要服务器')
        for key, value in attrs.items():
            if key.startswith('on') and value:
                _check_javascript(self.path, value)

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script':
            self.in_script = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_script:
            _check_javascript(self.path, data)


def single_html(files, records, primary_entries, title):
    """Serialize only the already checked runtime set; never read PRD/archive."""
    pages = {}
    for path, data in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in ('.html', '.htm'):
            page = _Page(path)
            page.feed(data.decode('utf-8-sig'))
            pages[path] = page.title.strip() or PurePosixPath(path).name
        elif suffix in ('.js', '.mjs'):
            _check_javascript(path, data.decode('utf-8-sig'))
        elif suffix == '.css' and re.search(r'''(?:url\(\s*['"]?|@import\s*['"])(?:https?:)?//''', data.decode('utf-8-sig')):
            _unsupported(path, '在线样式资源')
    ordered = list(dict.fromkeys(primary_entries + sorted(pages)))
    if not ordered or any(path not in pages for path in ordered):
        raise FlowError('单 HTML 演示入口缺失', 409)
    entries = [{'path': path, 'title': pages[path]} for path in ordered]
    embedded = {}
    for path, data in sorted(files.items()):
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if data.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        embedded[path] = {'mime': mime, 'base64': base64.b64encode(data).decode('ascii')}
    payload = json.dumps({'schemaVersion': 1, 'title': title, 'entries': entries, 'files': embedded},
                         ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    runtime = Path(__file__).with_name('pf_single_html_runtime.js').read_text(encoding='utf-8')
    # Escape HTML raw-text terminators without changing their JS string value.
    runtime = re.sub(r'</script', r'<\\/script', runtime, flags=re.I)
    document = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>' + html.escape(title) + ' · 演示版</title></head><body>'
                '<script id="pf-demo-bundle" type="application/json">' + payload + '</script>'
                '<script>' + runtime + '</script></body></html>')
    return document.encode('utf-8'), entries
