"""Independent loopback services and one registered Demo entry resolver."""
from __future__ import annotations

import copy
import contextlib
import fcntl
import hashlib
import html as html_escape
import http.client
import json
import mimetypes
import os
import re
import secrets
import select
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from pf_core import FlowError, ProjectStore, parse_requirements, split_frontmatter
from pf_export import module_package

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif'}
CONTENT_EXTENSIONS = IMAGE_EXTENSIONS | {'.pdf', '.txt', '.md', '.csv'}
SERVICE_PROTOCOL = 2
_PREVIEW_CHILDREN = {}
_WORKBENCH_CHILDREN = {}
_BUILD_CACHE = {}
_BUILD_LOCK = threading.RLock()


def runtime_fingerprint(package_root=None):
    """Content identity of the installed Skill, independent of its install path."""
    root = Path(package_root or Path(__file__).resolve().parents[1])
    ignored = {'__pycache__', '.DS_Store', '.git'}
    with _BUILD_LOCK:
        signature = metadata_signature(root, ignored)
        cached = _BUILD_CACHE.get(str(root))
        if cached and cached[0] == signature:
            return cached[1]
        entries = []
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if name not in ignored)
            for name in sorted(names):
                path = Path(directory) / name
                if name in ignored or name.endswith('.pyc'):
                    continue
                if path.is_symlink():
                    raise FlowError('运行包不允许符号链接', 409)
                entries.append((path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
        fingerprint = hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()
        if signature != metadata_signature(root, ignored):
            raise FlowError('运行包在检查期间发生变化，请重试', 409)
        _BUILD_CACHE[str(root)] = (signature, fingerprint)
        return fingerprint


def runtime_status(started_fingerprint, installed_fingerprint=None, project_root=None, service_kind=None):
    try:
        installed = installed_fingerprint or runtime_fingerprint()
        fingerprint_error = None
    except (FlowError, OSError) as exc:
        # A package being replaced must not make a healthy service disappear and
        # accidentally start another process for the same project.
        installed, fingerprint_error = None, str(exc)
    valid = isinstance(started_fingerprint, str) and bool(re.fullmatch(r'[0-9a-f]{64}', started_fingerprint))
    status = 'unknown' if not valid or installed is None else ('current' if started_fingerprint == installed else 'stale')
    result = {'status': status, 'startedFingerprint': started_fingerprint if valid else None,
              'installedFingerprint': installed, 'restartRequired': status != 'current'}
    if fingerprint_error:
        result['fingerprintError'] = fingerprint_error
    if result['restartRequired'] and project_root and service_kind:
        result['restartCommand'] = [sys.executable, '-B', str(Path(__file__).with_name('flow.py')),
            'service', str(project_root), '--kind', service_kind, '--restart']
    return result


def metadata_signature(root, ignored=()):
    """A change hint, never an integrity verdict; do not read file contents."""
    root = Path(root)
    entries = []
    if not root.exists():
        return 'missing'
    if not root.is_dir():
        value = root.lstat()
        return str((value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_ino))
    for directory, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in ignored)
        for name in sorted(directories + [name for name in names if name not in ignored]):
            path = Path(directory) / name
            try:
                value = path.lstat()
                entries.append((path.relative_to(root).as_posix(), value.st_mode, value.st_size,
                                value.st_mtime_ns, value.st_ctime_ns, value.st_ino))
            except FileNotFoundError:
                entries.append((path.relative_to(root).as_posix(), 'removed'))
    return hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()


def entry_signature(path):
    """One filesystem entry only; directory children are deliberately not read."""
    try:
        value = Path(path).lstat()
        return (value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_ino)
    except FileNotFoundError:
        return 'missing'


class ServiceRegistry:
    """Private per-user discovery outside project data and project snapshots."""
    def __init__(self, project_root, service_kind='workbench', directory=None):
        if service_kind not in ('workbench', 'preview'):
            raise FlowError('本地服务种类无效', 400)
        self.project_root = str(Path(project_root).resolve())
        self.service_kind = service_kind
        self.directory = Path(directory) if directory else Path(tempfile.gettempdir()) / ('prototype-flow-services-' + str(os.getuid()))
        key = hashlib.sha256(self.project_root.encode()).hexdigest()
        # The old unsuffixed record belongs to the former combined server. It is
        # deliberately left alone and cannot discover either new service.
        self.path = self.directory / (key + '.' + service_kind + '.json')
        self.lock_path = self.directory / (key + '.' + service_kind + '.lock')

    @contextlib.contextmanager
    def lock(self):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise FlowError('本地服务发现目录不安全', 403)
        self.directory.chmod(0o700)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _read(self):
        if self.path.is_symlink():
            raise FlowError('本地服务记录不允许符号链接', 403)
        try:
            value = json.loads(self.path.read_text('utf-8'))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, ValueError):
            return {}

    def reuse(self):
        record = self._read()
        if (record.get('projectRoot') != self.project_root or record.get('serviceKind') != self.service_kind
                or record.get('protocolVersion') != SERVICE_PROTOCOL):
            return None
        connection = None
        try:
            pid = record['pid']
            if not isinstance(pid, int) or pid < 1:
                return None
            try:
                os.kill(pid, 0)
            except PermissionError:
                # A later sandbox may be unable to signal an otherwise reachable
                # process. Its authenticated health reply still has to prove the
                # exact PID, instance, project, service kind, and protocol below.
                pass
            project_id = ProjectStore(self.project_root)._project()['id']
            if record.get('projectId') != project_id:
                return None
            address = urlsplit(record['url'])
            if (address.scheme != 'http' or address.hostname != '127.0.0.1' or not address.port
                    or address.path or address.query or address.fragment or address.username):
                return None
            connection = http.client.HTTPConnection('127.0.0.1', address.port, timeout=2)
            connection.request('GET', '/api/health', headers={'X-Prototype-Flow-Token': record['token']})
            response = connection.getresponse()
            if response.status != 200:
                return None
            result = json.loads(response.read(65536))
            if (result.get('projectRoot') != self.project_root or result.get('instanceId') != record.get('instanceId')
                    or result.get('url') != record.get('url') or result.get('pid') != pid
                    or result.get('projectId') != project_id or result.get('serviceKind') != self.service_kind
                    or result.get('protocolVersion') != SERVICE_PROTOCOL):
                return None
            reused = {key: result[key] for key in ('url', 'previewOrigin', 'projectRoot', 'projectId', 'serviceKind', 'pid', 'transport')} | {'reused': True}
            # The running process's package may have been replaced since startup,
            # or it may run from an older copy. Compare against this caller's copy.
            reported_runtime = result.get('runtime') if isinstance(result.get('runtime'), dict) else {}
            reused['runtime'] = runtime_status(reported_runtime.get('startedFingerprint'),
                                               project_root=self.project_root, service_kind=self.service_kind)
            if self.service_kind == 'workbench':
                if result.get('requirementMapUrl') != result['url'] + '/requirement-map':
                    return None
                reused['requirementMapUrl'] = result['requirementMapUrl']
            return reused
        except (FlowError, OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
            return None
        finally:
            if connection:
                connection.close()

    def publish(self, server):
        if server.service_kind != self.service_kind:
            raise FlowError('不能登记不同种类的本地服务', 400)
        data = dict(server.info(), token=server.token, instanceId=server.instance_id, protocolVersion=SERVICE_PROTOCOL)
        descriptor, name = tempfile.mkstemp(prefix='.service-', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(data, output)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def forget(self, instance_id):
        if self._read().get('instanceId') == instance_id:
            self.path.unlink(missing_ok=True)


def safe_file(root: Path, relative: str, store=None) -> Path:
    if not relative or '\x00' in relative or '\\' in relative:
        raise FlowError('无效的文件路径', 400)
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or any(part.startswith('.') for part in p.parts):
        raise FlowError('该文件不在允许的资源范围内', 403)
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise FlowError('资源入口不允许符号链接', 403)
    candidate = (root / p).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise FlowError('该文件超出项目范围', 403)
    if not (store._is_file(candidate) if store else candidate.is_file()):
        raise FlowError('文件不存在', 404)
    return candidate


def rows(value, key='items'):
    if isinstance(value, list):
        return value
    return value.get(key, []) if isinstance(value, dict) else []


def error_status(exc):
    return getattr(exc, 'status', getattr(exc, 'status_code', 400))


def inject_session_token(html, token):
    """Replace the build placeholder and normalize legacy duplicate token tags."""
    token_tags = re.compile(r'<meta\b(?=[^>]*\sname\s*=\s*[\"\']pf-token[\"\'])[^>]*>', re.I)
    clean = token_tags.sub('', html)
    meta = '<meta name="pf-token" content="%s">' % token
    if not re.search(r'</head\s*>', clean, re.I):
        raise FlowError('工作台入口缺少有效的 head，请重新构建前端', 503)
    return re.sub(r'</head\s*>', lambda match: meta + match.group(0), clean, count=1, flags=re.I)


class FlowServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class DemoAccess:
    """Shared path and integrity checks; no workbench or process dependency."""

    def _init_demo_access(self, store):
        self.store = store
        self._integrity_cache = {}
        self._integrity_lock = threading.RLock()

    def _init_runtime(self):
        self.started_fingerprint = runtime_fingerprint()

    def runtime(self):
        return runtime_status(self.started_fingerprint, project_root=self.store.root, service_kind=self.service_kind)

    def _checked_history(self, version):
        if not version:
            return self.store.root
        root = self.store.content_root(version)
        with self._integrity_lock:
            signature = metadata_signature(root.parent)
            key = ('history', version)
            if self._integrity_cache.get(key) != signature:
                self.store._verify_snapshot(version)
                if signature != metadata_signature(root.parent):
                    raise FlowError('历史版本在检查期间发生变化，请重试', 409)
                self._integrity_cache[key] = signature
        return root


    def _checked_artifact(self, artifact_id, version=None):
        """Check only this artifact; cache successful byte checks behind metadata."""
        with self.store._transaction(read_only=True), self.store._read_session():
            root = self._checked_history(version)
            artifact = next((a for a in self.store._read('artifacts.json', {'items': []}, base=root)['items']
                             if a['id'] == artifact_id), None)
            if not artifact:
                raise FlowError('该版本没有这个 Demo', 404)
            artifact_root = self.store._safe(artifact['path'], base=root)
            if not self.store._is_dir(artifact_root):
                raise FlowError('Demo 文件与登记版本不一致，请登记新产物后查看', 409)
            expected = artifact.get('fileHashes', {})
            with self._integrity_lock:
                if artifact.get('kind') == 'working-draft' and not version:
                    # A live draft is an editable preview. Historical snapshots and
                    # frozen artifacts still require their registered byte hashes.
                    signature = metadata_signature(artifact_root)
                    key = ('live-draft', artifact_id, str(artifact_root))
                    cached = self._integrity_cache.get(key)
                    if self.store._has_virtual_files(artifact_root) or not cached or cached[0] != signature:
                        hashes = self.store._inventory(artifact_root)
                        if signature != metadata_signature(artifact_root):
                            raise FlowError('工作稿在读取期间发生变化，请重试', 409)
                        cached = (signature, hashes)
                        self._integrity_cache[key] = cached
                    return dict(artifact, fileHashes=cached[1]), artifact_root
                signature = (metadata_signature(artifact_root), json.dumps(expected, sort_keys=True))
                key = ('artifact', version, artifact_id, str(artifact_root))
                if self.store._has_virtual_files(artifact_root) or self._integrity_cache.get(key) != signature:
                    if self.store._resource_inventory(artifact_root, artifact) != expected:
                        raise FlowError('Demo 文件与登记版本不一致，请登记新产物后查看', 409)
                    if signature[0] != metadata_signature(artifact_root):
                        raise FlowError('Demo 在检查期间发生变化，请重试', 409)
                    self._integrity_cache[key] = signature
            return artifact, artifact_root


    def demo_url(self, artifact, version=None, route=None):
        entry = artifact.get('entryHtml', 'index.html')
        route = route or entry
        if route.startswith(('?', '#')):
            route = entry + route
        parsed = urlsplit(route)
        if parsed.scheme or parsed.netloc or parsed.path.startswith('/'):
            return None
        if '..' in Path(parsed.path).parts or '\\' in parsed.path:
            return None
        base = '%s/demo/%s/%s/' % (
            self.preview_origin, quote(version or 'working', safe=''),
            quote(artifact['id'], safe=''))
        return base + quote(unquote(parsed.path or entry), safe='/') + (
            '?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')

    @staticmethod
    def _entry_error(message, code, status=409, **details):
        raise FlowError(message, status, {'code': code, **details})

    @staticmethod
    def _artifact_bindings(artifact, live):
        # An explicitly empty frozen namespace remains authoritative.
        frozen = artifact.get('kind') != 'working-draft' and 'frozenRelations' in artifact
        source = artifact['frozenRelations'].get('bindings', []) if frozen else live
        return [copy.deepcopy(binding) for binding in source if binding.get('artifactId') == artifact['id']]

    def _validate_primary_entries(self, bindings):
        declarations = {}
        for binding in bindings:
            requirements = binding.get('requirementIds', [])
            primary = binding.get('primaryRequirementIds', [])
            if (not isinstance(primary, list) or any(not isinstance(value, str) for value in primary)
                    or len(set(primary)) != len(primary) or not isinstance(requirements, list)
                    or not set(primary).issubset(requirements)):
                self._entry_error('默认 Demo 入口声明无效', 'default-entry-conflict', bindingId=binding.get('id'))
            for requirement in primary:
                if requirement in declarations:
                    self._entry_error('同一需求存在冲突的默认 Demo 入口', 'default-entry-conflict', requirementId=requirement)
                declarations[requirement] = binding
        return declarations

    def _entry_route(self, artifact, binding=None):
        entry = artifact.get('entryHtml', 'index.html')
        route = binding.get('route') if binding else entry
        if not isinstance(route, str) or not route:
            self._entry_error('页面状态的演示入口无效', 'entry-invalid', 400)
        if route.startswith(('?', '#')):
            route = entry + route
        parsed = urlsplit(route)
        relative = unquote(parsed.path or entry)
        if (parsed.scheme or parsed.netloc or relative.startswith('/') or '..' in Path(relative).parts
                or '\\' in relative or '\x00' in relative or any(part.startswith('.') for part in Path(relative).parts)):
            self._entry_error('页面状态的演示入口无效', 'entry-invalid', 400)
        if Path(relative).suffix.lower() not in ('.html', '.htm'):
            self._entry_error('页面状态未指向 HTML 演示入口', 'entry-invalid', 400)
        return route, relative

    def _requirement_exists(self, root, project, requirement_id):
        index = self.store._read('requirement-index.json', {'items': []}, base=root)
        requirement = next((item for item in index['items'] if item['id'] == requirement_id), None)
        module = next((item for item in project['modules'] if requirement
                       and item['documentId'] == requirement['documentId']), None)
        if not module:
            self._entry_error('需求在此版本中不存在，请重新定位当前对象', 'requirement-missing', 404,
                              requirementId=requirement_id)
        path = self.store._safe(module['documentPath'], base=root, must_exist=True)
        content = self.store._file_bytes(path).decode('utf-8')
        metadata, _, _ = split_frontmatter(content)
        if metadata.get('documentId') != module['documentId'] or metadata.get('moduleId') != module['id']:
            self._entry_error('需求文档身份已变化，请重新核对对象', 'requirement-changed',
                              requirementId=requirement_id)
        if not any(item['id'] == requirement_id for item in parse_requirements(content, module['documentId'], module['id'])):
            self._entry_error('需求已从当前文档移除，请重新定位当前对象', 'requirement-missing', 404,
                              requirementId=requirement_id)

    def _current_demo_metadata(self, artifact, project, root):
        run = self.store._read('runs/' + artifact['runId'] + '.json', {}, base=root) if artifact.get('runId') else {}
        document_index = {item['id']: item for item in run.get('documentIndex', [])}
        modules = {item['documentId']: item for item in project.get('modules', [])}
        documents = []
        fixed_documents = {item['id']: item for item in artifact.get('inputDocuments', [])}
        for document_id, business_hash in sorted(artifact.get('documentHashes', {}).items()):
            document = fixed_documents.get(document_id, {})
            identity = document_index.get(document_id, {})
            module = modules.get(document_id, {})
            documents.append({'id': document_id, 'businessHash': business_hash,
                              'path': document.get('path') or identity.get('path') or module.get('documentPath'),
                              'revision': document.get('revision') if document.get('businessHash') == business_hash else None,
                              'title': identity.get('title') or module.get('title') or document_id})
        return {'artifactId': artifact['id'], 'title': artifact.get('title') or artifact['id'],
                'kind': artifact.get('kind', 'frozen'), 'draftRevision': artifact.get('draftRevision'),
                'editStatus': artifact.get('editStatus'), 'status': artifact.get('status'),
                'inputRevision': artifact.get('inputRevision'), 'projectRevision': project['revision'],
                'documents': documents, 'requirementIds': sorted(artifact.get('requirementHashes', {})),
                'updatedAt': artifact.get('updatedAt') or artifact.get('createdAt'),
                'recentChange': {'runId': run.get('id'), 'summary': (run.get('change') or {}).get('summary') or
                                ((run.get('outputs') or {}).get('summary') if isinstance(run.get('outputs'), dict) else None),
                                'requirementIds': run.get('requirementIds', []), 'completedAt': run.get('finishedAt')},
                'freeze': {key: copy.deepcopy(artifact.get(key)) for key in
                           ('draftSourceArtifactId', 'lastFrozenArtifactId', 'lastFrozenRevision', 'frozenFrom')}}

    def resolve_entry(self, version=None, requirement_id=None, binding_id=None,
                      artifact_id=None, within_artifact=None, check_files=True, current=False):
        """Resolve stable objects without discovering or starting a service."""
        if current and (version not in (None, '', 'working') or within_artifact):
            self._entry_error('当前 Demo 入口不接受历史版本或所属产物；历史请使用准确产物入口', 'target-invalid', 400)
        if sum(bool(value) for value in (requirement_id, binding_id, artifact_id, current)) != 1:
            self._entry_error('请指定且只指定一个需求、页面绑定或 Demo 产物', 'target-invalid', 400)
        if within_artifact and not binding_id:
            self._entry_error('所属产物仅可用于定位页面绑定', 'target-invalid', 400)
        version = None if version in (None, '', 'working') else version
        with self.store._transaction(read_only=True), self.store._read_session():
            root = self._checked_history(version)
            project = self.store._project(base=root)
            registry = self.store._read('artifacts.json', {'items': []}, base=root)
            artifacts = {artifact['id']: artifact for artifact in registry['items']}
            live = self.store._read('relations.json', {'bindings': []}, base=root)['bindings']
            binding = None
            if current:
                artifact_id = registry.get('currentArtifactId')
                if not artifact_id:
                    self._entry_error('当前项目尚未登记可打开的 Demo', 'current-demo-missing', 404)
            elif requirement_id:
                self._requirement_exists(root, project, requirement_id)
                covering = [item for item in live if requirement_id in item.get('requirementIds', [])]
                current_artifact_id = registry.get('currentArtifactId')
                candidates = {item.get('artifactId') for item in covering}
                if current_artifact_id in candidates:
                    artifact_id = current_artifact_id
                elif len(candidates) == 1:
                    artifact_id = next(iter(candidates))
                elif not candidates:
                    self._entry_error('该需求尚未关联 Demo', 'demo-missing', 404, requirementId=requirement_id)
                else:
                    self._entry_error('该需求关联多个 Demo，请使用明确的产物或页面链接', 'artifact-ambiguous',
                                      requirementId=requirement_id, artifactIds=sorted(candidates))
            elif binding_id:
                namespaces = [artifacts[within_artifact]] if within_artifact in artifacts else (
                    [] if within_artifact else list(artifacts.values()))
                matches = [(artifact['id'], item) for artifact in namespaces
                           for item in self._artifact_bindings(artifact, live) if item.get('id') == binding_id]
                if not matches:
                    self._entry_error('该版本或指定产物没有这个页面状态', 'binding-missing', 404,
                                      bindingId=binding_id, artifactId=within_artifact)
                if len(matches) != 1:
                    self._entry_error('该页面绑定存在于多个产物，请指定所属产物', 'binding-ambiguous',
                                      bindingId=binding_id, artifactIds=sorted({item[0] for item in matches}))
                artifact_id, binding = matches[0]
            artifact = artifacts.get(artifact_id)
            if not artifact:
                self._entry_error('该版本没有这个 Demo', 'artifact-missing', 404, artifactId=artifact_id)
            bindings = self._artifact_bindings(artifact, live)
            declarations = self._validate_primary_entries(bindings)
            if requirement_id:
                binding = declarations.get(requirement_id)
                if binding is None:
                    legal = []
                    for candidate in bindings:
                        if requirement_id in candidate.get('requirementIds', []):
                            try:
                                self._entry_route(artifact, candidate)
                            except FlowError:
                                continue
                            legal.append(candidate)
                    if not legal:
                        self._entry_error('该需求没有可用的 Demo 页面绑定', 'binding-missing', 404,
                                          requirementId=requirement_id, artifactId=artifact_id)
                    if len(legal) != 1:
                        self._entry_error('尚未设置默认 Demo 入口', 'default-entry-missing',
                                          requirementId=requirement_id, artifactId=artifact_id,
                                          bindingIds=[item['id'] for item in legal])
                    binding = legal[0]
            route, relative = self._entry_route(artifact, binding)
            registered = artifact
            if check_files:
                artifact, artifact_root = self._checked_artifact(artifact_id, version)
                file = safe_file(artifact_root, relative, self.store)
                if relative not in artifact.get('fileHashes', {}):
                    self._entry_error('该入口未登记在 Demo 中', 'entry-invalid', 403)
                if self.store._file_digest(file) != artifact['fileHashes'][relative]:
                    self._entry_error('请求文件与登记版本不一致，请重新验证产物', 'entry-invalid')
            checked = {key: artifact[key] for key in ('id', 'kind', 'draftRevision', 'editStatus') if key in artifact}
            editing = artifact.get('kind') == 'working-draft' and (artifact.get('fileHashes') != registered.get('fileHashes')
                or artifact.get('activeRunId') or artifact.get('editStatus') != 'ready')
            checked['integrityStatus'] = ('editing' if editing else 'intact') if check_files else 'unchecked'
            result = {'versionId': version or 'working', 'historical': bool(version),
                      'artifact': checked, 'route': route, 'entryHtml': artifact.get('entryHtml', 'index.html')}
            if current:
                result.update(current=True, currentDemo=self._current_demo_metadata(registered, project, root))
            if requirement_id:
                result['requirementId'] = requirement_id
            if binding:
                evaluated = copy.deepcopy(binding)
                if check_files and (registered.get('kind') == 'working-draft' or 'frozenRelations' not in registered):
                    evaluated = next(item for item in self.store._evaluated_relations(root, binding_ids={binding['id']},
                        artifact_inventories={artifact_id: artifact['fileHashes']})['bindings']
                        if item['id'] == binding['id'] and item.get('artifactId') == artifact_id)
                elif evaluated.get('verified'):
                    reason = 'artifact-unchecked' if not check_files else None
                    if check_files:
                        try:
                            reason = ('missing-fingerprint' if not binding.get('verificationHash') else
                                      'fingerprint-changed' if binding['verificationHash'] != self.store._binding_fingerprint(
                                          binding, root, {artifact_id: artifact}) else None)
                        except (FlowError, OSError, UnicodeError):
                            reason = 'dependency-changed'
                    if reason:
                        evaluated.update(verified=False, status='needs-review', verificationStatus=reason)
                result['binding'] = evaluated
            return result


    def _base_handler(self):
        class Handler(BaseHTTPRequestHandler):
            server_version = 'PrototypeFlow/1.0'

            def log_message(self, fmt, *args):
                # Requests can contain local document names. Keep terminal output to lifecycle/errors.
                pass

            def respond_headers(self, status=200, content_type='application/json; charset=utf-8', length=None, csp=None, filename=None):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
                if length is not None:
                    self.send_header('Content-Length', str(length))
                if csp:
                    self.send_header('Content-Security-Policy', csp)
                if filename:
                    self.send_header('Content-Disposition', "attachment; filename=prototype-flow.zip; filename*=UTF-8''" + quote(filename, safe=''))
                self.end_headers()

            def json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.respond_headers(status, length=len(body))
                self.wfile.write(body)

            def failure(self, exc):
                if isinstance(exc, FlowError):
                    self.json({'error': str(exc), 'details': getattr(exc, 'details', None)}, error_status(exc))
                elif isinstance(exc, (ValueError, KeyError, TypeError)):
                    self.json({'error': '请求参数无效', 'details': str(exc)}, 400)
                elif isinstance(exc, FileNotFoundError):
                    self.json({'error': '文件不存在'}, 404)
                else:
                    self.json({'error': '本地服务处理失败', 'details': str(exc)}, 500)

            def check_host(self):
                expected = '127.0.0.1:%s' % self.server.server_port
                if self.headers.get('Host') != expected:
                    raise FlowError('不允许的访问地址', 403)

            def send_file(self, path, csp=None, expected=None, store=None):
                data = store._file_bytes(path) if store else path.read_bytes()
                if expected is not None and hashlib.sha256(data).hexdigest() != expected:
                    raise FlowError('请求文件与登记版本不一致，请重新验证产物', 409)
                kind = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                if kind.startswith('text/') or kind == 'application/javascript':
                    kind += '; charset=utf-8'
                self.respond_headers(200, kind, len(data), csp)
                self.wfile.write(data)

        return Handler

    def _demo_handler(self):
        owner = self
        Base = self._base_handler()

        class Handler(Base):
            def do_GET(self):
                try:
                    self.check_host()
                    if urlsplit(self.path).path in ('/demo/current', '/demo/current/'):
                        # Keep assets on the precise artifact namespace. A pointer
                        # switch must not mix two bundles while a page is loading.
                        entry = owner.resolve_entry(current=True)
                        target = owner.demo_url({'id': entry['artifact']['id'], 'entryHtml': entry['entryHtml']}, route=entry['route'])
                        query = urlsplit(self.path).query
                        if query:
                            parsed_target = urlsplit(target)
                            target = parsed_target._replace(query=query).geturl()
                        self.send_response(307)
                        self.send_header('Location', target)
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', '0')
                        return self.end_headers()
                    if urlsplit(self.path).path == '/api/health':
                        token = self.headers.get('X-Prototype-Flow-Token', '')
                        if not secrets.compare_digest(token, owner.token):
                            raise FlowError('预览服务身份校验失败', 401)
                        return self.json(owner.health())
                    parts = unquote(urlsplit(self.path).path).split('/')
                    if len(parts) < 5 or parts[1] != 'demo':
                        raise FlowError('演示入口不存在', 404)
                    version = None if parts[2] == 'working' else parts[2]
                    artifact, artifact_root = owner._checked_artifact(parts[3], version)
                    relative = '/'.join(parts[4:]) or artifact.get('entryHtml', 'index.html')
                    # No workbench token/API is exposed on this origin.
                    policy = "default-src 'self' data: blob: https:; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; connect-src 'self' https:; object-src 'none'; frame-ancestors 'none'"
                    file = safe_file(artifact_root, relative, owner.store)
                    expected = artifact.get('fileHashes', {}).get(file.relative_to(artifact_root).as_posix())
                    if not expected:
                        raise FlowError('该资源未登记在 Demo 中', 403)
                    return self.send_file(file, policy, expected, owner.store)
                except Exception as exc:
                    self.failure(exc)

            def do_POST(self):
                self.json({'error': '演示服务只读'}, 405)

            do_PUT = do_POST
            do_PATCH = do_POST
            do_DELETE = do_POST

            def do_OPTIONS(self):
                self.json({'error': '不支持跨站接口请求'}, 403)

        return Handler


class PreviewServer(DemoAccess):
    service_kind = 'preview'

    def __init__(self, store, port=0):
        self._init_demo_access(store)
        self._init_runtime()
        self.project_id = store._project()['id']
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_urlsafe(24)
        self.http = FlowServer(('127.0.0.1', port), self._demo_handler())
        self.origin = self.preview_origin = 'http://127.0.0.1:%s' % self.http.server_port
        self._threads = []

    def start(self):
        thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        thread.start()
        self._threads.append(thread)
        return self.info()

    def info(self):
        return {'url': self.origin, 'previewOrigin': self.preview_origin,
                'projectRoot': str(self.store.root), 'projectId': self.project_id,
                'serviceKind': self.service_kind, 'pid': os.getpid(),
                'transport': 'loopback_http', 'reused': False, 'runtime': self.runtime()}

    def health(self):
        if self.store._project()['id'] != self.project_id or not self._threads or not all(thread.is_alive() for thread in self._threads):
            raise FlowError('本地预览服务尚未就绪', 503)
        return dict(self.info(), instanceId=self.instance_id, protocolVersion=SERVICE_PROTOCOL)

    def close(self):
        if self._threads:
            self.http.shutdown()
        self.http.server_close()
        for thread in self._threads:
            thread.join(timeout=3)


def resolve_demo_entry(store, version=None, requirement_id=None, binding_id=None,
                       artifact_id=None, within_artifact=None, check_files=True, current=False):
    resolver = DemoAccess()
    resolver._init_demo_access(store)
    return resolver.resolve_entry(version, requirement_id, binding_id, artifact_id, within_artifact, check_files, current)


def preview(project_root, reuse=True, port=0):
    """Start only a detached preview worker; serialize discovery per project."""
    root = project_root.root if isinstance(project_root, ProjectStore) else project_root
    store = ProjectStore(root)
    store._project()  # Identity only; no full state, workbench build, or Demo bytes.
    registry = ServiceRegistry(store.root, 'preview')
    with registry.lock():
        existing = registry.reuse() if reuse else None
        if existing:
            if port and urlsplit(existing['previewOrigin']).port != port:
                raise FlowError('已有预览使用其他端口；请停止它或省略显式预览端口', 409)
            return existing
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
            '--preview-worker', str(store.root), '--port', str(port),
            '--registry-directory', str(registry.directory)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        try:
            if not select.select([process.stdout], [], [], 10)[0]:
                raise FlowError('独立预览启动超时', 503)
            line = process.stdout.readline()
            try:
                result = json.loads(line)
            except ValueError:
                raise FlowError('独立预览未返回有效启动结果', 503)
            if result.get('error'):
                raise FlowError(result['error'], result.get('status', 503))
            discovered = registry.reuse()
            if not discovered or discovered['pid'] != process.pid:
                raise FlowError('独立预览身份校验失败', 503)
            _PREVIEW_CHILDREN[process.pid] = process
            return dict(discovered, reused=False)
        except Exception:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise
        finally:
            process.stdout.close()


ensure_preview = preview


def stop_preview(project_root, expected_instance_id=None):
    """Stop only the healthy registered preview, never a workbench process."""
    registry = ServiceRegistry(project_root, 'preview')
    with registry.lock():
        service = registry.reuse()
        if not service:
            return False
        instance_id = registry._read().get('instanceId')
        if expected_instance_id is not None and instance_id != expected_instance_id:
            raise FlowError('预览服务实例已变化，请重新连接后再重启', 409)
        os.kill(service['pid'], signal.SIGTERM)
    process = _PREVIEW_CHILDREN.pop(service['pid'], None)
    if process:
        process.wait(timeout=5)
    else:
        # A different CLI may have created it. Wait for that instance to release
        # its own record without acquiring the lock needed by its exit handler.
        event = threading.Event()
        for _ in range(100):
            if registry._read().get('instanceId') != instance_id:
                return True
            event.wait(0.05)
        raise FlowError('独立预览尚未完成停止', 503)
    return True


def demo_entry(store, version=None, requirement_id=None, binding_id=None,
               artifact_id=None, within_artifact=None, current=False):
    registry = ServiceRegistry(store.root, 'preview')
    with registry.lock():
        service = registry.reuse()
    if not service:
        raise FlowError('独立预览服务未运行，请先运行 preview', 503, {'code': 'preview-not-running'})
    if current and service['runtime']['restartRequired']:
        raise FlowError('预览服务运行旧版或未知版本，请显式重启后打开当前 Demo', 409,
                        {'code': 'runtime-not-current', 'runtime': service['runtime']})
    resolver = DemoAccess()
    resolver._init_demo_access(store)
    resolver.preview_origin = service['previewOrigin']
    result = resolver.resolve_entry(version, requirement_id, binding_id, artifact_id, within_artifact, current=current)
    result['url'] = resolver.demo_url({'id': result['artifact']['id'], 'entryHtml': result['entryHtml']},
                                     None if result['versionId'] == 'working' else result['versionId'], result['route'])
    if current:
        result['canonicalUrl'], result['url'] = result['url'], service['previewOrigin'] + '/demo/current/'
    result['runtime'] = service['runtime']
    return result


def _preview_worker(project_root, port, registry_directory):
    registry = ServiceRegistry(project_root, 'preview', directory=registry_directory)
    server = None
    try:
        server = PreviewServer(ProjectStore(project_root), port)
        event = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: event.set())
        server.start()
        # The launching process owns the discovery lock until this reply is read.
        registry.publish(server)
        print(json.dumps(server.info(), ensure_ascii=False), flush=True)
        while not event.wait(1):
            pass
    except Exception as exc:
        print(json.dumps({'error': str(exc), 'status': error_status(exc)}, ensure_ascii=False), flush=True)
        return 1
    finally:
        if server:
            server.close()
            with registry.lock():
                registry.forget(server.instance_id)
    return 0


class WorkbenchServer(DemoAccess):
    service_kind = 'workbench'

    def __init__(self, store: ProjectStore, port=0, preview_port=0, assets=None):
        self._init_demo_access(store)
        self._init_runtime()
        self.project_id = store._project()['id']
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_urlsafe(24)
        self.assets = Path(assets or Path(__file__).resolve().parents[1] / 'assets' / 'workbench')
        self.preview_port = preview_port
        self._preview_info = None
        self.http = FlowServer(('127.0.0.1', port), self._workbench_handler())
        self.origin = 'http://127.0.0.1:%s' % self.http.server_port
        self._threads = []

    @property
    def preview_origin(self):
        return self._preview_info['previewOrigin'] if self._preview_info else None

    @property
    def demo(self):
        """Compatibility for Python callers explicitly requesting the Demo port."""
        self._preview_info = preview(self.store.root, port=self.preview_port)
        return SimpleNamespace(server_port=urlsplit(self._preview_info['previewOrigin']).port)

    def start(self):
        thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        thread.start()
        self._threads.append(thread)
        return self.info()

    def info(self):
        return {'url': self.origin, 'previewOrigin': self.preview_origin,
                'requirementMapUrl': self.origin + '/requirement-map',
                'projectRoot': str(self.store.root), 'projectId': self.project_id,
                'serviceKind': self.service_kind, 'pid': os.getpid(),
                'transport': 'loopback_http', 'reused': False, 'runtime': self.runtime()}

    def health(self):
        map_assets = Path(__file__).resolve().parents[1] / 'assets/conversation-ui'
        map_files = ('requirement-map.html', 'requirement-map.css', 'requirement-map.js', 'requirement-map-live.js')
        if (self.store._project()['id'] != self.project_id or not all((map_assets / name).is_file() for name in map_files)
                or not self._threads or not all(thread.is_alive() for thread in self._threads)):
            raise FlowError('本地需求图服务尚未就绪', 503)
        return dict(self.info(), instanceId=self.instance_id, protocolVersion=SERVICE_PROTOCOL)

    def revision(self, scope='all'):
        if scope not in ('active', 'all'):
            raise FlowError('变化检查范围无效', 400)
        # Saved mutations replace these files atomically. Reading their metadata and
        # the runs directory catches saves without walking old artifacts or runs.
        self.store._project()
        fast_paths = ('project.json', 'artifacts.json', 'relations.json', 'sources.json',
                      'frameworks.json', 'maintenance.json', 'impact.json', 'feishu.json',
                      'requirement-index.json', 'runs')
        fast = {name: entry_signature(self.store.meta / name) for name in fast_paths}
        state_token = hashlib.sha256(json.dumps(fast, sort_keys=True).encode()).hexdigest()
        result = {'revisionToken': state_token, 'stateRevisionToken': state_token,
                  'projectRoot': str(self.store.root), 'runtime': self.runtime()}
        if scope == 'active':
            return result
        # Scan only metadata. Integrity is checked separately before content is used.
        project = self.store._project()
        paths = {project['libraryRoot'], 'DESIGN.md'}
        paths.update(a['path'] for a in self.store._read('artifacts.json', {'items': []})['items'])
        paths.update(f['path'] for f in self.store._frameworks()['items'])
        paths.update(b['screenshot'] for b in self.store._read('relations.json', {'bindings': []})['bindings']
                     if b.get('screenshot'))
        for source in self.store._read('sources.json', {'items': []})['items']:
            paths.update(source[key] for key in ('path', 'archivePath') if source.get(key))
        # Skip nested paths already covered by their library or artifact directory.
        roots = sorted(paths, key=lambda value: (len(Path(value).parts), value))
        scopes = []
        for relative in roots:
            if not any(Path(parent) in Path(relative).parents for parent in scopes):
                scopes.append(relative)
        signatures = {relative: metadata_signature(self.store._safe(relative), {'__pycache__', '.DS_Store'})
                      for relative in scopes}
        signatures['.prototype-flow'] = metadata_signature(self.store.meta,
            {'store.lock', 'revisions', 'run-inputs', 'run-outputs', 'draft-revisions', 'draft-blobs',
             'feishu-plans', '__pycache__'})
        versions = self.store._safe('versions')
        signatures['versions'] = {path.name: metadata_signature(path / 'manifest.json')
                                  for path in sorted(versions.iterdir()) if path.is_dir() and not path.is_symlink()} if versions.exists() else {}
        token = hashlib.sha256(json.dumps(signatures, sort_keys=True).encode()).hexdigest()
        return dict(result, revisionToken=token, externalRevisionToken=token)



    def close(self):
        if self._threads:
            self.http.shutdown()
        self.http.server_close()
        for thread in self._threads:
            thread.join(timeout=3)


    def enriched_state(self, version=None):
        state = copy.deepcopy(self.store.workbench_state(version=version))
        state['previewOrigin'] = self.preview_origin
        state['historical'] = bool(version)
        state['selectedVersion'] = version
        artifacts = rows(state.get('artifacts'))
        for artifact in artifacts:
            artifact['demoEntry'] = {'artifact': artifact['id'], 'version': version or 'working'}
        relations = state.get('relations', {})
        for binding in rows(relations, 'bindings'):
            binding['demoEntry'] = {'binding': binding['id'], 'withinArtifact': binding.get('artifactId'),
                                    'version': version or 'working'}
            if binding.get('screenshot'):
                query = {'path': binding['screenshot']}
                if version:
                    query['version'] = version
                binding['screenshotUrl'] = '/content?' + urlencode(query)
        return state

    def requirement_map(self, module_id=None, requirement_id=None, version=None):
        from pf_requirement_map import requirement_map_state
        snapshot = requirement_map_state(self.store, module_id, requirement_id, version)
        return {'snapshot': snapshot, 'requirementMap': snapshot['data']['requirementMap']}

    def requirement_map_html(self, module_id=None, requirement_id=None, version=None):
        from render_conversation import render_requirement_map
        snapshot = self.requirement_map(module_id, requirement_id, version)['snapshot']
        fragment = render_requirement_map(snapshot)
        nonce = secrets.token_urlsafe(24)
        fragment = fragment.replace('<script>', '<script nonce="' + nonce + '">')
        html = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="pf-token" content="' + html_escape.escape(self.token, quote=True) + '">'
            '<title>需求地图 · ' + html_escape.escape(snapshot['project']['name']) + '</title>'
            '<style>html{height:100%;color-scheme:light dark}body{height:calc(100dvh - 40px);'
            'margin:20px;overflow:hidden;background:light-dark(#f6f7f9,#17191c)}'
            'main{height:100%;max-width:1440px;margin:0 auto}button{cursor:pointer}'
            '@media(max-width:720px){body{height:calc(100dvh - 16px);margin:8px}}'
            '</style></head><body class="pf-requirement-map-live"><main>' + fragment +
            '</main><script src="/requirement-map-assets/requirement-map-live.js"></script></body></html>')
        policy = ("default-src 'self'; script-src 'self' 'nonce-" + nonce +
                  "'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self'; "
                  "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; frame-src 'none'")
        return html.encode('utf-8'), policy




    def demo_entry(self, version=None, binding_id=None, artifact_id=None,
                   requirement_id=None, within_artifact=None, current=False):
        result = self.resolve_entry(version, requirement_id, binding_id, artifact_id, within_artifact, current=current)
        self._preview_info = preview(self.store.root, port=self.preview_port)
        if current and self._preview_info['runtime']['restartRequired']:
            raise FlowError('预览服务运行旧版或未知版本，请显式重启后打开当前 Demo', 409,
                            {'code': 'runtime-not-current', 'runtime': self._preview_info['runtime']})
        result['url'] = self.demo_url({'id': result['artifact']['id'], 'entryHtml': result['entryHtml']},
                                     None if result['versionId'] == 'working' else result['versionId'], result['route'])
        if current:
            result['canonicalUrl'], result['url'] = result['url'], self.preview_origin + '/demo/current/'
        result['runtime'] = self._preview_info['runtime']
        return result

    def _workbench_handler(self):
        owner = self
        Base = self._base_handler()

        class Handler(Base):
            def authenticate(self, mutation=False):
                self.check_host()
                token = self.headers.get('X-Prototype-Flow-Token', '')
                if not secrets.compare_digest(token, owner.token):
                    raise FlowError('会话已失效，请重新打开工作台', 401)
                origin = self.headers.get('Origin')
                if origin and origin != owner.origin:
                    raise FlowError('不允许从其他页面访问项目接口', 403)
                if mutation and origin != owner.origin:
                    raise FlowError('写入请求必须来自当前工作台', 403)

            def do_GET(self):
                try:
                    self.check_host()
                    parsed = urlsplit(self.path)
                    path = unquote(parsed.path)
                    query = parse_qs(parsed.query)
                    version = query.get('version', [None])[0]
                    if version == 'working':
                        version = None
                    if path.startswith('/api/'):
                        self.authenticate()
                        if path == '/api/state':
                            return self.json(owner.enriched_state(version))
                        if path == '/api/requirement-map':
                            return self.json(owner.requirement_map(query.get('module', [None])[0],
                                query.get('requirement', [None])[0], version))
                        if path == '/api/revision':
                            return self.json(owner.revision(query.get('scope', ['all'])[0]))
                        if path == '/api/health':
                            return self.json(owner.health())
                        if path == '/api/demo-entry':
                            return self.json(owner.demo_entry(version=version,
                                binding_id=query.get('binding', [None])[0], artifact_id=query.get('artifact', [None])[0],
                                requirement_id=query.get('requirement', [None])[0],
                                within_artifact=query.get('withinArtifact', [None])[0],
                                current=query.get('current', ['false'])[0] in ('1', 'true')))
                        if path == '/api/current-demo':
                            return self.json(owner.resolve_entry(version=version, current=True))
                        if path.startswith('/api/modules/') and path.endswith('/package'):
                            parts = path.split('/')
                            if len(parts) != 5:
                                raise FlowError('接口不存在', 404)
                            delivery_format = query.get('format', ['project_bundle'])[0]
                            data, filename = module_package(owner.store, parts[3], version,
                                                            delivery_format=delivery_format)
                            content_type = 'text/html; charset=utf-8' if delivery_format == 'single_html' else 'application/zip'
                            self.respond_headers(200, content_type, len(data), filename=filename)
                            return self.wfile.write(data)
                        if path.startswith('/api/documents/'):
                            return self.json(owner.store.document(path.split('/')[-1], version=version))
                        if path == '/api/versions':
                            return self.json(owner.store.versions())
                        if path == '/api/compare':
                            result = owner.store.compare(query.get('from', [''])[0], query.get('to', ['working'])[0])
                            return self.json(result)
                        if path == '/api/validate':
                            return self.json(owner.store.validate())
                        raise FlowError('接口不存在', 404)
                    if path == '/content':
                        if version:
                            # Validate the immutable manifest before serving any historical bytes.
                            owner._checked_history(version)
                        root = owner.store.content_root(version=version)
                        file = safe_file(root, query.get('path', [''])[0], owner.store)
                        if file.suffix.lower() not in CONTENT_EXTENSIONS:
                            raise FlowError('该类型不作为工作台内容提供', 403)
                        return self.send_file(file, "sandbox; default-src 'none'; style-src 'unsafe-inline'", store=owner.store)
                    if path == '/requirement-map':
                        data, policy = owner.requirement_map_html(query.get('module', [None])[0],
                            query.get('requirement', [None])[0], version)
                        self.respond_headers(200, 'text/html; charset=utf-8', len(data), policy)
                        return self.wfile.write(data)
                    if path == '/requirement-map-assets/requirement-map-live.js':
                        return self.send_file(Path(__file__).resolve().parents[1] /
                            'assets/conversation-ui/requirement-map-live.js')
                    if path in ('/', '/index.html'):
                        file = owner.assets / 'index.html'
                        if not file.is_file():
                            raise FlowError('工作台前端缺失，请先构建或使用完整 Skill 包', 503)
                        html = file.read_text('utf-8')
                        html = inject_session_token(html, owner.token)
                        data = html.encode('utf-8')
                        policy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; frame-src 'none'"
                        self.respond_headers(200, 'text/html; charset=utf-8', len(data), policy)
                        return self.wfile.write(data)
                    return self.send_file(safe_file(owner.assets, path.lstrip('/')))
                except Exception as exc:
                    self.failure(exc)

            def reject_write(self):
                try:
                    self.authenticate(mutation=True)
                    raise FlowError('工作台仅供浏览，请通过 Agent 使用本地 CLI 修改项目。', 405)
                except Exception as exc:
                    self.failure(exc)

            do_POST = reject_write
            do_PUT = reject_write
            do_PATCH = reject_write
            do_DELETE = reject_write

            def do_OPTIONS(self):
                self.json({'error': '不支持跨站接口请求'}, 403)

        return Handler


