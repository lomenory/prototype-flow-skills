"""Versioned Demo resources: runtime delivery, retained evidence, and workspace debris.

The manifest is an explicit delivery contract, not a proof that arbitrary JavaScript
has no other dependencies. Static references are checked; unresolved dynamic loads
need a complete author declaration before freezing or exporting a new manifest.
"""
from __future__ import annotations

import copy
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit

from pf_core import FlowError

_FIELDS = ('runtimeFiles', 'archiveFiles', 'excludedFiles')
_DIRECTORY_FIELDS = ('runtimeDirectories', 'archiveDirectories', 'excludedDirectories')
_TEMP_DIRS = {'.git', '__MACOSX', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
              '.cache', '.parcel-cache', '.playwright', '.playwright-cli', 'node_modules'}
_ARCHIVE_DIRS = {'evidence', '_evidence', 'screenshots', 'reports'}
_ARCHIVE_NAMES = {'design.md', 'source-brief.md', 'prototype-contract.json',
                  'design-guidance.json', 'validation-report.json', 'verification-report.json'}
_HASH = re.compile(r'^[a-f0-9]{64}$')


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise FlowError('资源清单路径无效', 403, {'path': value})
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or value != path.as_posix() or value == '.':
        raise FlowError('资源清单路径必须是规范的 Demo 相对路径', 403, {'path': value})
    return value


def _paths(value, name):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise FlowError('资源清单字段必须是路径数组：' + name)
    paths = [_relative(item) for item in value]
    if len(paths) != len(set(paths)):
        raise FlowError('资源清单包含重复路径：' + name)
    return set(paths)


def _directory(store, directory):
    directory = Path(directory)
    if not directory.is_absolute():
        directory = store._safe(directory)
    else:
        directory = store._safe(directory.relative_to(store.root))
    return directory


def _temporary_reason(relative):
    path = PurePosixPath(relative)
    if '__MACOSX' in path.parts or path.name in {'.DS_Store', 'Thumbs.db', 'desktop.ini'} or path.name.startswith('._'):
        return '自动排除：系统附加元数据'
    for part in path.parts:
        if part in _TEMP_DIRS:
            return '自动排除：工作缓存或工具目录 ' + part
    if path.suffix.lower() in {'.pyc', '.pyo'}:
        return '自动排除：编译缓存'
    if path.suffix.lower() == '.log':
        return '自动排除：运行日志'
    if path.suffix.lower() in {'.tmp', '.temp', '.bak', '.swp', '.swo'} or path.name.endswith('~'):
        return '自动排除：临时或备份文件'
    return None


def _temporary(relative):
    return _temporary_reason(relative) is not None


def _archive(relative):
    path = PurePosixPath(relative)
    return (path.name.lower() in _ARCHIVE_NAMES or path.suffix.lower() in {'.md', '.map'}
            or any(part in _ARCHIVE_DIRS for part in path.parts[:-1]))


def _css_urls(text):
    # Quoted paths may contain spaces; do not truncate them at the first space.
    values = []
    for match in re.finditer(r'url\(\s*(?:"([^"]*)"|\'([^\']*)\'|([^)]*?))\s*\)', text, re.I):
        values.append(next(value for value in match.groups() if value is not None).strip())
    values.extend(re.findall(r'@import\s+[\'"]([^\'"]+)', text, re.I))
    return values


def _srcset_urls(text):
    # Data URLs contain commas, so consume the whole non-whitespace token first.
    values = []
    for match in re.finditer(r'(?:^|,)\s*(data:[^\s]+|[^\s,]+)(?:\s+[^,]*)?', text):
        values.append(match.group(1).rstrip(','))
    return values


