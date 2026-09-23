"""Loopback-only workbench and an isolated read-only Demo origin."""
from __future__ import annotations

import copy
import contextlib
import fcntl
import hashlib
import http.client
import json
import mimetypes
import os
import re
import secrets
import stat
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from pf_core import FlowError, ProjectStore
from pf_export import module_package

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif'}
CONTENT_EXTENSIONS = IMAGE_EXTENSIONS | {'.pdf', '.txt', '.md', '.csv'}


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


class ServiceRegistry:
    """Private per-user discovery outside project data and project snapshots."""
    def __init__(self, project_root):
        self.project_root = str(Path(project_root).resolve())
        self.directory = Path(tempfile.gettempdir()) / ('prototype-flow-services-' + str(os.getuid()))
        key = hashlib.sha256(self.project_root.encode()).hexdigest()
        self.path = self.directory / (key + '.json')
        self.lock_path = self.directory / (key + '.lock')

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
            return json.loads(self.path.read_text('utf-8'))
        except (FileNotFoundError, ValueError):
            return {}

    def reuse(self):
        record = self._read()
        if record.get('projectRoot') != self.project_root:
            return None
        connection = None
        try:
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
                    or result.get('url') != record.get('url') or result.get('previewOrigin') != record.get('previewOrigin')
                    or result.get('protocolVersion') != 1):
                return None
            return {key: result[key] for key in ('url', 'previewOrigin', 'projectRoot', 'transport')} | {'reused': True}
        except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
            return None
        finally:
            if connection:
                connection.close()

    def publish(self, server):
        data = dict(server.info(), token=server.token, instanceId=server.instance_id)
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


def safe_file(root: Path, relative: str) -> Path:
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
    if not candidate.is_file():
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