def ensure_workbench(project_root, reuse=True, port=0):
    """Discover or start one detached read-only service without opening a UI."""
    root = project_root.root if isinstance(project_root, ProjectStore) else project_root
    store = ProjectStore(root)
    store._project()
    registry = ServiceRegistry(store.root, 'workbench')
    with registry.lock():
        existing = registry.reuse() if reuse else None
        if existing:
            if port and urlsplit(existing['url']).port != port:
                raise FlowError('已有需求图服务使用其他端口；请停止它或省略显式端口', 409)
            return existing
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
            '--workbench-worker', str(store.root), '--port', str(port),
            '--registry-directory', str(registry.directory)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        try:
            if not select.select([process.stdout], [], [], 10)[0]:
                raise FlowError('本地需求图服务启动超时', 503)
            line = process.stdout.readline()
            try:
                result = json.loads(line)
            except ValueError:
                raise FlowError('本地需求图服务未返回有效启动结果', 503)
            if result.get('error'):
                raise FlowError(result['error'], result.get('status', 503))
            discovered = registry.reuse()
            if not discovered or discovered['pid'] != process.pid:
                raise FlowError('本地需求图服务身份校验失败', 503)
            _WORKBENCH_CHILDREN[process.pid] = process
            return dict(discovered, reused=False)
        except Exception:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise
        finally:
            process.stdout.close()