class _HTMLResources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.scripts = []
        self.styles = []
        self.dynamic = []
        self._script = False
        self._style = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base':
            self.dynamic.append('HTML base 改变相对路径')
        if 'srcdoc' in attrs:
            self.dynamic.append('iframe srcdoc 内嵌文档')
        for name in ('src', 'poster'):
            if attrs.get(name):
                self.urls.append(attrs[name])
        for name in ('href', 'xlink:href'):
            if attrs.get(name) and tag in {'link', 'a', 'area', 'use', 'image'}:
                self.urls.append(attrs[name])
        if tag == 'object' and attrs.get('data'):
            self.urls.append(attrs['data'])
        if tag == 'form' and attrs.get('action'):
            self.urls.append(attrs['action'])
        if attrs.get('srcset'):
            self.urls.extend(_srcset_urls(attrs['srcset']))
        self.urls.extend(_css_urls(attrs.get('style', '')))
        self.scripts.extend(value for key, value in attrs.items() if key.startswith('on') and value)
        self._script = tag == 'script'
        self._style = tag == 'style'
        if tag == 'script' and attrs.get('type') == 'importmap':
            self.dynamic.append('importmap 需要显式运行资源声明')

    def handle_endtag(self, tag):
        if tag == 'script':
            self._script = False
        if tag == 'style':
            self._style = False

    def handle_data(self, data):
        if self._script:
            self.scripts.append(data)
        if self._style:
            self.styles.append(data)


def _js_references(text):
    """Return (URL, resolution-base) plus constructs needing an author declaration."""
    references, unresolved = [], []
    # Ignore comments without damaging URLs or comment-like characters in strings.
    text = re.sub(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)|/\*[\s\S]*?\*/|//[^\n]*',
                  lambda match: match.group(1) or '', text)
    literal = r'([\'"])([^\'"\n]+)\1'
    for match in re.finditer(r'''\b(?:import|export)\s+(?:[^;"'()]*?\s+from\s*)?''' + literal, text):
        references.append((match.group(2), 'module'))
    calls = [
        (r'\bimport\s*\(', 'module', '动态 import'),
        (r'\bfetch\s*\(', 'document', '动态 fetch'),
        (r'\b(?:new\s+)?(?:Worker|SharedWorker)\s*\(', 'worker', '动态 Worker'),
        (r'\bimportScripts\s*\(', 'module', '动态 importScripts'),
        (r'\b(?:navigator\.)?serviceWorker\.register\s*\(', 'worker', '动态 ServiceWorker'),
        (r'\bnew\s+URL\s*\(', 'module', '动态 URL'),
    ]
    for pattern, base, reason in calls:
        for match in re.finditer(pattern, text):
            tail = text[match.end():]
            argument = re.match(r'\s*' + literal, tail)
            if argument and not re.match(r'\s*[,)]', tail[argument.end():]):
                argument = None  # A quoted prefix plus an expression is still dynamic.
            if argument:
                resolved_base = base
                if reason == '动态 URL':
                    if not re.match(r'\s*,\s*import\.meta\.url\s*\)', tail[argument.end():]):
                        unresolved.append('URL 基准不是 import.meta.url')
                        continue
                    if re.search(r'(?:Worker|SharedWorker)\s*\(\s*new\s+URL\s*\($', text[:match.end()]):
                        resolved_base = 'worker-module'
                references.append((argument.group(2), resolved_base))
                if reason == '动态 importScripts' and re.match(r'\s*,', tail[argument.end():]):
                    unresolved.append('多参数 importScripts')
            elif reason == '动态 Worker' and re.match(r'\s*new\s+URL\s*\(', tail):
                # The inner URL is handled above with its module-relative base.
                continue
            else:
                unresolved.append(reason)
    if re.search(r'\b(?:XMLHttpRequest|WebSocket|EventSource|eval|Function)\b|\.(?:src|href)\s*=', text):
        unresolved.append('动态资源地址或脚本执行')
    for match in re.finditer(r'\bsetAttribute\s*\(', text):
        name = re.match(r'\s*' + literal, text[match.end():])
        if not name or name.group(2).lower() in {'src', 'href', 'srcset', 'poster', 'data'}:
            unresolved.append('动态资源属性')
    return references, unresolved


