"""Local-authoritative Feishu publication. No network calls occur at import/prepare.

CLI calls use argv, documented JSON envelopes, explicit identities and pinned
remote revisions. Transport is injectable so tests never touch live accounts.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    from pf_core import FlowError
except ImportError:
    class FlowError(Exception):
        def __init__(self, message, status=400, details=None):
            super().__init__(message)
            self.status, self.details = status, details


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(value):
    if not isinstance(value, bytes):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _read(path, default=None):
    return json.loads(path.read_text("utf-8")) if path.exists() else copy.deepcopy(default)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(temporary, path)


def _inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise FlowError("路径超出当前项目")
    return path


@contextlib.contextmanager
def _lock(root):
    # Do not steal a lock on timeout: another publishing process may still run.
    path = root / ".prototype-flow" / "feishu.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise FlowError("另一个飞书任务正在运行；确认原进程结束后才能移除残留 feishu.lock", 409)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class TransportError(FlowError):
    def __init__(self, message, ambiguous=False, details=None):
        super().__init__(message, 502, details)
        self.ambiguous = ambiguous


class LarkCLITransport:
    """Version-matched lark-cli docs shortcuts; no auth/config mutation."""
    def __init__(self, identity="user", executable="lark-cli", timeout=90):
        if identity not in ("user", "bot"):
            raise FlowError("飞书身份必须为 user 或 bot")
        self.identity, self.executable, self.timeout = identity, executable, timeout

    def _call(self, args, cwd=None, content=None, write=False):
        env = dict(os.environ, LARKSUITE_CLI_NO_UPDATE_NOTIFIER="1", LARKSUITE_CLI_NO_SKILLS_NOTIFIER="1")
        argv = [self.executable] + args + ["--as", self.identity, "--format", "json"]
        try:
            result = subprocess.run(argv, input=content, text=True, cwd=cwd, env=env,
                                    capture_output=True, timeout=self.timeout, check=False)
        except FileNotFoundError:
            raise TransportError("未找到 lark-cli，请通过 use-feishu-cli 技能配置")
        except (subprocess.TimeoutExpired, OSError) as error:
            raise TransportError("飞书调用结果不明确：" + type(error).__name__, ambiguous=write)
        try:
            value = json.loads(result.stdout if result.returncode == 0 else result.stderr)
        except (ValueError, TypeError):
            # Do not copy raw output, which could contain authentication material.
            raise TransportError("飞书 CLI 未返回预期 JSON 信封", ambiguous=write)
        if result.returncode or value.get("ok") is not True:
            error = value.get("error", {})
            details = {key: error[key] for key in ("type", "subtype", "code", "missing_scopes") if key in error}
            raise TransportError("飞书 CLI 调用失败，请核对身份、权限和命令帮助", ambiguous=write and result.returncode != 10, details=details)
        data = value.get("data")
        if not isinstance(data, dict):
            raise TransportError("飞书 CLI 缺少 data", ambiguous=write)
        return data

    def fetch(self, remote):
        data = self._call(["docs", "+fetch", "--doc", remote, "--scope", "full", "--detail", "full", "--doc-format", "xml"])
        document = data.get("document", {})
        revision, doc_id = document.get("revision_id"), document.get("document_id")
        if not isinstance(revision, int) or not doc_id or not isinstance(document.get("content"), str):
            raise TransportError("飞书读取结果缺少文档 ID、修订或正文")
        exported = self._call(["docs", "+fetch", "--doc", doc_id, "--revision-id", str(revision), "--scope", "full", "--detail", "full", "--doc-format", "markdown"])
        markdown = exported.get("document", {}).get("content")
        if not isinstance(markdown, str):
            raise TransportError("飞书读取结果缺少 Markdown 正文")
        return {"id": doc_id, "revision": revision, "markdown": markdown,
                "xml": document["content"], "url": document.get("url") or (remote if remote.startswith("https://") else None)}

    def create(self, title, markdown, parent_token=None):
        args = ["docs", "+create", "--title", title, "--doc-format", "markdown", "--content", "-"]
        if parent_token:
            args += ["--parent-token", parent_token]
        result = self._call(args, content=markdown, write=True).get("document", {})
        if not result.get("document_id"):
            raise TransportError("飞书创建结果未提供文档 ID，不可自动重复创建", ambiguous=True)
        return {"id": result["document_id"], "url": result.get("url")}

    def overwrite(self, remote, markdown, revision, title=None):
        if title is not None:
            markdown = "<title>" + html.escape(title) + "</title>\n\n" + markdown
        return self._call(["docs", "+update", "--doc", remote, "--command", "overwrite", "--revision-id", str(revision), "--doc-format", "markdown", "--content", "-"], content=markdown, write=True)

    def append(self, remote, markdown, revision):
        return self._call(["docs", "+update", "--doc", remote, "--command", "append", "--revision-id", str(revision), "--doc-format", "markdown", "--content", "-"], content=markdown, write=True)

    def insert_image(self, remote, path, caption):
        path = Path(path)
        # --file paths are cwd-relative. Frozen image copies live in the plan.
        return self._call(["docs", "+media-insert", "--doc", remote, "--file", path.name,
                           "--type", "image", "--caption", caption], cwd=str(path.parent), write=True)


def _xml_nodes(xml):
    try:
        return list(ET.fromstring("<pf-root>" + xml + "</pf-root>").iter())
    except ET.ParseError:
        raise TransportError("飞书返回的 XML 不能完整解析；停止同步以保留内容")


def _remote_hash(remote):
    # Ignore transient URLs and block IDs while preserving structure, style,
    # resource tokens and text. Remote revisions are also checked separately.
    nodes = _xml_nodes(remote["xml"])
    parts = []
    for node in nodes:
        attrs = {k: v for k, v in node.attrib.items() if k not in ("id", "url")}
        parts.append([node.tag, attrs, node.text or "", node.tail or ""])
    return _hash(json.dumps(parts, ensure_ascii=False, sort_keys=True))


_IMAGE = re.compile(r'!\[([^\]\n]*)\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"\n]*")?\)')
_REQ = re.compile(r'<!--\s*pf:req\s+(\{.*?\})\s*-->\s*', re.S)


def _canonical(markdown, title):
    """Conservative exporter normalization, not a general Markdown renderer."""
    text = re.sub(r'<title\b[^>]*>.*?</title>', '', markdown, flags=re.S)
    text = _IMAGE.sub('', text)
    text = re.sub(r'<img\b[^>]*\/?>', '', text)
    lines = [line.rstrip() for line in text.replace('\r\n', '\n').splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip() == '# ' + title:
        lines.pop(0)
    # Exporters may use '*' for an unordered list. Preserve all other syntax,
    # including table separators/emphasis; mismatches require inspection.
    lines = [re.sub(r'^(\s*)\* ', r'\1- ', line) for line in lines]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _remote_images(remote):
    return [node for node in _xml_nodes(remote['xml']) if node.tag == 'img']


def _verify(remote, expected, title, assets):
    remote_titles = [''.join(n.itertext()).strip() for n in _xml_nodes(remote['xml']) if n.tag == 'title']
    if remote_titles and remote_titles[0] != title:
        return False
    if _canonical(remote['markdown'], title) != _canonical(expected, title):
        return False
    images = _remote_images(remote)
    if len(images) != len(assets):
        return False
    # All local images were individually inserted by this run and must retain
    # a concrete token. Existing uploads are tied to their frozen local hash.
    return all((n.get('token') or n.get('src')) and (not a.get('token') or a['token'] == (n.get('token') or n.get('src'))) for n, a in zip(images, assets))


class FeishuSync:
    def __init__(self, store, transport=None):
        self.store, self.root = store, Path(store.root).resolve()
        self.path = _inside(self.root, '.prototype-flow/feishu.json')
        self.transport = transport or LarkCLITransport()
        if not self.path.parent.exists():
            raise FlowError('请先初始化 prototype-flow 项目')

    def _ledger(self):
        result = _read(self.path, {})
        result.setdefault('schemaVersion', 1)
        result.setdefault('direction', 'local-to-feishu')
        for key in ('config', 'bindings', 'plans'):
            result.setdefault(key, {})
        return result

    def configure(self, parent_token=None, navigation_title=None):
        with _lock(self.root):
            ledger = self._ledger()
            if parent_token is not None:
                if not re.fullmatch(r'[A-Za-z0-9_-]+', parent_token):
                    raise FlowError('目标目录请提供飞书 folder 或 wiki 节点 token')
                ledger['config']['parentToken'] = parent_token
            if navigation_title is not None:
                ledger['config']['navigationTitle'] = navigation_title
            _write(self.path, ledger)
        return ledger

    def bind(self, document_id, remote, accept_existing=False):
        if document_id != '__navigation__':
            self.store.document(document_id)
        parsed = urlparse(remote)
        if parsed.scheme and (parsed.scheme != 'https' or not re.search(r'/(docx|wiki)/[A-Za-z0-9]+', parsed.path)):
            raise FlowError('请提供飞书 docx/wiki 链接或文档 token')
        if not parsed.scheme and not re.fullmatch(r'[A-Za-z0-9_-]+', remote):
            raise FlowError('飞书文档 token 无效')
        with _lock(self.root):
            ledger = self._ledger()
            old = ledger['bindings'].get(document_id)
            fetched = self.transport.fetch(remote)
            if old:
                if old['remoteId'] != fetched['id']:
                    raise FlowError('此 PRD 已绑定其他文档；先核对现有绑定，禁止静默改绑', 409)
                if not old.get('url') and fetched.get('url'):
                    old['url'] = fetched['url']
                    _write(self.path, ledger)
                return old  # Rebinding must never reset a drifted baseline.
            if not fetched.get('url'):
                raise FlowError('读取未返回分享链接；请提供文档完整 HTTPS 链接进行绑定，不推测租户地址')
            occupied = next((key for key, item in ledger['bindings'].items() if item['remoteId'] == fetched['id']), None)
            if occupied:
                raise FlowError('目标云文档已绑定其他本地文档：' + occupied, 409)
            has_body = bool(_canonical(fetched['markdown'], '')) or bool(_remote_images(fetched))
            if has_body and not accept_existing:
                raise FlowError('云端已有正文；仅在已授权使用该文档作为本地 PRD 展示副本后添加 --accept-existing', 409)
            binding = {'documentId': document_id, 'remoteId': fetched['id'], 'url': fetched['url'],
                       'baselineHash': _remote_hash(fetched), 'remoteRevision': fetched['revision'],
                       'status': 'pending', 'boundAt': _now()}
            ledger['bindings'][document_id] = binding
            # Reconcile an uncertain create only when the exact cloud doc has
            # been located and explicitly bound. No searching or recreation.
            _write(self.path, ledger)
            return binding

    def status(self):
        ledger = self._ledger()
        for doc_id, binding in ledger['bindings'].items():
            if doc_id == '__navigation__':
                continue
            try:
                doc = self.store.document(doc_id)
                if binding.get('status') == 'synced' and binding.get('localHash') != doc['fullHash']:
                    binding['status'] = 'pending'
            except (FlowError, KeyError):
                binding['status'] = 'local_missing'
        return ledger

    def _prepare_document(self, doc, plan_dir):
        content = doc['content']
        if content.startswith('---\n'):
            content = re.sub(r'^---\n.*?\n---\n', '', content, count=1, flags=re.S)
        content = re.sub(r'<!--\s*prdlib:related:start\s*-->.*?<!--\s*prdlib:related:end\s*-->', '', content, flags=re.S)
        requirement_ids = []
        def requirement(match):
            try:
                req_id = json.loads(match.group(1))['id']
            except (ValueError, KeyError):
                raise FlowError('需求块元数据无效')
            requirement_ids.append(req_id)
            return '\n\n' + req_id + '\n\n'
        content = _REQ.sub(requirement, content)
        content = re.sub(r'<!--\s*/pf:req\s*-->', '', content)
        # Add stable IDs to requirement headings so block IDs can be rebuilt.
        content = re.sub(r'(?m)^(REQ-[A-Za-z0-9_-]+)\s*\n+(#{1,6})\s+([^\n]+)', r'\2 \3 · \1', content)
        if re.search(r'<(?:[A-Za-z][\w:-]*)(?:\s|>|/)', re.sub(r'```.*?```', '', content, flags=re.S)):
            raise FlowError('PRD 含非标准 Markdown 嵌入内容；先人工确认飞书转换，不能静默降级')
        fence_spans = [m.span() for m in re.finditer(r'(?ms)^```[^\n]*\n.*?^```[^\n]*$', content)]
        image_matches = [m for m in _IMAGE.finditer(content) if not any(a <= m.start() < b for a, b in fence_spans)]
        image_spans = [match.span() for match in image_matches]
        # Local links are not remotely accessible. Generated related blocks were
        # stripped; authored local links must be replaced explicitly first.
        for link in re.finditer(r'(?<!!)\[[^\]]+\]\(([^\s)]+)\)', content):
            if any(a <= link.start() < b for a, b in image_spans):
                continue
            if not urlparse(link.group(1).strip('<>')).scheme:
                raise FlowError('云端不能访问本地链接，请先改为已绑定的飞书链接或说明：' + link.group(1))
        segments, assets, cursor = [], [], 0
        for index, match in enumerate(image_matches):
            # Inline/table/nested image placement cannot be preserved by the
            # append-based transport; fail before any remote modification.
            start = content.rfind('\n', 0, match.start()) + 1
            end = content.find('\n', match.end())
            if end == -1:
                end = len(content)
            if content[start:match.start()].strip() or content[match.end():end].strip():
                raise FlowError('飞书同步首版要求图片独占一行；行内或表格图片需先确认转换')
            target = unquote(match.group(2).strip('<>'))
            if urlparse(target).scheme:
                raise FlowError('同步图片需先保存为项目内本地资源，以固定版本并验证上传')
            source = _inside(self.root, str(Path(doc['path']).parent / target))
            if not source.is_file() or source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'):
                raise FlowError('图片不存在或格式不支持：' + target)
            digest = _hash(source.read_bytes())
            destination = plan_dir / 'images' / (digest + source.suffix.lower())
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists():
                shutil.copyfile(source, destination)
            before = content[cursor:match.start()].strip()
            if before:
                segments.append({'type': 'text', 'content': before})
            asset = {'path': str(destination.relative_to(plan_dir)), 'sha256': digest,
                     'alt': match.group(1), 'sourcePath': str(source.relative_to(self.root)), 'index': index}
            assets.append(asset)
            segments.append({'type': 'image', 'asset': asset})
            cursor = match.end()
        tail = content[cursor:].strip()
        if tail:
            segments.append({'type': 'text', 'content': tail})
        # Always start with a text operation. Empty text uses a readable short
        # title paragraph, never an invisible sync marker in the shared PRD.
        if not segments or segments[0]['type'] != 'text':
            segments.insert(0, {'type': 'text', 'content': doc['title']})
        # Avoid duplicating the document title in the cloud body.
        first = segments[0]['content']
        if first.splitlines()[0].strip() == '# ' + doc['title']:
            first = '\n'.join(first.splitlines()[1:]).strip()
            segments[0]['content'] = first or doc['title']
        if any(len(s.get('content', '')) > 60000 for s in segments):
            raise FlowError('单段文档超过 60000 字符，请按模块拆分后同步')
        return {'documentId': doc['id'], 'title': doc['title'], 'revision': doc['revision'],
                'localHash': doc['fullHash'], 'requirementIds': requirement_ids, 'segments': segments,
                'assets': assets, 'status': 'prepared', 'completedSteps': 0, 'expected': '', 'uploadedAssets': []}

    def prepare(self, document_ids=None, include_navigation=False):
        with _lock(self.root):
            ledger = self._ledger()
            state = self.store.state()
            ids = list(document_ids) if document_ids is not None else [d['id'] for d in state['documents']]
            if len(ids) != len(set(ids)):
                raise FlowError('同步文档 ID 重复')
            plan_id = 'SYNC-' + uuid.uuid4().hex[:12]
            plan_dir = self.path.parent / 'feishu-plans' / plan_id
            plan_dir.mkdir(parents=True)
            documents = [self._prepare_document(self.store.document(doc_id), plan_dir) for doc_id in ids]
            for document in documents:
                document['binding'] = copy.deepcopy(ledger['bindings'].get(document['documentId']))
            plan = {'schemaVersion': 1, 'id': plan_id, 'createdAt': _now(), 'inputRevision': state['project']['revision'],
                    'parentToken': ledger['config'].get('parentToken'), 'includeNavigation': include_navigation,
                    'navigationTitle': ledger['config'].get('navigationTitle', state['project']['name'] + ' · PRD 文档库'),
                    'navigationDocuments': [{'id': d['id'], 'title': d['title']} for d in state['documents']],
                    'documents': documents, 'status': 'prepared'}
            # The checksum covers fixed input; mutable progress is kept apart.
            plan['inputHash'] = _hash(json.dumps(self._input(plan), ensure_ascii=False, sort_keys=True))
            _write(plan_dir / 'plan.json', plan)
            ledger['plans'][plan_id] = {'id': plan_id, 'createdAt': plan['createdAt'], 'status': 'prepared',
                                       'documentIds': ids, 'path': str((plan_dir / 'plan.json').relative_to(self.root))}
            _write(self.path, ledger)
            return plan

    @staticmethod
    def _input(plan):
        return {'parentToken': plan['parentToken'], 'inputRevision': plan['inputRevision'],
                'includeNavigation': plan['includeNavigation'], 'navigationTitle': plan['navigationTitle'],
                'navigationDocuments': plan['navigationDocuments'],
                'documents': [{key: d[key] for key in ('documentId', 'title', 'revision', 'localHash', 'requirementIds', 'segments', 'assets', 'binding')} for d in plan['documents'] if not d.get('navigation')]}

    def _save(self, ledger, plan, directory):
        _write(directory / 'plan.json', plan)
        ledger['plans'][plan['id']]['status'] = plan['status']
        _write(self.path, ledger)

    def _reconcile_pending(self, item, remote):
        pending = item.get('pending')
        if not pending:
            return
        if _verify(remote, pending['expected'], item['title'], pending['assets']):
            item['expected'] = pending['expected']
            item['uploadedAssets'] = pending['assets']
            for asset, node in zip(item['uploadedAssets'], _remote_images(remote)):
                asset['token'] = node.get('token') or node.get('src')
            item['completedSteps'] += 1
            item['checkpointHash'] = _remote_hash(remote)
            item['checkpointRevision'] = remote['revision']
            item.pop('pending', None)
        elif _remote_hash(remote) == pending.get('beforeHash') and remote['revision'] == pending.get('beforeRevision'):
            item.pop('pending', None)  # Read proved the operation did not apply.
        else:
            raise FlowError('上次写入结果与写入前及预期内容均不一致；需检查云端后恢复', 409)

    def _sync_document(self, ledger, plan, item, directory):
        doc_id = item['documentId']
        binding = ledger['bindings'].get(doc_id)
        if item['status'] == 'synced':
            return
        if item.get('status') in ('creating', 'ambiguous_creation') and not binding:
            raise FlowError('上次创建结果不明确；先定位已创建文档并 bind，禁止自动重复创建', 409)
        if not binding:
            item['status'] = 'creating'
            self._save(ledger, plan, directory)
            try:
                created = self.transport.create(item['title'], item['segments'][0]['content'], plan.get('parentToken'))
            except TransportError as error:
                item['status'] = 'ambiguous_creation' if error.ambiguous else 'failed'
                raise
            binding = {'documentId': doc_id, 'remoteId': created['id'], 'url': created['url'], 'status': 'publishing', 'boundAt': _now()}
            ledger['bindings'][doc_id] = binding
            # Persist ID before readback. Never recreate on a later fetch failure.
            item['pending'] = {'expected': item['segments'][0]['content'], 'assets': [], 'beforeHash': None, 'beforeRevision': None}
            self._save(ledger, plan, directory)
        remote = self.transport.fetch(binding['remoteId'])
        if not binding.get('url'):
            binding['url'] = remote.get('url')
        if not binding.get('url'):
            raise FlowError('已保存云端文档 ID，但未取得分享链接；使用完整文档链接 bind 后继续同一计划', 409)
        if item.get('status') == 'ambiguous_creation' and binding:
            item['pending'] = {'expected': item['segments'][0]['content'], 'assets': [], 'beforeHash': None, 'beforeRevision': None}
        self._reconcile_pending(item, remote)
        if item.get('checkpointHash'):
            expected_hash, expected_revision = item['checkpointHash'], item['checkpointRevision']
        else:
            prepared_binding = item.get('binding')
            if prepared_binding and prepared_binding['remoteId'] != binding['remoteId']:
                raise FlowError('计划准备后文档绑定改变，请重新 prepare', 409)
            baseline = prepared_binding or binding
            expected_hash, expected_revision = baseline.get('baselineHash'), baseline.get('remoteRevision')
        if expected_hash is not None and (_remote_hash(remote) != expected_hash or remote['revision'] != expected_revision):
            raise FlowError('飞书正文或修订与同步基线不一致；暂停此文档，禁止覆盖意外变化', 409)
        while item['completedSteps'] < len(item['segments']):
            index = item['completedSteps']
            segment = item['segments'][index]
            expected = item['expected']
            assets = copy.deepcopy(item['uploadedAssets'])
            if segment['type'] == 'text':
                expected = segment['content'] if index == 0 else expected + '\n\n' + segment['content']
            else:
                assets.append(copy.deepcopy(segment['asset']))
                expected += '\n\n![' + segment['asset']['alt'] + '](pf-image:' + segment['asset']['sha256'] + ')'
            item['pending'] = {'expected': expected, 'assets': assets, 'beforeHash': _remote_hash(remote), 'beforeRevision': remote['revision']}
            item['status'] = 'publishing'
            self._save(ledger, plan, directory)
            failure = None
            try:
                if segment['type'] == 'text':
                    if index == 0:
                        self.transport.overwrite(binding['remoteId'], segment['content'], remote['revision'], title=item['title'])
                    else:
                        self.transport.append(binding['remoteId'], segment['content'], remote['revision'])
                else:
                    path = _inside(directory, segment['asset']['path'])
                    if _hash(path.read_bytes()) != segment['asset']['sha256']:
                        raise FlowError('固定图片副本发生变化，停止同步')
                    inserted = self.transport.insert_image(binding['remoteId'], path, segment['asset']['alt'])
                    if inserted.get('file_token'):
                        item['pending']['assets'][-1]['token'] = inserted['file_token']
                        self._save(ledger, plan, directory)
            except TransportError as error:
                failure = error
            # After every operation, including an ambiguous error, read before
            # deciding whether a retry is safe. No blind append/image retries.
            remote = self.transport.fetch(binding['remoteId'])
            self._reconcile_pending(item, remote)
            self._save(ledger, plan, directory)
            if item['completedSteps'] == index:
                raise failure or FlowError('云端读回不符合预期，未标记成功', 409)
        if not _verify(remote, item['expected'], item['title'], item['uploadedAssets']):
            raise FlowError('飞书最终读回校验未通过', 409)
        requirement_blocks = {}
        for node in _xml_nodes(remote['xml']):
            if node.get('id') and re.fullmatch(r'h[1-9]', node.tag):
                text = ''.join(node.itertext())
                for req_id in item['requirementIds']:
                    if re.search(r'(?<![\w-])' + re.escape(req_id) + r'(?![\w-])', text):
                        requirement_blocks[req_id] = {'blockId': node.get('id'), 'url': binding['url'] + '#' + node.get('id')}
        if set(item['requirementIds']) != set(requirement_blocks):
            raise FlowError('需求标题块映射不完整，未标记同步成功', 409)
        image_map = [{**asset, 'blockId': node.get('id'), 'token': node.get('token') or node.get('src')} for asset, node in zip(item['uploadedAssets'], _remote_images(remote))]
        binding.update({'status': 'synced', 'baselineHash': _remote_hash(remote), 'remoteRevision': remote['revision'],
                        'localRevision': item['revision'], 'localHash': item['localHash'], 'syncedAt': _now(),
                        'requirementBlocks': requirement_blocks, 'images': image_map})
        binding.pop('error', None)
        item['status'] = 'synced'
        item.pop('error', None)
        self._save(ledger, plan, directory)

    def sync(self, plan_id, allow_write=False):
        if not allow_write:
            raise FlowError('此命令会将计划中的本地 PRD 写入飞书；先查看固定计划，明确同步授权后使用 --execute', 403)
        if not re.fullmatch(r'SYNC-[0-9a-f]{12}', plan_id):
            raise FlowError('同步计划 ID 无效')
        with _lock(self.root):
            ledger = self._ledger()
            directory = _inside(self.root, str((self.path.parent / 'feishu-plans' / plan_id).relative_to(self.root)))
            plan = _read(directory / 'plan.json')
            if not plan:
                raise FlowError('未找到同步计划', 404)
            if plan['inputHash'] != _hash(json.dumps(self._input(plan), ensure_ascii=False, sort_keys=True)):
                # Older runtimes accidentally aliased image progress into fixed input.
                # Accept only that exact defect: the original checksum must still match.
                repaired = copy.deepcopy(plan)
                for item in repaired['documents']:
                    for asset in item.get('assets', []):
                        asset.pop('token', None)
                    for segment in item.get('segments', []):
                        if segment.get('type') == 'image':
                            segment['asset'].pop('token', None)
                if plan['inputHash'] != _hash(json.dumps(self._input(repaired), ensure_ascii=False, sort_keys=True)):
                    raise FlowError('同步计划固定输入发生变化；请重新 prepare', 409)
                plan = repaired
            for item in plan['documents']:
                for asset in item['assets']:
                    if _hash(_inside(directory, asset['path']).read_bytes()) != asset['sha256']:
                        raise FlowError('固定图片副本发生变化；请重新 prepare', 409)
            plan['status'] = 'running'
            self._save(ledger, plan, directory)
            for item in list(plan['documents']):
                try:
                    self._sync_document(ledger, plan, item, directory)
                except Exception as error:
                    if item['status'] == 'creating':
                        item['status'] = 'ambiguous_creation'
                    if item['status'] not in ('ambiguous_creation',):
                        item['status'] = 'conflict' if getattr(error, 'status', 0) == 409 else 'failed'
                    item['error'] = str(error)
                    binding = ledger['bindings'].get(item['documentId'])
                    if binding:
                        binding.update(status=item['status'], error=str(error))
                    self._save(ledger, plan, directory)
            if plan['includeNavigation'] and all(d['status'] == 'synced' for d in plan['documents'] if not d.get('navigation')):
                navigation = next((d for d in plan['documents'] if d.get('navigation')), None)
                if navigation is None:
                    # Fix directory content only once, after stable URLs exist.
                    links = []
                    for nav_doc in plan['navigationDocuments']:
                        title = nav_doc['title'].replace(']', '\\]')
                        nav_binding = ledger['bindings'].get(nav_doc['id'])
                        if nav_binding and nav_binding.get('url'):
                            links.append('- [' + title + '](' + nav_binding['url'] + ')' + ('（同步未完成）' if nav_binding.get('status') != 'synced' else ''))
                        else:
                            links.append('- ' + title + '（尚未同步）')
                    content = '\n'.join(links) or '此文档库尚无 PRD。'
                    navigation = {'documentId': '__navigation__', 'title': plan['navigationTitle'], 'revision': plan['inputRevision'],
                                  'localHash': _hash(content), 'requirementIds': [], 'segments': [{'type': 'text', 'content': content}],
                                  'assets': [], 'binding': copy.deepcopy(ledger['bindings'].get('__navigation__')),
                                  'navigation': True, 'status': 'prepared', 'completedSteps': 0, 'expected': '', 'uploadedAssets': []}
                    plan['documents'].append(navigation)
                    self._save(ledger, plan, directory)
                try:
                    self._sync_document(ledger, plan, navigation, directory)
                except Exception as error:
                    if navigation['status'] != 'ambiguous_creation':
                        navigation['status'] = 'conflict' if getattr(error, 'status', 0) == 409 else 'failed'
                    navigation['error'] = str(error)
            plan['status'] = 'synced' if all(d['status'] == 'synced' for d in plan['documents']) else 'partial'
            plan['finishedAt'] = _now()
            self._save(ledger, plan, directory)
            return {'planId': plan_id, 'status': plan['status'], 'results': [{k: d[k] for k in ('documentId', 'status', 'error') if k in d} for d in plan['documents']]}