def stop_workbench(project_root, expected_instance_id=None):
    """Stop only the healthy registered workbench; leave Demo preview alone."""
    registry = ServiceRegistry(project_root, 'workbench')
    with registry.lock():
        service = registry.reuse()
        if not service:
            return False
        instance_id = registry._read().get('instanceId')
        if expected_instance_id is not None and instance_id != expected_instance_id:
            raise FlowError('需求图服务实例已变化，请重新连接后再重启', 409)
        os.kill(service['pid'], signal.SIGTERM)
    process = _WORKBENCH_CHILDREN.pop(service['pid'], None)
    if process:
        process.wait(timeout=5)
        return True
    event = threading.Event()
    for _ in range(100):
        if registry._read().get('instanceId') != instance_id:
            return True
        event.wait(0.05)
    raise FlowError('本地需求图服务尚未完成停止', 503)


def reconnect_service(project_root, service_kind='workbench'):
    """Inspect the existing authenticated service, without starting or stopping it."""
    root = project_root.root if isinstance(project_root, ProjectStore) else project_root
    registry = ServiceRegistry(root, service_kind)
    with registry.lock():
        service = registry.reuse()
    if not service:
        raise FlowError('没有可确认身份的本地服务，请先启动服务', 503,
                        {'code': 'service-not-running', 'serviceKind': service_kind})
    return dict(service, reconnected=True)