def _declaration(supplied, previous):
    if previous and 'resourceManifest' in previous:
        previous = previous['resourceManifest']
    prior = copy.deepcopy((previous or {}).get('declaration', {}))
    if supplied is None:
        return prior
    if not isinstance(supplied, dict):
        raise FlowError('resourceManifest 必须是对象')
    if type(supplied.get('schemaVersion', 1)) is not int or supplied.get('schemaVersion', 1) != 1:
        raise FlowError('不支持的资源清单版本')
    # A saved manifest can be passed back without converting inferred files into
    # an assertion of complete dynamic dependencies.
    if 'declaration' in supplied:
        supplied = supplied['declaration']
        if not isinstance(supplied, dict):
            raise FlowError('资源声明必须是对象')
    allowed = set(_FIELDS + _DIRECTORY_FIELDS + ('entryPoints', 'complete', 'schemaVersion'))
    unknown = set(supplied) - allowed
    if unknown:
        raise FlowError('未知资源声明字段', details=sorted(unknown))
    for key, value in supplied.items():
        if key != 'schemaVersion':
            prior[key] = copy.deepcopy(value)
    if 'complete' in prior and not isinstance(prior['complete'], bool):
        raise FlowError('资源声明 complete 必须是布尔值')
    for key in _FIELDS + _DIRECTORY_FIELDS + ('entryPoints',):
        if key in prior:
            _paths(prior[key], key)
    return prior