class WorkbenchServer:
    def __init__(self, store: ProjectStore, port=0, preview_port=0, assets=None):
        self.store = store
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_urlsafe(24)
        self._integrity_cache = {}
        self._integrity_lock = threading.RLock()
        self.assets = Path(assets or Path(__file__).resolve().parents[1] / 'assets' / 'workbench')
        self.demo = FlowServer(('127.0.0.1', preview_port), self._demo_handler())
        self.preview_origin = 'http://127.0.0.1:%s' % self.demo.server_port
        try:
            self.http = FlowServer(('127.0.0.1', port), self._workbench_handler())
        except Exception:
            self.demo.server_close()
            raise
        self.origin = 'http://127.0.0.1:%s' % self.http.server_port
        self._threads = []

    def start(self):
        for server in (self.demo, self.http):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._threads.append(thread)
        return self.info()

    def info(self):
        return {'url': self.origin, 'previewOrigin': self.preview_origin,
                'projectRoot': str(self.store.root), 'transport': 'loopback_http', 'reused': False}

    def health(self):
        self.store._project()
        if not (self.assets / 'index.html').is_file() or not all(thread.is_alive() for thread in self._threads):
            raise FlowError('本地工作台服务尚未就绪', 503)
        return dict(self.info(), instanceId=self.instance_id, protocolVersion=1)

    def revision(self):
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
        return {'revisionToken': token,
                'projectRoot': str(self.store.root)}

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
        with self.store._transaction(read_only=True):
            root = self._checked_history(version)
            artifact = next((a for a in self.store._read('artifacts.json', {'items': []}, base=root)['items']
                             if a['id'] == artifact_id), None)
            if not artifact:
                raise FlowError('该版本没有这个 Demo', 404)
            artifact_root = self.store._safe(artifact['path'], base=root)
            if not artifact_root.is_dir():
                raise FlowError('Demo 文件与登记版本不一致，请登记新产物后查看', 409)
            expected = artifact.get('fileHashes', {})
            with self._integrity_lock:
                if artifact.get('kind') == 'working-draft' and not version:
                    # A live draft is an editable preview. Historical snapshots and
                    # frozen artifacts still require their registered byte hashes.
                    signature = metadata_signature(artifact_root)
                    key = ('live-draft', artifact_id, str(artifact_root))
                    cached = self._integrity_cache.get(key)
                    if not cached or cached[0] != signature:
                        hashes = self.store._inventory(artifact_root)
                        if signature != metadata_signature(artifact_root):
                            raise FlowError('工作稿在读取期间发生变化，请重试', 409)
                        cached = (signature, hashes)
                        self._integrity_cache[key] = cached
                    return dict(artifact, fileHashes=cached[1]), artifact_root
                signature = (metadata_signature(artifact_root), json.dumps(expected, sort_keys=True))
                key = ('artifact', version, artifact_id, str(artifact_root))
                if self._integrity_cache.get(key) != signature:
                    if self.store._inventory(artifact_root) != expected:
                        raise FlowError('Demo 文件与登记版本不一致，请登记新产物后查看', 409)
                    if signature[0] != metadata_signature(artifact_root):
                        raise FlowError('Demo 在检查期间发生变化，请重试', 409)
                    self._integrity_cache[key] = signature
            return artifact, artifact_root

    def close(self):
        for server in (self.http, self.demo):
            server.shutdown()
            server.server_close()
        for thread in self._threads:
            thread.join(timeout=3)

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
        return base + quote(parsed.path or entry, safe='/') + (
            '?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')

    def enriched_state(self, version=None):
        state = copy.deepcopy(self.store.state(version=version))
        state['previewOrigin'] = self.preview_origin
        state['historical'] = bool(version)
        state['selectedVersion'] = version
        artifacts = rows(state.get('artifacts'))
        by_id = {a['id']: a for a in artifacts}
        for artifact in artifacts:
            artifact['demoUrl'] = self.demo_url(artifact, version)
        relations = state.get('relations', {})
        for binding in rows(relations, 'bindings'):
            artifact = by_id.get(binding.get('artifactId'))
            if artifact:
                binding['demoUrl'] = self.demo_url(artifact, version, binding.get('route'))
            if binding.get('screenshot'):
                query = {'path': binding['screenshot']}
                if version:
                    query['version'] = version
                binding['screenshotUrl'] = '/content?' + urlencode(query)
        return state

    def demo_entry(self, version=None, binding_id=None, artifact_id=None):
        """Check a registered entry before embedding; never accept a client URL."""
        root = self._checked_history(version)
        binding = None
        if binding_id:
            relations = self.store._read('relations.json', {'bindings': []}, base=root)
            binding = next((b for b in relations['bindings'] if b['id'] == binding_id), None)
            if not binding:
                raise FlowError('该版本没有这个页面状态', 404)
            artifact_id = binding.get('artifactId')
        artifact, artifact_root = self._checked_artifact(artifact_id, version)
        url = self.demo_url(artifact, version, binding.get('route') if binding else None)
        if not url:
            raise FlowError('页面状态的演示入口无效', 400)
        relative = '/'.join(unquote(urlsplit(url).path).split('/')[4:])
        file = safe_file(artifact_root, relative)
        if file.suffix.lower() not in ('.html', '.htm'):
            raise FlowError('页面状态未指向 HTML 演示入口', 400)
        return {'url': url}

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

            def send_file(self, path, csp=None, expected=None):
                data = path.read_bytes()
                if expected is not None and hashlib.sha256(data).hexdigest() != expected:
                    raise FlowError('请求文件与登记版本不一致，请重新验证产物', 409)
                kind = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                if kind.startswith('text/') or kind == 'application/javascript':
                    kind += '; charset=utf-8'
                self.respond_headers(200, kind, len(data), csp)
                self.wfile.write(data)

        return Handler

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
                        if path == '/api/revision':
                            return self.json(owner.revision())
                        if path == '/api/health':
                            return self.json(owner.health())
                        if path == '/api/demo-entry':
                            return self.json(owner.demo_entry(version, query.get('binding', [None])[0], query.get('artifact', [None])[0]))
                        if path.startswith('/api/modules/') and path.endswith('/package'):
                            parts = path.split('/')
                            if len(parts) != 5:
                                raise FlowError('接口不存在', 404)
                            data, filename = module_package(owner.store, parts[3], version)
                            self.respond_headers(200, 'application/zip', len(data), filename=filename)
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
                        file = safe_file(root, query.get('path', [''])[0])
                        if file.suffix.lower() not in CONTENT_EXTENSIONS:
                            raise FlowError('该类型不作为工作台内容提供', 403)
                        return self.send_file(file, "sandbox; default-src 'none'; style-src 'unsafe-inline'")
                    if path in ('/', '/index.html'):
                        file = owner.assets / 'index.html'
                        if not file.is_file():
                            raise FlowError('工作台前端缺失，请先构建或使用完整 Skill 包', 503)
                        html = file.read_text('utf-8')
                        html = inject_session_token(html, owner.token)
                        data = html.encode('utf-8')
                        policy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; frame-src " + owner.preview_origin
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

    def _demo_handler(self):
        owner = self
        Base = self._base_handler()

        class Handler(Base):
            def do_GET(self):
                try:
                    self.check_host()
                    parts = unquote(urlsplit(self.path).path).split('/')
                    if len(parts) < 5 or parts[1] != 'demo':
                        raise FlowError('演示入口不存在', 404)
                    version = None if parts[2] == 'working' else parts[2]
                    artifact, artifact_root = owner._checked_artifact(parts[3], version)
                    relative = '/'.join(parts[4:]) or artifact.get('entryHtml', 'index.html')
                    # No workbench token/API is exposed on this origin.
                    policy = "default-src 'self' data: blob: https:; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; connect-src 'self' https:; object-src 'none'; frame-ancestors " + owner.origin
                    file = safe_file(artifact_root, relative)
                    expected = artifact.get('fileHashes', {}).get(file.relative_to(artifact_root).as_posix())
                    if not expected:
                        raise FlowError('该资源未登记在 Demo 中', 403)
                    return self.send_file(file, policy, expected)
                except Exception as exc:
                    self.failure(exc)

            def do_POST(self):
                self.json({'error': '演示服务只读'}, 405)

            do_PUT = do_POST
            do_DELETE = do_POST

        return Handler