def restart_service(project_root, service_kind='workbench', port=0):
    """Explicitly replace only the discovered instance and preserve its old port."""
    root = project_root.root if isinstance(project_root, ProjectStore) else project_root
    registry = ServiceRegistry(root, service_kind)
    with registry.lock():
        service = registry.reuse()
        instance_id = registry._read().get('instanceId')
        if not service:
            raise FlowError('无法确认要重启的服务身份；未停止任何进程', 409,
                            {'code': 'service-identity-unavailable', 'serviceKind': service_kind})
        target_port = port or urlsplit(service['url']).port
    stop = stop_workbench if service_kind == 'workbench' else stop_preview
    start = ensure_workbench if service_kind == 'workbench' else preview
    if not stop(root, expected_instance_id=instance_id):
        raise FlowError('原服务在重启前已失去连接；未启动替代进程', 409,
                        {'code': 'service-identity-unavailable', 'serviceKind': service_kind})
    started = start(root, reuse=True, port=target_port)
    return dict(started, restarted=True, previousPid=service['pid'], previousUrl=service['url'])


def _workbench_worker(project_root, port, registry_directory):
    registry = ServiceRegistry(project_root, 'workbench', directory=registry_directory)
    server = None
    try:
        server = WorkbenchServer(ProjectStore(project_root), port)
        event = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: event.set())
        server.start()
        registry.publish(server)
        print(json.dumps(server.info(), ensure_ascii=False), flush=True)
        while not event.wait(1):
            pass
    except Exception as exc:
        print(json.dumps({'error': str(exc), 'status': error_status(exc)}, ensure_ascii=False), flush=True)
        return 1
    finally:
        if server:
            server.close()
            with registry.lock():
                registry.forget(server.instance_id)
    return 0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    worker = parser.add_mutually_exclusive_group(required=True)
    worker.add_argument('--preview-worker')
    worker.add_argument('--workbench-worker')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--registry-directory', required=True)
    arguments = parser.parse_args()
    run_worker = _preview_worker if arguments.preview_worker else _workbench_worker
    root = arguments.preview_worker or arguments.workbench_worker
    raise SystemExit(run_worker(root, arguments.port, arguments.registry_directory))