def build_manifest(store, directory, supplied=None, previous=None, entries=(), required_archive=(), protected_files=()):
    """Classify a current tree without deleting or rewriting any source file."""
    directory = _directory(store, directory)
    all_hashes = store._inventory(directory)
    files = set(all_hashes)
    declaration = _declaration(supplied, previous)
    explicit = {key: _paths(declaration.get(key, []), key) for key in _FIELDS}
    for key, directory_key in zip(_FIELDS, _DIRECTORY_FIELDS):
        for relative in _paths(declaration.get(directory_key, []), directory_key):
            path = store._safe(relative, base=directory, must_exist=key != 'excludedFiles')
            if key == 'excludedFiles' and not path.exists():
                continue
            if not path.is_dir():
                raise FlowError('资源目录声明不是目录：' + relative)
            explicit[key].update(name for name in files if name.startswith(relative + '/'))
    missing = (explicit['runtimeFiles'] | explicit['archiveFiles']) - files
    if missing:
        raise FlowError('资源声明文件不存在', details=sorted(missing))
    for left, right in (('runtimeFiles', 'archiveFiles'), ('runtimeFiles', 'excludedFiles'), ('archiveFiles', 'excludedFiles')):
        if explicit[left] & explicit[right]:
            raise FlowError('资源分类冲突', details=sorted(explicit[left] & explicit[right]))
    required = {_relative(path) for path in required_archive}
    protected = {_relative(path) for path in protected_files}
    if (required | protected) - files:
        raise FlowError('必须保留的归档资源不存在', details=sorted((required | protected) - files))
    excluded = {name for name in files if _temporary(name)}
    # Explicitly retained files may be intentional assets despite their names.
    excluded -= explicit['runtimeFiles'] | explicit['archiveFiles'] | protected
    excluded |= explicit['excludedFiles'] & files
    if excluded & (required | protected):
        raise FlowError('证据或固定框架资源不能排除', details=sorted(excluded & (required | protected)))
    archive = explicit['archiveFiles'] | required | protected
    archive.update(name for name in files - excluded if _archive(name))
    # Reusing a fully classified baseline preserves the role of its historical
    # evidence even when the new task does not rebind every old screenshot.
    # Pending classifications must never become resolved merely by copying.
    previous_manifest = (previous or {}).get('resourceManifest', previous or {})
    if previous_manifest and previous_manifest.get('unresolved') == []:
        archive.update(set(previous_manifest.get('archiveFiles', [])) & (files - excluded))
    entry_points = {_relative(path) for path in entries}
    entry_points |= _paths(declaration.get('entryPoints', []), 'entryPoints')
    # Every authored HTML page is a potential direct preview entry. Framework
    # examples and explicitly archived pages are retained without being entries.
    entry_points.update(name for name in files - archive - excluded
                        if PurePosixPath(name).suffix.lower() in {'.html', '.htm'}
                        and not name.startswith('_framework/'))
    if entry_points - files:
        raise FlowError('资源清单入口不存在', details=sorted(entry_points - files))
    runtime = set()
    pending = [(name, name) for name in sorted(entry_points)]
    deferred = set(explicit['runtimeFiles'])
    visited = set()
    unresolved = set()
    complete = declaration.get('complete') is True and bool(explicit['runtimeFiles'])

    def add_url(url, relative, document, base_kind='module'):
        parsed = urlsplit(url.strip())
        if not parsed.path or parsed.scheme in {'data', 'blob', 'javascript', 'mailto', 'tel'}:
            return
        if parsed.scheme or parsed.netloc:
            return  # External URLs remain external; they do not select local files.
        if parsed.path.startswith('/'):
            unresolved.add(relative + '：根路径资源 ' + url)
            return
        if document is None and base_kind in {'document', 'worker'}:
            if not complete:
                unresolved.add(relative + '：动态资源缺少页面或 Worker 上下文')
            return
        reference_base = document if base_kind in {'document', 'worker'} else relative
        decoded = unquote(parsed.path)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(reference_base), decoded))
        _relative(target)
        store._safe(target, base=directory)
        if target not in files:
            raise FlowError('预览依赖文件不存在：' + target, details={'source': relative, 'reference': url})
        pending.append((target, target if base_kind in {'worker', 'worker-module'}
                        or PurePosixPath(target).suffix.lower() in {'.html', '.htm'} else document))

    while pending or deferred:
        if not pending:
            pending = [(name, name if PurePosixPath(name).suffix.lower() in {'.html', '.htm'} else None)
                       for name in sorted(deferred - runtime)]
            deferred.clear()
            if not pending:
                break
        relative, document = pending.pop()
        if relative in excluded or relative in explicit['archiveFiles']:
            raise FlowError('运行依赖与资源分类冲突：' + relative)
        runtime.add(relative)
        context = (relative, document)
        if context in visited:
            continue
        visited.add(context)
        suffix = PurePosixPath(relative).suffix.lower()
        if suffix not in {'.html', '.htm', '.css', '.js', '.mjs', '.cjs', '.svg'}:
            continue
        try:
            text = store._file_bytes(directory / relative).decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise FlowError('预览源码不是 UTF-8：' + relative) from exc
        if suffix in {'.html', '.htm', '.svg'}:
            parser = _HTMLResources()
            parser.feed(text)
            for url in parser.urls + [url for css in parser.styles for url in _css_urls(css)]:
                add_url(url, relative, document)
            for reason in parser.dynamic:
                if not complete:
                    unresolved.add(relative + '：' + reason)
            script_texts = parser.scripts
        elif suffix == '.css':
            for url in _css_urls(text):
                add_url(url, relative, document)
            script_texts = []
        else:
            script_texts = [text]
        for script in script_texts:
            references, dynamic = _js_references(script)
            for url, base_kind in references:
                # Bare module specifiers need an import map/bundler declaration.
                if base_kind == 'module' and not url.startswith(('.', '/')) and not urlsplit(url).scheme:
                    if url not in files and not (directory / posixpath.dirname(relative) / url).is_file():
                        if not complete:
                            unresolved.add(relative + '：无法解析模块 ' + url)
                        continue
                add_url(url, relative, document, base_kind)
            if not complete:
                unresolved.update(relative + '：' + reason for reason in dynamic)
    archive -= runtime
    for relative in files - runtime - archive - excluded:
        archive.add(relative)
        unresolved.add('未分类资源：' + relative)
    excluded_reasons = {}
    declared_exclusions = set(declaration.get('excludedFiles', []))
    for relative in sorted(excluded):
        if relative in declared_exclusions:
            excluded_reasons[relative] = '显式排除：文件声明'
        elif relative in explicit['excludedFiles']:
            prefix = next(prefix for prefix in declaration.get('excludedDirectories', [])
                          if relative.startswith(prefix + '/'))
            excluded_reasons[relative] = '显式排除：目录 ' + prefix
        else:
            excluded_reasons[relative] = _temporary_reason(relative)
    manifest = {'schemaVersion': 1, 'entryPoints': sorted(entry_points),
                'runtimeFiles': sorted(runtime), 'archiveFiles': sorted(archive),
                'excludedFiles': sorted(excluded), 'excludedReasons': excluded_reasons,
                'unresolved': sorted(unresolved),
                'declaration': declaration}
    validate_manifest({'resourceManifest': manifest,
                       'fileHashes': {path: all_hashes[path] for path in runtime | archive}})
    return manifest


def validate_manifest(record, require_complete=False):
    manifest = record.get('resourceManifest')
    if manifest is None:
        return None
    if not isinstance(manifest, dict) or type(manifest.get('schemaVersion')) is not int or manifest['schemaVersion'] != 1:
        raise FlowError('不支持的资源清单版本')
    groups = {key: _paths(manifest.get(key), key) for key in _FIELDS}
    entries = _paths(manifest.get('entryPoints'), 'entryPoints')
    if not entries.issubset(groups['runtimeFiles']):
        raise FlowError('资源清单入口必须属于运行资源')
    if require_complete and (not entries or (record.get('entryHtml') and record['entryHtml'] not in entries)):
        raise FlowError('资源清单缺少登记的预览入口', 409)
    for left, right in (('runtimeFiles', 'archiveFiles'), ('runtimeFiles', 'excludedFiles'), ('archiveFiles', 'excludedFiles')):
        if groups[left] & groups[right]:
            raise FlowError('资源清单分类冲突', details=sorted(groups[left] & groups[right]))
    hashes = record.get('fileHashes')
    if not isinstance(hashes, dict) or any(not isinstance(value, str) or not _HASH.fullmatch(value) for value in hashes.values()):
        raise FlowError('资源清单缺少有效文件哈希')
    for relative in hashes:
        _relative(relative)
    if groups['runtimeFiles'] | groups['archiveFiles'] != set(hashes):
        raise FlowError('资源清单未完整覆盖登记文件', details={
            'unclassified': sorted(set(hashes) - groups['runtimeFiles'] - groups['archiveFiles']),
            'missing': sorted((groups['runtimeFiles'] | groups['archiveFiles']) - set(hashes))})
    if 'excludedReasons' in manifest:
        reasons = manifest['excludedReasons']
        if (not isinstance(reasons, dict) or set(reasons) != groups['excludedFiles']
                or any(not isinstance(reason, str) or not reason.strip() for reason in reasons.values())):
            raise FlowError('资源清单 excludedReasons 必须逐项说明排除原因')
    _declaration({'declaration': manifest.get('declaration', {})}, None)
    unresolved = manifest.get('unresolved')
    if not isinstance(unresolved, list) or any(not isinstance(reason, str) or not reason for reason in unresolved):
        raise FlowError('资源清单 unresolved 必须是原因数组')
    if require_complete and unresolved:
        raise FlowError('资源清单尚未完成分类或依赖声明', 409, {'unresolved': unresolved})
    return manifest


def inventory(store, directory, record):
    """Observe managed files while still detecting additions outside the manifest."""
    directory = _directory(store, directory)
    actual = store._inventory(directory)
    manifest = validate_manifest(record)
    if manifest is None:
        return actual
    retained = set(manifest.get('runtimeFiles', [])) | set(manifest.get('archiveFiles', []))
    excluded = set(manifest.get('excludedFiles', [])) | set(manifest.get('declaration', {}).get('excludedFiles', []))
    excluded_dirs = manifest.get('declaration', {}).get('excludedDirectories', [])
    return {path: hash_ for path, hash_ in actual.items()
            if path in retained or (path not in excluded and not _temporary(path)
                and not any(path.startswith(prefix + '/') for prefix in excluded_dirs))}


def copy_resource_tree(store, source, target, record):
    """Copy the registered bytes, preserving legacy records without reinterpretation."""
    source, target = _directory(store, source), _directory(store, target)
    if record.get('resourceManifest') is None:
        store._copy_tree(source, target)
        return
    validate_manifest(record)
    if inventory(store, source, record) != record['fileHashes']:
        raise FlowError('资源在复制前已变化', 409)
    target.mkdir(parents=True, exist_ok=True)
    for relative in sorted(record['fileHashes']):
        store._copy_file(store._safe(relative, base=source, must_exist=True), store._safe(relative, base=target))
    if store._inventory(target) != record['fileHashes'] or inventory(store, source, record) != record['fileHashes']:
        raise FlowError('资源在复制期间发生变化', 409)


def runtime_files(record):
    manifest = validate_manifest(record, require_complete=True)
    if manifest is None:
        return sorted(path for path in record.get('fileHashes', {}) if PurePosixPath(path).name != '.DS_Store')
    return list(manifest['runtimeFiles'])
