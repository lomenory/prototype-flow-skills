"""Prototype Flow project store. Python 3.9+, standard library only.

Markdown is authoritative. JSON indexes are derived; relations and immutable
snapshots preserve semantic and historical information separately.
"""
import contextlib
import copy
import datetime as dt
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import uuid
from urllib.parse import urlsplit, unquote


class FlowError(Exception):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status, self.details = status, details


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')


def digest(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def uid(prefix):
    return prefix + '-' + uuid.uuid4().hex[:12].upper()


GENERATED = re.compile(r'<!-- prdlib:related:start -->.*?<!-- prdlib:related:end -->', re.S)
REQ = re.compile(r'<!-- pf:req\s+(\{[^\n]*\})\s*-->\s*\n?(.*?)<!-- /pf:req -->', re.S)
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
MODULE_STAGES = ('intake', 'draft', 'review', 'demo', 'validation', 'confirmed')


def valid_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise FlowError('Invalid stable ID', details=value)
    return value


def split_frontmatter(content):
    """Read supported scalar/list fields without rewriting unknown YAML."""
    if not content.startswith('---\n'):
        return {}, '', content
    end = content.find('\n---', 4)
    if end < 0 or (end + 4 < len(content) and content[end + 4] != '\n'):
        raise FlowError('Invalid frontmatter closing delimiter')
    raw = content[4:end]
    meta = {}
    for line in raw.splitlines():
        match = re.match(r'^([A-Za-z][\w-]*):\s*(.*)$', line)
        if match:
            key, value = match.groups()
            try:
                meta[key] = json.loads(value)
            except (ValueError, TypeError):
                meta[key] = value.strip("'\"")
    return meta, raw, content[end + 4:].lstrip('\n')


def set_metadata(content, updates):
    _, raw, body = split_frontmatter(content)
    lines = raw.splitlines() if raw else []
    for key, value in updates.items():
        encoded = json.dumps(value, ensure_ascii=False)
        pattern = re.compile(r'^' + re.escape(key) + ':')
        matches = [i for i, line in enumerate(lines) if pattern.match(line)]
        if len(matches) > 1:
            raise FlowError('Duplicate metadata key: ' + key)
        if matches:
            lines[matches[0]] = key + ': ' + encoded
        else:
            lines.append(key + ': ' + encoded)
    return '---\n' + '\n'.join(lines) + '\n---\n\n' + body


def business_text(content):
    meta, raw, body = split_frontmatter(content)
    # Only known machine-maintained fields are omitted. Unknown YAML is retained
    # verbatim, including nested business metadata that our scalar parser ignores.
    ignored = {'updated', 'version', 'documentId', 'moduleId', 'related'}
    business_meta = []
    skip = False
    for line in raw.splitlines():
        match = re.match(r'^([A-Za-z][\w-]*):', line)
        if match:
            skip = match.group(1) in ignored
        if not skip:
            business_meta.append(line.rstrip())
    body = GENERATED.sub('', body)
    body = '\n'.join(line.rstrip() for line in body.splitlines()).strip()
    return '\n'.join(business_meta) + '\n' + re.sub(r'\n{3,}', '\n\n', body)


def markdown_links(content):
    """Return local or remote Markdown targets, excluding examples in code."""
    content = GENERATED.sub('', content)
    lines, fence = [], None
    for line in content.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        lines.append(line)
    content = '\n'.join(lines)
    content = re.sub(r'(`+)(?!`)(.*?)\1(?!`)', '', content, flags=re.S)
    targets = re.findall(r'!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)', content)
    targets += re.findall(r'^\s{0,3}\[[^\]\n]+\]:\s*(<[^>]+>|\S+)', content, re.M)
    return [target.strip('<>') for target in targets]


def parse_requirements(content, document_id, module_id):
    clean = GENERATED.sub('', content)
    spans, found = [], []
    for match in REQ.finditer(clean):
        try:
            data = json.loads(match.group(1))
        except ValueError as exc:
            raise FlowError('Invalid requirement metadata: ' + str(exc))
        rid = valid_id(data.get('id'))
        for field in ('sourceIds', 'dependsOn', 'supersedes'):
            values = data.setdefault(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise FlowError('Requirement ' + field + ' must be a list of IDs')
            for value in values:
                valid_id(value)
        body = match.group(2).strip()
        title = re.search(r'^#{1,6}\s+(.+)$', body, re.M)
        if not title:
            raise FlowError('Requirement needs a heading', details={'requirementId': rid})
        if '<!-- pf:req' in body:
            raise FlowError('Requirement blocks must not be nested')
        item = dict(data, documentId=document_id, moduleId=module_id,
                    title=title.group(1).strip(), content=body,
                    priority=data.get('priority', 'P1'), status=data.get('status', 'draft'),
                    anchor=rid, line=clean[:match.start()].count('\n') + 1)
        item['hash'] = digest(canonical({'metadata': data, 'body': body}))
        found.append(item)
        spans.append(match.span())
    residue = REQ.sub('', clean)
    if '<!-- pf:req' in residue or '<!-- /pf:req' in residue:
        raise FlowError('Malformed requirement boundary; no content was saved')
    ids = [item['id'] for item in found]
    if len(ids) != len(set(ids)):
        raise FlowError('Duplicate requirement IDs in document')
    return found


def requirement_block(data, body):
    return '<!-- pf:req ' + canonical(data) + ' -->\n' + body.strip() + '\n<!-- /pf:req -->\n'


def new_requirement_blocks(parts, module_id, source_ids=None, depends_on=None, supersedes=None):
    ids, blocks = [], []
    if not isinstance(parts, list):
        raise FlowError('Requirements must be a list')
    for part in parts:
        if (not isinstance(part, dict) or not isinstance(part.get('title'), str)
                or not part['title'].strip() or not isinstance(part.get('content', ''), str)):
            raise FlowError('Each new part requires title and content')
        rid = uid('REQ-' + module_id[:60])
        ids.append(rid)
        metadata = {'id': rid, 'priority': part.get('priority', 'P1'), 'status': 'draft',
                    'sourceIds': part.get('sourceIds', source_ids or []),
                    'dependsOn': part.get('dependsOn', depends_on or []), 'supersedes': supersedes or []}
        body = part.get('content', '').strip()
        if not re.match(r'^#{1,6}\s', body):
            body = '### ' + part['title'].strip() + '\n\n' + body
        blocks.append(requirement_block(metadata, body))
    return ids, blocks


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.meta = self.root / '.prototype-flow'
        self._lock = threading.RLock()
        self._depth = 0
        self._write_journals = []

    @contextlib.contextmanager
    def _rollback_writes(self):
        """Restore only files written by this operation if a later step fails."""
        journal = {}
        self._write_journals.append(journal)
        try:
            yield
        except Exception:
            self._write_journals.pop()
            for path, original in reversed(list(journal.items())):
                if original is None:
                    if path.exists():
                        path.unlink()
                else:
                    data, stat = original
                    self._write_bytes(path, data)
                    os.chmod(path, stat.st_mode)
                    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            raise
        else:
            self._write_journals.pop()

    @contextlib.contextmanager
    def _transaction(self, read_only=False):
        with self._lock:
            if not read_only:
                self.root.mkdir(parents=True, exist_ok=True)
                self.meta.mkdir(exist_ok=True)
            self._safe('.prototype-flow')
            outer = self._depth == 0
            handle = None
            if outer:
                lockpath = self._safe('.prototype-flow/store.lock')
                if not read_only or lockpath.exists():
                    handle = lockpath.open('rb' if read_only else 'a+b')
                    fcntl.flock(handle, fcntl.LOCK_SH if read_only else fcntl.LOCK_EX)
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if handle:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                    handle.close()

    def _safe(self, relative, base=None, must_exist=False):
        base = Path(base or self.root).resolve()
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise FlowError('Path must be relative and stay inside the project', 403)
        target = base / relative
        current = base
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise FlowError('Symbolic links are not permitted in managed paths', 403)
        try:
            target.resolve().relative_to(base)
        except ValueError:
            raise FlowError('Path escapes project', 403)
        if must_exist and not target.exists():
            raise FlowError('File does not exist: ' + relative.as_posix(), 404)
        return target

    def _read(self, name, default=None, base=None):
        path = self._safe('.prototype-flow/' + name, base=base)
        if not path.exists():
            return copy.deepcopy(default)
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise FlowError('Cannot read project data: ' + name, 500, str(exc))

    def _write_bytes(self, path, data):
        path = Path(path)
        # Validate again immediately before replacement, including parents.
        path = self._safe(path.relative_to(self.root))
        if path.is_file() and path.read_bytes() == data:
            return
        for journal in self._write_journals:
            if path not in journal:
                journal[path] = (path.read_bytes(), path.stat()) if path.is_file() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.pf-write-', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _write(self, name, value):
        self._write_bytes(self._safe('.prototype-flow/' + name),
                          (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())

    def _project(self, base=None):
        result = self._read('project.json', base=base)
        if not result:
            raise FlowError('Project is not initialized', 404)
        return result

    def _bump(self):
        project = self._project()
        project['revision'] += 1
        project['updatedAt'] = now()
        self._write('project.json', project)
        return project['revision']

    def _maintain(self):
        from pf_library import maintain
        try:
            result = maintain(self)
        except (OSError, FlowError, ValueError) as exc:
            result = {'status': 'pending', 'engine': 'builtin', 'message': str(exc)}
        self._write('maintenance.json', result)
        return result

    def init(self, name, mode='local', library_root='prd-library', maintainer_path=None, create_overview=True):
        if mode not in ('local', 'feishu'):
            raise FlowError('mode must be local or feishu')
        with self._transaction(), self._rollback_writes():
            if self._read('project.json'):
                return self.state()
            library = self._safe(library_root)
            if library == self.root or library.parts[len(self.root.parts)] in ('.prototype-flow', 'versions', 'demos', 'demo-framework'):
                raise FlowError('Library must be a dedicated project subdirectory')
            library.mkdir(parents=True, exist_ok=True)
            self._write('project.json', {'schemaVersion': 1, 'id': uid('PROJECT'), 'name': name,
                        'revision': 0, 'libraryRoot': library.relative_to(self.root).as_posix(),
                        'mode': mode, 'modules': [], 'maintainerPath': str(maintainer_path) if maintainer_path else None,
                        'createdAt': now(), 'updatedAt': now()})
            self._write('sources.json', {'schemaVersion': 1, 'items': []})
            self._write('relations.json', {'schemaVersion': 1, 'flows': [], 'bindings': [], 'supersessions': []})
            self._write('artifacts.json', {'schemaVersion': 1, 'items': [], 'currentArtifactId': None})
            # Legacy maintainer_path is accepted but never executed.
            for name_ in ('00-ai-context', '01-active', '03-research', '05-prototypes'):
                self._safe(library.relative_to(self.root) / name_).mkdir(parents=True, exist_ok=True)
            self._adopt_documents()
            if create_overview and not self._project()['modules']:
                self.add_module('项目总览', 'OVERVIEW')
            else:
                self._reindex()
                self._maintain()
            return self._state()

    def _adopt_documents(self):
        project = self._project()
        library = self._safe(project['libraryRoot'])
        known = {m['documentId']: m['documentPath'] for m in project['modules']}
        known_modules = {m['id'] for m in project['modules']}
        skipped = {'00-ai-context', 'templates', 'dashboard', '02-archive', '03-research', '04-decisions', '05-prototypes'}
        for path in sorted(library.rglob('*.md')):
            self._safe(path.relative_to(self.root))
            rel = path.relative_to(library)
            content = path.read_text(encoding='utf-8')
            meta, _, body = split_frontmatter(content)
            if not meta.get('documentId') and (any(p in skipped for p in rel.parts) or path.name in ('README.md', 'INDEX.md', 'CHANGELOG.md', 'AGENTS.md', 'CLAUDE.md')):
                continue
            document_id = valid_id(meta.get('documentId') or uid('DOC'))
            if document_id in known:
                if known[document_id] != path.relative_to(self.root).as_posix():
                    raise FlowError('Duplicate document identity in library', 409, {'documentId': document_id})
                continue
            module_id = valid_id(meta.get('moduleId') or uid('MODULE'))
            if module_id in known_modules:
                raise FlowError('Duplicate module identity in library', 409, {'moduleId': module_id})
            title_match = re.search(r'^#\s+(.+)', body, re.M)
            title = str(meta.get('title') or (title_match.group(1) if title_match else path.stem))
            content = set_metadata(content, {'documentId': document_id, 'moduleId': module_id, 'title': title})
            parse_requirements(content, document_id, module_id)
            self._write_bytes(path, content.encode())
            project['modules'].append({'id': module_id, 'title': title, 'documentId': document_id,
                                       'documentPath': path.relative_to(self.root).as_posix(), 'stage': 'draft'})
            known[document_id] = path.relative_to(self.root).as_posix()
            known_modules.add(module_id)
        self._write('project.json', project)

    def _scan(self, base=None):
        base = Path(base or self.root)
        project = self._project(base)
        documents, requirements, ids = [], [], set()
        for module in project['modules']:
            path = self._safe(module['documentPath'], base=base, must_exist=True)
            content = path.read_text(encoding='utf-8')
            meta, _, _ = split_frontmatter(content)
            if meta.get('documentId') != module['documentId'] or meta.get('moduleId') != module['id']:
                raise FlowError('Document identity changed outside an explicit operation', 409, {'path': module['documentPath']})
            reqs = parse_requirements(content, module['documentId'], module['id'])
            for req in reqs:
                if req['id'] in ids:
                    raise FlowError('Duplicate project requirement ID: ' + req['id'])
                ids.add(req['id'])
            requirements.extend(reqs)
            documents.append({'id': module['documentId'], 'path': module['documentPath'],
                              'title': str(meta.get('title', module['title'])), 'moduleId': module['id'],
                              'revision': digest(content), 'content': content,
                              'businessHash': digest(business_text(content)), 'fullHash': digest(content),
                              'readOnly': base != self.root})
        return documents, requirements

    def _check_requirement_lifecycle(self, before_ids, after_ids, relations, allow_removed=False):
        retired = {rid for change in relations.get('supersessions', []) for rid in change.get('from', [])}
        removed = set(before_ids) - set(after_ids) - retired
        if removed and not allow_removed:
            raise FlowError('External edit removed stable requirements without an explicit transformation', 409,
                            {'requirementIds': sorted(removed)})
        if set(after_ids) & retired:
            raise FlowError('Retired requirement IDs cannot be reused', 409,
                            {'requirementIds': sorted(set(after_ids) & retired)})

    @staticmethod
    def _step_bindings(step, bindings):
        """Resolve every supported page reference without duplicating flow metadata."""
        if not isinstance(step, dict):
            return []
        fields = ('artifactId', 'screenId', 'stateId')
        return [binding for binding in bindings if
                (step.get('bindingId') and step['bindingId'] == binding.get('id')) or
                (all(step.get(key) for key in fields) and
                 all(step[key] == binding.get(key) for key in fields))]

    def _step_requirements(self, step, bindings):
        if not isinstance(step, dict):
            return set()
        ids = {step['requirementId']} if step.get('requirementId') else set()
        for binding in self._step_bindings(step, bindings):
            ids.update(binding.get('requirementIds', []))
        return ids

    def _relation_requirements(self, relation, bindings):
        ids = set(relation.get('requirementIds', []))
        for step in relation.get('steps', []):
            ids.update(self._step_requirements(step, bindings))
        return ids

    def _index_changes(self):
        """Calculate the current view without writing indexes or confirmation history."""
        documents, requirements = self._scan()
        previous = self._read('requirement-index.json', {'items': [], 'documents': []})
        old_docs = {d['id']: d for d in previous.get('documents', [])}
        old_reqs = {r['id']: r for r in previous.get('items', [])}
        new_reqs = {r['id']: r for r in requirements}
        relations = self._read('relations.json', {'flows': [], 'bindings': [], 'supersessions': []})
        self._check_requirement_lifecycle(old_reqs, new_reqs, relations)
        project = self._project()
        changed_documents = (any(old_docs.get(d['id'], {}).get('fullHash') != d['fullHash']
                                 for d in documents) or len(documents) != len(old_docs))
        stored_revision = project['revision']
        if changed_documents:
            project.update(revision=stored_revision + 1, updatedAt=now())
        titles = {d['id']: d['title'] for d in documents}
        for module in project['modules']:
            module['title'] = titles[module['documentId']]
        changed = {rid for rid in set(old_reqs) | set(new_reqs)
                   if old_reqs.get(rid, {}).get('hash') != new_reqs.get(rid, {}).get('hash')}
        for document in documents:
            old = old_docs.get(document['id'])
            if old and old.get('businessHash') != document['businessHash']:
                # Shared text outside requirement blocks can affect every requirement.
                old_outside = old.get('outsideHash')
                outside = digest(REQ.sub('', business_text(document['content'])))
                if old_outside != outside:
                    changed.update(r['id'] for r in requirements if r['documentId'] == document['id'])
        impacted = set(changed)
        all_reqs = dict(old_reqs, **new_reqs)
        while True:
            before = set(impacted)
            for req in all_reqs.values():
                if set(req.get('dependsOn', [])) & impacted:
                    impacted.add(req['id'])
            for flow in relations.get('flows', []):
                references = self._relation_requirements(flow, relations.get('bindings', []))
                if references & impacted:
                    impacted.update(references)
            for binding in relations.get('bindings', []):
                if set(binding.get('requirementIds', [])) & impacted:
                    impacted.update(binding.get('requirementIds', []))
            if before == impacted:
                break
        affected_modules = {req['moduleId'] for req in all_reqs.values() if req['id'] in impacted}
        affected_modules.update(d['moduleId'] for d in documents if d['id'] in old_docs and
                                old_docs[d['id']].get('businessHash') != d['businessHash'])
        for module in project['modules']:
            # Invalidate only a prior confirmation. Preserve manually selected work
            # stages (draft/demo/validation) while their task is already in progress.
            if module.get('stage') == 'confirmed' and module['id'] in affected_modules:
                prior = copy.deepcopy(module.get('stageEvidence'))
                affected = sorted(req['id'] for req in all_reqs.values()
                                  if req['moduleId'] == module['id'] and req['id'] in impacted)
                evidence = {'type': 'change-impact', 'summary': '业务内容或已知依赖已变化，原确认需要复核。',
                            'requirementIds': affected, 'previousConfirmation': prior,
                            'inputRevision': project['revision']}
                timestamp = now()
                module.setdefault('stageHistory', []).append({'from': 'confirmed', 'to': 'review',
                    'changedAt': timestamp, 'reason': 'business-change', 'evidence': copy.deepcopy(evidence)})
                module.update(stage='review', stageEvidence=evidence, stageUpdatedAt=timestamp)
        prior_impact = self._read('impact.json', {'requirementIds': []})
        pending = self._pending_after_confirmation(project, documents, requirements,
            set(prior_impact.get('requirementIds', [])) | impacted)
        return {'project': project, 'documents': documents, 'requirements': requirements,
                'impactedRequirementIds': sorted(impacted), 'pendingRequirementIds': pending,
                'refreshRequired': changed_documents, 'storedRevision': stored_revision}

    @staticmethod
    def _pending_after_confirmation(project, documents, requirements, pending):
        """Close only inputs covered by a still-valid, explicit module confirmation.

        Also interpret older confirmation records on read, without mutating projects
        or historical snapshots just to remove an obsolete pending label.
        """
        pending = set(pending)
        docs = {d['id']: d for d in documents}
        for module in project['modules']:
            evidence = module.get('stageEvidence') or {}
            document = docs.get(module['documentId'], {})
            if (module.get('stage') != 'confirmed'
                    or evidence.get('type') != 'user-confirmation'
                    or not evidence.get('summary') or not evidence.get('source')
                    or not evidence.get('businessHash')
                    or evidence['businessHash'] != document.get('businessHash')):
                continue
            hashes = evidence.get('requirementHashes', {})
            pending.difference_update(r['id'] for r in requirements
                if r['moduleId'] == module['id'] and hashes.get(r['id']) == r['hash'])
        return sorted(pending)

    def _reindex(self):
        view = self._index_changes()
        documents, requirements = view['documents'], view['requirements']
        self._write('project.json', view['project'])
        prior = self._read('impact.json', {})
        if prior.get('requirementIds') != view['pendingRequirementIds']:
            self._write('impact.json', {'requirementIds': view['pendingRequirementIds'], 'updatedAt': now()})
        self._write('requirement-index.json', {'schemaVersion': 1, 'items': requirements,
                    'documents': [dict((k, v) for k, v in d.items() if k != 'content') |
                                  {'outsideHash': digest(REQ.sub('', business_text(d['content'])))} for d in documents]})
        return documents, requirements, view['impactedRequirementIds']

    def refresh(self):
        with self._transaction(), self._rollback_writes():
            self._adopt_documents()
            self._reindex()
            self._maintain()
            return self._state()

    def content_root(self, version=None):
        if version in (None, '', 'working'):
            return self.root
        valid_id(version)
        manifest = self._safe('versions/' + version + '/manifest.json', must_exist=True)
        if not manifest.is_file():
            raise FlowError('Unknown project version', 404)
        return self._safe('versions/' + version + '/project', must_exist=True)

    def state(self, version=None, summary=False):
        with self._transaction(read_only=True):
            view = None
            if not version or version == 'working':
                view = self._index_changes()
            else:
                self._verify_snapshot(version)
            result = self._summary(version, view) if summary else self._state(version, view)
            if view:
                result.update(refreshRequired=view['refreshRequired'], storedRevision=view['storedRevision'],
                              changedRequirementIds=view['impactedRequirementIds'])
            return result

    def _summary(self, version=None, view=None):
        """CLI lookup without repeating text or inspecting every Demo artifact."""
        base = self.content_root(version)
        project = view['project'] if view else self._project(base)
        index = ({'documents': view['documents'], 'items': view['requirements']} if view else
                 self._read('requirement-index.json', {'documents': [], 'items': []}, base=base))
        modules = [{key: module[key] for key in ('id', 'title', 'documentId', 'documentPath', 'stage')
                    if key in module} for module in project['modules']]
        documents = [{key: document[key] for key in ('id', 'title', 'moduleId', 'path', 'revision')}
                     for document in index['documents']]
        return {'project': {key: project[key] for key in ('id', 'name', 'revision', 'mode', 'libraryRoot')},
                'modules': modules, 'documents': documents,
                'counts': {'modules': len(modules), 'documents': len(documents),
                           'requirements': len(index['items']),
                           'sources': len(self._read('sources.json', {'items': []}, base=base)['items']),
                           'artifacts': len(self._read('artifacts.json', {'items': []}, base=base)['items'])},
                'maintenanceStatus': self._read('maintenance.json', {}, base=base),
                'frameworks': self._framework_summary(base),
                'historical': base != self.root, 'versionId': version if base != self.root else None}

    def _state(self, version=None, view=None):
        base = self.content_root(version)
        documents, requirements = (view['documents'], view['requirements']) if view else self._scan(base)
        artifacts = self._read('artifacts.json', {'items': []}, base=base)
        current_hashes = {r['id']: r['hash'] for r in requirements}
        current_documents = {d['id']: d['businessHash'] for d in documents}
        pending = set(view['pendingRequirementIds'] if view else
                      self._read('impact.json', {'requirementIds': []}, base=base).get('requirementIds', []))
        if view is None:
            pending = set(self._pending_after_confirmation(self._project(base), documents, requirements, pending))
        for artifact in artifacts['items']:
            artifact['staleRequirementIds'] = sorted(r for r, h in artifact.get('requirementHashes', {}).items() if current_hashes.get(r) != h)
            artifact['staleDocumentIds'] = sorted(d for d, h in artifact.get('documentHashes', {}).items() if current_documents.get(d) != h)
            artifact['syncStatus'] = 'stale' if artifact['staleRequirementIds'] or artifact['staleDocumentIds'] else 'current'
            artifact_path = self._safe(artifact['path'], base=base)
            artifact['integrityStatus'] = 'intact' if artifact_path.is_dir() and self._inventory(artifact_path) == artifact.get('fileHashes') else 'changed'
            if artifact['integrityStatus'] != 'intact':
                artifact['syncStatus'] = 'invalid'
        for req in requirements:
            req['analysisStatus'] = 'pending' if req['id'] in pending else 'current'
        runs_dir = base / '.prototype-flow/runs'
        runs = []
        if runs_dir.exists():
            for path in sorted(runs_dir.glob('*.json')):
                self._safe(path.relative_to(base), base=base)
                runs.append(json.loads(path.read_text(encoding='utf-8')))
        return {'project': view['project'] if view else self._project(base), 'documents': documents, 'requirements': requirements,
                'relations': self._evaluated_relations(base), 'artifacts': artifacts,
                'frameworks': self._frameworks(base),
                'sources': self._read('sources.json', {'items': []}, base=base),
                'versions': self.versions(), 'feishu': self._read('feishu.json', {}, base=base),
                'runs': runs, 'maintenanceStatus': self._read('maintenance.json', {}, base=base),
                'historical': base != self.root, 'versionId': version if base != self.root else None}

    def document(self, document_id, version=None):
        valid_id(document_id)
        with self._transaction(read_only=True):
            if version and version != 'working':
                self._verify_snapshot(version)
            for document in self._scan(self.content_root(version))[0]:
                if document['id'] == document_id:
                    return document
        raise FlowError('Unknown document: ' + document_id, 404)

    def _check_content(self, current, content, allow_removed=False):
        if not isinstance(content, str) or len(content.encode()) > 8 * 1024 * 1024:
            raise FlowError('Document must be UTF-8 text under 8 MiB')
        meta, _, _ = split_frontmatter(content)
        if meta.get('documentId') != current['id'] or meta.get('moduleId') != current['moduleId']:
            raise FlowError('Document and module identities must be preserved')
        next_reqs = parse_requirements(content, current['id'], current['moduleId'])
        before_ids = {r['id'] for r in parse_requirements(current['content'], current['id'], current['moduleId'])}
        after_ids = {r['id'] for r in next_reqs}
        self._check_requirement_lifecycle(before_ids, after_ids, self._read('relations.json', {}), allow_removed)
        other = {r['id'] for r in self._scan()[1] if r['documentId'] != current['id']}
        if other & after_ids and not allow_removed:
            raise FlowError('Requirement ID already exists in another document')

    def _save_revision(self, document):
        rel = 'revisions/' + document['id'] + '/' + document['revision'] + '.md'
        path = self._safe('.prototype-flow/' + rel)
        if not path.exists():
            self._write_bytes(path, document['content'].encode())

    def save_document(self, document_id, content, base_revision):
        with self._transaction(), self._rollback_writes():
            current = self.document(document_id)
            if base_revision != current['revision']:
                raise FlowError('The document changed after it was opened; your draft was not overwritten.', 409,
                                {'current': current, 'draft': content, 'baseRevision': base_revision})
            self._check_content(current, content)
            # A generated area is maintained separately. Reject editor changes there.
            if GENERATED.findall(current['content']) != GENERATED.findall(content):
                raise FlowError('Generated related-document blocks must be preserved', 409)
            self._save_revision(current)
            if digest(self._safe(current['path']).read_text(encoding='utf-8')) != current['revision']:
                raise FlowError('Document changed during save; retry with the latest document', 409,
                                {'draft': content, 'current': self.document(document_id)})
            self._write_bytes(self._safe(current['path']), content.encode())
            _, _, impacted = self._reindex()
            maintenance = self._maintain()
            saved = self.document(document_id)
            self._save_revision(saved)
            return {'document': saved, 'impactedRequirementIds': impacted, 'maintenanceStatus': maintenance}

    def add_module(self, title, module_id=None):
        if not isinstance(title, str) or not title.strip():
            raise FlowError('Module title is required')
        with self._transaction():
            project = self._project()
            module_id = valid_id(module_id or uid('MODULE'))
            if any(m['id'] == module_id for m in project['modules']):
                raise FlowError('Module already exists', 409)
            document_id = uid('DOC')
            relative = project['libraryRoot'] + '/01-active/' + module_id + '.md'
            if self._safe(relative).exists():
                raise FlowError('Module path already exists', 409)
            body = '# ' + title.strip() + '\n\n## 目标与范围\n\n待整理：目标用户、问题、范围与非目标。\n\n## 需求\n\n## 待确认事项\n\n尚未提供的业务规则应在此记录，不视为既定事实。\n'
            content = set_metadata(body, {'documentId': document_id, 'moduleId': module_id,
                        'title': title.strip(), 'status': 'draft', 'version': '0.1.0', 'updated': now()[:10]})
            self._write_bytes(self._safe(relative), content.encode())
            project['modules'].append({'id': module_id, 'title': title.strip(), 'documentId': document_id,
                                       'documentPath': relative, 'stage': 'draft'})
            self._write('project.json', project)
            self._reindex()
            self._maintain()
            document = self.document(document_id)
            self._save_revision(document)
            return document

    def add_source(self, label, kind, locator, content=None, source_id=None):
        with self._transaction(), self._rollback_writes():
            self._project()
            source_id = valid_id(source_id or uid('SRC'))
            sources = self._read('sources.json', {'schemaVersion': 1, 'items': []})
            if any(s['id'] == source_id for s in sources['items']):
                raise FlowError('Source ID already exists', 409)
            source = {'id': source_id, 'label': str(label), 'kind': str(kind), 'locator': str(locator),
                      'createdAt': now(), 'status': 'captured' if content is not None else 'unread'}
            if content is not None:
                relative = self._project()['libraryRoot'] + '/03-research/' + source_id + '.md'
                if self._safe(relative).exists():
                    raise FlowError('Source path already exists', 409)
                self._write_bytes(self._safe(relative), str(content).encode())
                source.update(path=relative, hash=digest(str(content)))
            sources['items'].append(source)
            self._write('sources.json', sources)
            self._bump()
            self._maintain()
            return source

    def intake(self, payload):
        """Create one complete PRD and its source/requirements with one maintenance pass."""
        if not isinstance(payload, dict):
            raise FlowError('Intake must be an object')
        unknown = set(payload) - {'title', 'content', 'moduleId', 'source', 'requirements'}
        if unknown:
            raise FlowError('Unknown intake fields', details=sorted(unknown))
        title, content = payload.get('title'), payload.get('content', '')
        if not isinstance(title, str) or not title.strip():
            raise FlowError('Module title is required')
        if not isinstance(content, str) or len(content.encode()) > 8 * 1024 * 1024:
            raise FlowError('Document must be UTF-8 text under 8 MiB')
        if '<!-- pf:req' in content or '<!-- /pf:req' in content or GENERATED.search(content):
            raise FlowError('Intake content is shared prose; put requirement blocks in requirements')
        with self._transaction(), self._rollback_writes():
            project = self._project()
            self._scan()  # Reject an inconsistent existing project before writing.
            module_id = valid_id(payload.get('moduleId') or uid('MODULE'))
            if any(module['id'] == module_id for module in project['modules']):
                raise FlowError('Module already exists; use document/save to update it', 409)
            document_id = uid('DOC')
            relative = project['libraryRoot'] + '/01-active/' + module_id + '.md'
            if self._safe(relative).exists():
                raise FlowError('Module path already exists', 409)
            sources = self._read('sources.json', {'schemaVersion': 1, 'items': []})
            source, source_content = None, None
            data = payload.get('source')
            if data is not None:
                if (not isinstance(data, dict) or set(data) - {'id', 'label', 'kind', 'locator', 'content'}
                        or any(not isinstance(data.get(key), str) or not data[key].strip()
                               for key in ('label', 'locator'))):
                    raise FlowError('Source requires label, locator and supported source fields')
                source_content = data.get('content')
                if source_content is not None and (not isinstance(source_content, str)
                        or len(source_content.encode()) > 8 * 1024 * 1024):
                    raise FlowError('Source content must be extracted UTF-8 text under 8 MiB')
                source_id = valid_id(data.get('id') or uid('SRC'))
                if any(item['id'] == source_id for item in sources['items']):
                    raise FlowError('Source ID already exists', 409)
                source = {'id': source_id, 'label': data['label'], 'kind': data.get('kind', 'document'),
                          'locator': data['locator'], 'createdAt': now(),
                          'status': 'captured' if source_content is not None else 'unread'}
                if source_content is not None:
                    source_path = project['libraryRoot'] + '/03-research/' + source_id + '.md'
                    if self._safe(source_path).exists():
                        raise FlowError('Source path already exists', 409)
                    source.update(path=source_path, hash=digest(source_content))
                sources['items'].append(source)
            requirement_ids, blocks = new_requirement_blocks(payload.get('requirements', []), module_id,
                                                              [source['id']] if source else [])
            _, raw, body = split_frontmatter(content)
            if not re.search(r'^#\s+', body, re.M):
                body = '# ' + title.strip() + '\n\n' + body
                content = '---\n' + raw + '\n---\n\n' + body if raw else body
            content = set_metadata(content, {'documentId': document_id, 'moduleId': module_id,
                                   'title': title.strip(), 'status': 'draft', 'version': '0.1.0', 'updated': now()[:10]})
            if blocks:
                content = content.rstrip() + '\n\n' + '\n\n'.join(blocks) + '\n'
            if len(content.encode()) > 8 * 1024 * 1024:
                raise FlowError('Document must be UTF-8 text under 8 MiB')
            parse_requirements(content, document_id, module_id)
            module = {'id': module_id, 'title': title.strip(), 'documentId': document_id,
                      'documentPath': relative, 'stage': 'draft'}
            project['modules'].append(module)
            writes = {self._safe(relative): content.encode(),
                      self._safe('.prototype-flow/project.json'): (json.dumps(project, ensure_ascii=False, indent=2) + '\n').encode()}
            if source:
                writes[self._safe('.prototype-flow/sources.json')] = (json.dumps(sources, ensure_ascii=False, indent=2) + '\n').encode()
                if source_content is not None:
                    writes[self._safe(source['path'])] = source_content.encode()
            for path, data in writes.items():
                self._write_bytes(path, data)
            self._reindex()
            maintenance = self._maintain()
            document = self.document(document_id)
            self._save_revision(document)
            validation = self.validate(stage='prd', document_ids={document_id})
            return {'document': document, 'module': module, 'requirementIds': requirement_ids,
                    'sourceId': source['id'] if source else None, 'maintenanceStatus': maintenance,
                    'validation': validation}

    def set_module_stage(self, module_id, stage, evidence=None):
        """Record workflow progress; user confirmation is explicit, never inferred."""
        valid_id(module_id)
        if stage not in MODULE_STAGES:
            raise FlowError('Unknown module stage', details={'allowedStages': list(MODULE_STAGES)})
        if evidence is not None and not isinstance(evidence, dict):
            raise FlowError('Stage evidence must be a JSON object')
        if stage == 'confirmed':
            if not evidence or evidence.get('type') != 'user-confirmation' or any(
                    not isinstance(evidence.get(key), str) or not evidence[key].strip()
                    for key in ('summary', 'source')):
                raise FlowError('Confirmed stage requires a user-confirmation record with summary and source',
                                details={'requiredEvidence': {'type': 'user-confirmation',
                                         'summary': '用户明确确认的内容', 'source': '对话或评审记录定位'}})
        with self._transaction():
            self._reindex()
            project = self._project()
            module = next((m for m in project['modules'] if m['id'] == module_id), None)
            if not module:
                raise FlowError('Unknown module: ' + module_id, 404)
            document = self.document(module['documentId'])
            requirements = [r for r in self._scan()[1] if r['moduleId'] == module_id]
            record = copy.deepcopy(evidence or {})
            record.update(inputRevision=project['revision'], documentRevision=document['revision'],
                          businessHash=document['businessHash'],
                          requirementHashes={r['id']: r['hash'] for r in requirements})
            timestamp = now()
            module.setdefault('stageHistory', []).append({'from': module.get('stage'), 'to': stage,
                'changedAt': timestamp, 'reason': 'explicit-update', 'evidence': copy.deepcopy(record)})
            module.update(stage=stage, stageEvidence=record, stageUpdatedAt=timestamp)
            project.update(revision=project['revision'] + 1, updatedAt=timestamp)
            self._write('project.json', project)
            self._reindex()
            self._maintain()
            return copy.deepcopy(module)

    def _flow_step_errors(self, relations, requirement_ids):
        """The same reference checks serve both writes and project validation."""
        bindings = {b['id']: b for b in relations.get('bindings', [])}
        errors = []
        for flow in relations.get('flows', []):
            steps = flow.get('steps', [])
            if not isinstance(steps, list):
                errors.append({'code': 'flow-steps-invalid', 'id': flow['id']})
                continue
            for index, step in enumerate(steps):
                problem = None
                if not isinstance(step, dict):
                    problem = 'flow-step-invalid'
                elif any(key in step and (not isinstance(step[key], str) or not step[key])
                         for key in ('bindingId', 'requirementId', 'artifactId', 'screenId', 'stateId')):
                    problem = 'flow-step-invalid'
                elif step.get('bindingId') and step['bindingId'] not in bindings:
                    problem = 'flow-step-binding-missing'
                elif step.get('requirementId') and step['requirementId'] not in requirement_ids:
                    problem = 'flow-step-requirement-missing'
                elif any(key in step for key in ('artifactId', 'screenId', 'stateId')) and not self._step_bindings(
                        {key: step[key] for key in ('artifactId', 'screenId', 'stateId') if key in step}, bindings.values()):
                    problem = 'flow-step-state-missing'
                elif not any(step.get(key) for key in ('bindingId', 'requirementId', 'stateId')):
                    problem = 'flow-step-target-missing'
                if problem:
                    errors.append({'code': problem, 'id': flow['id'], 'step': index})
        return errors

    def _binding_fingerprint(self, binding, base=None):
        base = base or self.root
        fields = ('artifactId', 'screenId', 'stateId', 'route', 'fixtureId', 'screenshot', 'requirementIds')
        value = {key: binding.get(key) for key in fields}
        artifact = next((a for a in self._read('artifacts.json', {'items': []}, base=base)['items']
                         if a['id'] == binding.get('artifactId')), None)
        if not artifact or not binding.get('screenshot'):
            return None
        path = self._safe(binding['screenshot'], base=base)
        if not path.is_file():
            return None
        value['screenshotHash'] = digest(path.read_bytes())
        value['artifactFiles'] = artifact.get('fileHashes')
        return digest(canonical(value))

    def _evaluated_relations(self, base=None):
        relations = self._read('relations.json', base=base)
        for binding in relations.get('bindings', []):
            if binding.get('verified'):
                reason = ('missing-fingerprint' if not binding.get('verificationHash') else
                          'fingerprint-changed' if binding['verificationHash'] != self._binding_fingerprint(binding, base) else None)
                if reason:
                    binding.update(verified=False, status='needs-review', verificationStatus=reason)
        return relations

    def update_relations(self, data):
        with self._transaction():
            if not isinstance(data, dict):
                raise FlowError('Relations must be an object')
            data = copy.deepcopy(data)
            data.setdefault('schemaVersion', 1)
            current = self._read('relations.json', {})
            for key in ('flows', 'bindings', 'supersessions'):
                data.setdefault(key, current.get(key, []))
                if not isinstance(data[key], list):
                    raise FlowError(key + ' must be a list')
            requirements = {r['id'] for r in self._scan()[1]}
            artifacts = {a['id'] for a in self._read('artifacts.json')['items']}
            previous_bindings = {b['id']: b for b in current.get('bindings', [])}
            for group in ('flows', 'bindings'):
                ids = set()
                for item in data[group]:
                    valid_id(item.get('id'))
                    if item['id'] in ids:
                        raise FlowError('Duplicate relation ID')
                    ids.add(item['id'])
                    references = item.get('requirementIds', [])
                    if not isinstance(references, list) or set(references) - requirements:
                        raise FlowError('Relation references unknown requirements', details=item)
                    if group == 'bindings':
                        if item.get('artifactId') not in artifacts:
                            raise FlowError('Binding references unknown artifact')
                        route = item.get('route', '')
                        self._validate_route(route)
                        if item.get('screenshot'):
                            self._safe(item['screenshot'])
                        if item.get('verified') and not item.get('evidence'):
                            raise FlowError('Verified binding requires actual evidence')
                        reverify = item.pop('reverify', False)
                        previous = previous_bindings.get(item['id'])
                        if item.get('verified'):
                            fingerprint = self._binding_fingerprint(item)
                            if not fingerprint:
                                raise FlowError('Verified binding requires an existing screenshot')
                            if previous and not reverify:
                                item['verificationHash'] = previous.get('verificationHash')
                                if item['verificationHash'] != fingerprint:
                                    reason = 'fingerprint-changed' if item['verificationHash'] else 'missing-fingerprint'
                                    item.update(verified=False, status='needs-review', verificationStatus=reason)
                            else:
                                item.update(verificationHash=fingerprint, verificationStatus='verified')
                                if item.get('status') == 'needs-review':
                                    item.pop('status')
            step_errors = self._flow_step_errors(data, requirements)
            if step_errors:
                raise FlowError('Invalid flow step references', details=step_errors)
            # Supersession history is append-only through explicit transformations.
            if data['supersessions'] != current.get('supersessions', []):
                raise FlowError('Supersession history is managed by requirement transformations')
            self._write('relations.json', data)
            self._bump()
            return data

    def _validate_route(self, route):
        if not isinstance(route, str):
            raise FlowError('Demo route must be a relative string')
        parsed = urlsplit(route)
        if parsed.scheme or parsed.netloc or route.startswith('/') or '\\' in route:
            raise FlowError('Demo route must be relative to its artifact')
        decoded = unquote(parsed.path)
        if '..' in Path(decoded).parts or decoded.startswith('/'):
            raise FlowError('Demo route escapes its artifact')

    def _inventory(self, directory):
        directory = Path(directory)
        if not directory.exists():
            return {}
        inventory = {}
        for path in sorted(directory.rglob('*')):
            self._safe(path.relative_to(self.root))
            if path.is_file():
                inventory[path.relative_to(directory).as_posix()] = digest(path.read_bytes())
        return inventory

    def register_artifact(self, data):
        with self._transaction(), self._rollback_writes():
            self._reindex()
            data = copy.deepcopy(data)
            artifact_id = valid_id(data.get('id') or uid('DEMO'))
            artifacts = self._read('artifacts.json')
            if any(a['id'] == artifact_id for a in artifacts['items']):
                raise FlowError('Artifact identity is immutable; register a new artifact', 409)
            path = self._safe(data.get('path', ''), must_exist=True)
            if not path.is_dir() or path.relative_to(self.root).parts[0] != 'demos':
                raise FlowError('Artifact must be a complete directory under demos/')
            entry = data.get('entryHtml', 'index.html')
            self._validate_route(entry)
            if '?' in entry or '#' in entry or not self._safe(entry, base=path, must_exist=True).is_file():
                raise FlowError('entryHtml must name an existing file')
            if data.get('runId'):
                run = self._read('runs/' + valid_id(data['runId']) + '.json')
                if not run:
                    raise FlowError('Unknown generation run')
                data['inputRevision'] = run['inputRevision']
                data['requirementHashes'] = run['requirementHashes']
                data['requirementIds'] = run['requirementIds']
                data['documentHashes'] = run.get('documentHashes', {d['id']: d['businessHash'] for d in run['documents']})
                data['inputDocuments'] = copy.deepcopy(run['documents'])
                data['inputPath'] = run.get('inputPath')
                data['inputFileHashes'] = run.get('inputFileHashes', {})
                if data['inputPath'] and self._inventory(self._safe(data['inputPath'])) != data['inputFileHashes']:
                    raise FlowError('Fixed generation input changed on disk', 409)
                self._bind_demo_framework(data, run, path)
            elif self._frameworks()['items'] or data.get('frameworkId'):
                raise FlowError('Framework-managed artifacts require a fixed demo run')
            if not isinstance(data.get('inputRevision'), int) or not isinstance(data.get('requirementHashes'), dict):
                raise FlowError('Artifact requires fixed inputRevision and requirementHashes, or runId')
            if not data['requirementHashes']:
                raise FlowError('Artifact must identify its requirement inputs')
            if data['inputRevision'] > self._project()['revision'] or data['inputRevision'] < 0:
                raise FlowError('Artifact input revision is not a project revision')
            if 'documentHashes' not in data:
                if data['inputRevision'] != self._project()['revision']:
                    raise FlowError('Older inputs need runId or explicit documentHashes')
                data['documentHashes'] = {d['id']: d['businessHash'] for d in self._scan()[0]}
                data['inputDocuments'] = [{'id': d['id'], 'revision': d['revision'], 'path': d['path'],
                                           'businessHash': d['businessHash']} for d in self._scan()[0]]
                for document in self._scan()[0]:
                    self._save_revision(document)
            if not isinstance(data['documentHashes'], dict):
                raise FlowError('documentHashes must be a mapping')
            for requirement_id, hash_ in data['requirementHashes'].items():
                valid_id(requirement_id)
                if not isinstance(hash_, str) or not re.fullmatch('[a-f0-9]{64}', hash_):
                    raise FlowError('Invalid fixed requirement hash')
            artifact = dict(data, id=artifact_id, path=path.relative_to(self.root).as_posix(), entryHtml=entry,
                            status=data.get('status', 'candidate'), createdAt=now(),
                            evidence=data.get('evidence', {}), fileHashes=self._inventory(path))
            if artifact['status'] in ('verified', 'current') and not artifact['evidence']:
                raise FlowError('Verified artifact requires verification evidence')
            artifacts['items'].append(artifact)
            if artifact['status'] in ('verified', 'current'):
                docs_now, reqs_now = self._scan()
                current = {r['id']: r['hash'] for r in reqs_now}
                current_docs = {d['id']: d['businessHash'] for d in docs_now}
                compatible = all(current.get(r) == h for r, h in artifact['requirementHashes'].items())
                compatible = compatible and all(current_docs.get(d) == h for d, h in artifact['documentHashes'].items())
                if compatible:
                    self._activate_demo_framework(artifact)
                    artifacts['currentArtifactId'] = artifact_id
                    resolved = set(artifact.get('requirementIds', artifact['requirementHashes']))
                    impact = self._read('impact.json', {'requirementIds': []})
                    impact['requirementIds'] = sorted(set(impact['requirementIds']) - resolved)
                    self._write('impact.json', impact)
            self._write('artifacts.json', artifacts)
            self._bump()
            return dict(artifact, activated=artifacts.get('currentArtifactId') == artifact_id)

    def _frameworks(self, base=None):
        return self._read('frameworks.json', {'schemaVersion': 1, 'items': [],
                                             'currentFrameworkId': None}, base=base)

    def _framework_summary(self, base=None):
        registry = self._frameworks(base)
        return {'currentFrameworkId': registry['currentFrameworkId'],
                'items': [{k: f[k] for k in ('id', 'title', 'path', 'basedOn', 'entryHtml', 'changeSummary')}
                          for f in registry['items']]}

    def register_framework(self, data):
        """Register immutable executable resources; activation happens with a verified Demo."""
        with self._transaction(), self._rollback_writes():
            self._project()
            if not isinstance(data, dict):
                raise FlowError('Framework must be an object')
            fid = valid_id(data.get('id'))
            registry = self._frameworks()
            if any(f['id'] == fid for f in registry['items']):
                raise FlowError('Framework identity is immutable; use a new ID and directory', 409)
            if 'basedOn' not in data or data['basedOn'] != registry['currentFrameworkId']:
                raise FlowError('Framework baseline changed; compare with the current framework', 409)
            if data.get('path') != 'demo-framework/' + fid:
                raise FlowError('Framework path must be demo-framework/<id>')
            directory = self._safe(data['path'], must_exist=True)
            if not directory.is_dir():
                raise FlowError('Framework must be a complete directory')
            entry = data.get('entryHtml', 'index.html')
            self._validate_route(entry)
            hashes = self._inventory(directory)
            if entry not in hashes or Path(entry).suffix.lower() != '.html' or 'DESIGN.md' not in hashes:
                raise FlowError('Framework requires DESIGN.md and an executable HTML entry')
            for field in ('title', 'changeSummary'):
                if not isinstance(data.get(field), str) or not data[field].strip():
                    raise FlowError('Framework requires ' + field)
            artifact_id = data.get('sourceArtifactId')
            if artifact_id:
                self._intact_artifact(artifact_id)
            record = {key: data[key] for key in ('id', 'title', 'path', 'basedOn', 'changeSummary')}
            record.update(entryHtml=entry, sourceArtifactId=artifact_id, fileHashes=hashes, createdAt=now())
            registry['items'].append(record)
            self._write('frameworks.json', registry)
            self._bump()
            return record

    def _intact_artifact(self, artifact_id):
        artifact = next((a for a in self._read('artifacts.json')['items'] if a['id'] == artifact_id), None)
        if not artifact:
            raise FlowError('Unknown baseline Demo', 404)
        path = self._safe(artifact['path'])
        if not path.is_dir() or self._inventory(path) != artifact['fileHashes']:
            raise FlowError('Baseline Demo changed on disk', 409)
        return artifact

    def _demo_inputs(self, framework_id=None, base_artifact_id=None, base_demo_path=None, base_entry='index.html'):
        registry = self._frameworks()
        framework_id = framework_id or registry['currentFrameworkId']
        # A sole first candidate is unambiguous; later candidates must be explicitly selected.
        if not framework_id and len(registry['items']) == 1:
            framework_id = registry['items'][0]['id']
        framework = next((f for f in registry['items'] if f['id'] == framework_id), None)
        if not framework:
            raise FlowError('Establish a Demo framework first; register it with framework --file and select --framework')
        if framework_id != registry['currentFrameworkId'] and framework['basedOn'] != registry['currentFrameworkId']:
            raise FlowError('Framework candidate is based on an older version; compare before continuing', 409)
        path = self._safe(framework['path'])
        if not path.is_dir() or self._inventory(path) != framework['fileHashes']:
            raise FlowError('Registered framework changed on disk', 409)
        artifacts = self._read('artifacts.json')
        current = artifacts['currentArtifactId']
        if base_demo_path:
            if base_artifact_id or artifacts['items']:
                raise FlowError('Use --base-artifact for registered Demos; raw import is only for first adoption')
            if len(Path(base_demo_path).parts) != 2 or Path(base_demo_path).parts[0] != 'demos':
                raise FlowError('Imported Demo must be a complete directory under demos/<name>')
            source = self._safe(base_demo_path, must_exist=True)
            self._validate_route(base_entry)
            hashes = self._inventory(source)
            if not source.is_dir() or base_entry not in hashes or Path(base_entry).suffix.lower() != '.html':
                raise FlowError('Imported Demo requires an existing HTML entry')
            baseline = {'id': None, 'path': base_demo_path, 'entryHtml': base_entry, 'fileHashes': hashes}
            return {'framework': copy.deepcopy(framework), 'baseArtifact': baseline,
                    'frameworkBaselineId': registry['currentFrameworkId'], 'artifactBaselineId': current}
        base_id = base_artifact_id or current
        if not base_id and len(artifacts['items']) == 1:
            base_id = artifacts['items'][0]['id']
        if not base_id and artifacts['items']:
            raise FlowError('No current Demo; select --base-artifact explicitly to preserve existing work')
        baseline = self._intact_artifact(base_id) if base_id else None
        return {'framework': copy.deepcopy(framework), 'baseArtifact': copy.deepcopy(baseline),
                'frameworkBaselineId': registry['currentFrameworkId'], 'artifactBaselineId': current}

    def prepare_demo(self, run_id, path, recovered_output=None):
        """Materialize a NEW work directory from the pinned business Demo and framework."""
        with self._transaction(), self._rollback_writes():
            run = self._read('runs/' + valid_id(run_id) + '.json')
            if not run or run['status'] != 'running' or not run.get('framework'):
                raise FlowError('Preparation requires a running task with a fixed framework')
            fixed = self._safe(run['inputPath'])
            if self._inventory(fixed) != run['inputFileHashes']:
                raise FlowError('Fixed generation input changed on disk', 409)
            target = self._safe(path)
            if len(Path(path).parts) != 2 or Path(path).parts[0] != 'demos':
                raise FlowError('Demo work path must be demos/<new-directory>')
            if target.exists():
                raise FlowError('Demo work directory already exists; preserve it and choose a new path', 409)
            framework = run['framework']
            recoverable = {item['path'] for item in run.get('recoveredOutputs', [])
                           if (self._safe(item['path']) / '_framework').is_dir()}
            if recovered_output is None and recoverable:
                if len(recoverable) != 1:
                    raise FlowError('Multiple recovered Demos; select --from-output', 409,
                                    {'paths': sorted(recoverable)})
                recovered_output = next(iter(recoverable))
            recovered = None
            if recovered_output is not None:
                if recovered_output not in recoverable:
                    raise FlowError('Select a recovered Demo directory from this run', 409)
                recovered = self._safe(recovered_output, must_exist=True)
                if (self._inventory(recovered / '_framework') != framework['fileHashes'] or
                        not (recovered / 'DESIGN.md').is_file() or
                        digest((recovered / 'DESIGN.md').read_bytes()) != framework['fileHashes']['DESIGN.md']):
                    raise FlowError('Recovered Demo differs from the fixed framework; preserve it and review the changes', 409)
            try:
                baseline = run.get('baseArtifact')
                if recovered:
                    self._copy_tree(recovered, target)
                elif baseline:
                    self._copy_tree(fixed / baseline['path'], target)
                    bundled = target / '_framework'
                    if bundled.exists():
                        if not baseline.get('frameworkId'):
                            raise FlowError('Unmanaged _framework directory conflicts with framework packaging')
                        shutil.rmtree(bundled)
                else:
                    target.mkdir(parents=True)
                if not recovered:
                    self._copy_tree(fixed / framework['path'], target / '_framework')
                    self._copy_file(fixed / framework['path'] / 'DESIGN.md', target / 'DESIGN.md')
                outputs = run.get('outputs') or {}
                if not isinstance(outputs, dict):
                    outputs = {'paths': outputs}
                outputs.setdefault('paths', []).append(path)
                run['outputs'] = outputs
                self._write('runs/' + run['id'] + '.json', run)
            except Exception:
                if target.exists():
                    shutil.rmtree(target)
                raise
            return {'runId': run_id, 'path': path, 'frameworkId': framework['id'],
                    'baseArtifactId': baseline['id'] if baseline else None,
                    'recoveredFrom': recovered_output,
                    'frameworkEntry': '_framework/' + framework['entryHtml']}

    def _framework_review_file(self, data, directory):
        evidence = data.get('evidence')
        review = evidence.get('frameworkReview') if isinstance(evidence, dict) else None
        if not isinstance(review, dict) or any(not isinstance(review.get(k), str) or not review[k].strip()
                                              for k in ('summary', 'source')):
            raise FlowError('Verified Demo requires evidence.frameworkReview with summary and source')
        source = self._safe(review['source'])
        if directory not in source.parents or not source.is_file():
            raise FlowError('frameworkReview.source must name an existing file inside this Demo, relative to the project')
        return source

    def _bind_demo_framework(self, data, run, directory):
        framework = run.get('framework')
        if not framework:
            if self._frameworks()['items'] or data.get('frameworkId'):
                raise FlowError('Legacy run has no framework; start a new demo run before registering')
            return  # Historical/import-only records remain readable and adoptable.
        if data.get('frameworkId', framework['id']) != framework['id']:
            raise FlowError('Artifact framework differs from its fixed input')
        if self._inventory(directory / '_framework') != framework['fileHashes']:
            raise FlowError('Demo must bundle the fixed framework unchanged in _framework/', 409)
        design = directory / 'DESIGN.md'
        if not design.is_file() or digest(design.read_bytes()) != framework['fileHashes']['DESIGN.md']:
            raise FlowError('Demo DESIGN.md must match the fixed framework', 409)
        if data.get('status') in ('verified', 'current'):
            self._framework_review_file(data, directory)
        data.update(frameworkId=framework['id'], frameworkPath='_framework',
                    frameworkBaselineId=run['frameworkBaselineId'], artifactBaselineId=run['artifactBaselineId'],
                    baseArtifactId=(run.get('baseArtifact') or {}).get('id'))
        baseline = run.get('baseArtifact') or {}
        if baseline and not baseline.get('id'):
            data['sourceDemoPath'] = baseline['path']
        # Unchanged pages retain their original business provenance, never claim the new PRD by copying.
        retired = {rid for item in self._read('relations.json')['supersessions'] for rid in item.get('from', [])}
        data['requirementHashes'] = {**{rid: h for rid, h in baseline.get('requirementHashes', {}).items()
                                     if rid not in retired}, **data['requirementHashes']}
        data['documentHashes'] = {**baseline.get('documentHashes', {}), **data['documentHashes']}

    def _activate_demo_framework(self, artifact):
        if not artifact.get('frameworkId'):
            return
        registry = self._frameworks()
        current_demo = self._read('artifacts.json')['currentArtifactId']
        if (registry['currentFrameworkId'] != artifact['frameworkBaselineId']
                or current_demo != artifact['artifactBaselineId']):
            raise FlowError('Current framework or Demo changed during this task; compare before publishing locally', 409)
        framework = next((f for f in registry['items'] if f['id'] == artifact['frameworkId']), None)
        if not framework or self._inventory(self._safe(framework['path'])) != framework['fileHashes']:
            raise FlowError('Framework is missing or changed; cannot activate', 409)
        registry['currentFrameworkId'] = framework['id']
        self._write('frameworks.json', registry)

    def transform_requirements(self, operation, ids, parts=None, target_module_id=None, base_revision=None, summary=False):
        with self._transaction(), self._rollback_writes():
            self._reindex()
            if base_revision is not None and base_revision != self._project()['revision']:
                raise FlowError('Project changed; reload before transforming requirements', 409)
            if operation not in ('add', 'split', 'merge', 'remove', 'move'):
                raise FlowError('Unknown requirement transformation')
            if not isinstance(ids, list) or (not ids and operation != 'add') or len(ids) != len(set(ids)):
                raise FlowError('Choose unique requirement IDs')
            documents, requirements = self._scan()
            by_req = {r['id']: r for r in requirements}
            if set(ids) - set(by_req):
                raise FlowError('Unknown requirement ID')
            if operation == 'split' and (len(ids) != 1 or not parts or len(parts) < 2):
                raise FlowError('Split requires one source and at least two parts')
            if operation == 'merge' and (len(ids) < 2 or not parts or len(parts) != 1):
                raise FlowError('Merge requires at least two sources and exactly one result')
            if operation == 'add' and (ids or not parts or not target_module_id):
                raise FlowError('Add requires no source IDs, new parts and a target module')
            modules = {m['id']: m for m in self._project()['modules']}
            target_module_id = target_module_id or by_req[ids[0]]['moduleId']
            if target_module_id not in modules:
                raise FlowError('Unknown target module')
            if operation == 'move' and target_module_id in {by_req[r]['moduleId'] for r in ids}:
                raise FlowError('Move target must differ from source module')
            docmap = {d['id']: d for d in documents}
            changes = {d['id']: d['content'] for d in documents}
            blocks = {}
            for d in documents:
                for match in REQ.finditer(d['content']):
                    rid = json.loads(match.group(1))['id']
                    if rid in ids:
                        blocks[rid] = match.group(0)
                changes[d['id']] = REQ.sub(lambda m: '' if json.loads(m.group(1))['id'] in ids else m.group(0), d['content'])
            new_ids = []
            additions = []
            if operation in ('add', 'split', 'merge'):
                new_ids, additions = new_requirement_blocks(parts, target_module_id,
                    sorted({source for rid in ids for source in by_req[rid]['sourceIds']}),
                    sorted({dependency for rid in ids for dependency in by_req[rid]['dependsOn']} - set(ids)), ids)
            elif operation == 'move':
                new_ids = list(ids)
                additions = [blocks[r] for r in ids]
            if additions:
                target_document = modules[target_module_id]['documentId']
                # Insert before the generated footer, keeping managed content intact.
                text_ = changes[target_document]
                position = text_.find('<!-- prdlib:related:start -->')
                if position < 0:
                    position = len(text_)
                changes[target_document] = text_[:position].rstrip() + '\n\n' + '\n\n'.join(additions) + '\n\n' + text_[position:]
            relations = self._read('relations.json')
            if operation not in ('move', 'add'):
                original_bindings = copy.deepcopy(relations['bindings'])
                relations['supersessions'].append({'id': uid('CHANGE'), 'operation': operation, 'from': ids, 'to': new_ids, 'createdAt': now(), 'status': 'needs-review'})
                for group in ('bindings', 'flows'):
                    for relation in relations[group]:
                        affected = self._relation_requirements(relation, original_bindings) & set(ids)
                        if affected:
                            relation['previousRequirementIds'] = sorted(set(relation.get('previousRequirementIds', [])) | affected)
                            relation['requirementIds'] = [r for r in relation.get('requirementIds', []) if r not in ids]
                            relation['candidateRequirementIds'] = new_ids
                            relation['status'] = 'needs-review'
                            if group == 'bindings':
                                relation['verified'] = False
                        if group == 'flows':
                            for step in relation.get('steps', []):
                                if self._step_requirements(step, original_bindings) & set(ids):
                                    step.update(status='needs-review', candidateRequirementIds=new_ids)
                                    relation['status'] = 'needs-review'
                # Dependencies retain the retired ID until their meaning is reviewed.
            # Validate the entire candidate set before the first file write.
            seen = set()
            for did, candidate in changes.items():
                self._check_content(docmap[did], candidate, allow_removed=True)
                for req in parse_requirements(candidate, did, docmap[did]['moduleId']):
                    if req['id'] in seen:
                        raise FlowError('Transformation creates duplicate requirements')
                    seen.add(req['id'])
            changed_docs = [d for d in documents if changes[d['id']] != d['content']]
            for document in changed_docs:
                self._save_revision(document)
                if digest(self._safe(document['path']).read_text(encoding='utf-8')) != document['revision']:
                    raise FlowError('Document changed during transformation; reload project', 409,
                                    {'documentId': document['id']})
            for document in changed_docs:
                self._write_bytes(self._safe(document['path']), changes[document['id']].encode())
            self._write('relations.json', relations)
            self._reindex()
            self._maintain()
            if summary:
                result = self._summary()
                result.update(operation=operation, newRequirementIds=new_ids,
                              removedRequirementIds=ids if operation in ('split', 'merge', 'remove') else [],
                              changedRequirementIds=sorted(set(ids + new_ids)))
                return result
            return self._state()

    def upload_asset(self, document_id, filename, data_bytes):
        document = self.document(document_id)
        if not isinstance(filename, str) or Path(filename).name != filename or '\\' in filename:
            raise FlowError('Asset filename must not contain a path')
        extension = Path(filename).suffix.lower()
        signatures = {'.png': lambda b: b.startswith(b'\x89PNG\r\n\x1a\n'),
                      '.jpg': lambda b: b.startswith(b'\xff\xd8\xff'), '.jpeg': lambda b: b.startswith(b'\xff\xd8\xff'),
                      '.gif': lambda b: b.startswith((b'GIF87a', b'GIF89a')),
                      '.webp': lambda b: b.startswith(b'RIFF') and b[8:12] == b'WEBP'}
        if not isinstance(data_bytes, bytes) or len(data_bytes) > 20 * 1024 * 1024:
            raise FlowError('Image must be bytes under 20 MiB')
        if extension not in signatures or not signatures[extension](data_bytes):
            raise FlowError('Only correctly identified PNG, JPEG, GIF and WebP images are accepted')
        with self._transaction():
            relative = self._project()['libraryRoot'] + '/05-prototypes/' + document_id + '/' + digest(data_bytes)[:24] + extension
            target = self._safe(relative)
            if not target.exists():
                self._write_bytes(target, data_bytes)
            return {'path': relative, 'markdownPath': os.path.relpath(target, self._safe(document['path']).parent).replace(os.sep, '/')}

    def start_run(self, stage, requirement_ids=None, shared_document_ids=None, full_context=False,
                  framework_id=None, base_artifact_id=None, base_demo_path=None, base_entry='index.html'):
        with self._transaction(), self._rollback_writes():
            demo_inputs = self._demo_inputs(framework_id, base_artifact_id, base_demo_path, base_entry) if stage == 'demo' else {}
            if stage != 'demo' and (framework_id or base_artifact_id or base_demo_path):
                raise FlowError('Framework and baseline selection require stage demo')
            self._reindex()
            documents, requirements = self._scan()
            hashes = {r['id']: r['hash'] for r in requirements}
            selected = list(hashes) if requirement_ids is None else requirement_ids
            if not isinstance(selected, list) or set(selected) - set(hashes):
                raise FlowError('Run references unknown requirements')
            shared_document_ids = shared_document_ids or []
            if set(shared_document_ids) - {d['id'] for d in documents}:
                raise FlowError('Run references unknown shared documents')
            relations = self._read('relations.json')
            inputs = set(selected)
            while True:
                previous = set(inputs)
                for req in requirements:
                    if req['id'] in inputs:
                        inputs.update(req.get('dependsOn', []))
                for relation in relations.get('flows', []) + relations.get('bindings', []):
                    refs = self._relation_requirements(relation, relations.get('bindings', []))
                    if inputs & refs:
                        inputs.update(refs)
                if previous == inputs:
                    break
            if inputs - set(hashes):
                raise FlowError('Resolve missing requirement dependencies before starting a run',
                                details=sorted(inputs - set(hashes)))
            document_ids = set(shared_document_ids) | {r['documentId'] for r in requirements if r['id'] in inputs}
            input_documents = [d for d in documents if full_context or d['id'] in document_ids]
            sources = self._read('sources.json')
            input_relations = copy.deepcopy(relations)
            if not full_context:
                source_ids = {sid for req in requirements if req['documentId'] in document_ids
                              for sid in req.get('sourceIds', [])}
                sources['items'] = [s for s in sources['items'] if s['id'] in source_ids]
                binding_ids = {b['id'] for b in relations.get('bindings', [])
                               if inputs.intersection(b.get('requirementIds', []))}
                input_relations['flows'] = [flow for flow in relations.get('flows', [])
                    if inputs.intersection(self._relation_requirements(flow, relations.get('bindings', [])))]
                binding_ids.update(binding['id'] for flow in input_relations['flows']
                                   for step in flow.get('steps', [])
                                   for binding in self._step_bindings(step, relations.get('bindings', [])))
                input_relations['bindings'] = [b for b in relations.get('bindings', []) if b['id'] in binding_ids]
                input_relations['supersessions'] = [item for item in relations.get('supersessions', [])
                    if inputs.intersection(item.get('from', []) + item.get('to', []))]
            run = {'id': uid('RUN'), 'stage': str(stage), 'status': 'running', 'createdAt': now(),
                   'inputRevision': self._project()['revision'], 'requirementIds': selected,
                   'contextScope': 'full' if full_context else 'selected',
                   'requirementHashes': {r: hashes[r] for r in sorted(inputs)},
                   'documentHashes': {d['id']: d['businessHash'] for d in documents if d['id'] in document_ids},
                   'sharedDocumentIds': shared_document_ids,
                   'documentIndex': [{key: d[key] for key in ('id', 'title', 'moduleId', 'path', 'revision')}
                                     for d in documents],
                   'documents': [{'id': d['id'], 'revision': d['revision'], 'path': d['path'],
                                  'businessHash': d['businessHash']} for d in input_documents],
                   'relations': input_relations, 'sources': sources, 'outputs': []}
            run['inputPath'] = '.prototype-flow/run-inputs/' + run['id']
            run.update(demo_inputs)
            fixed = self._safe(run['inputPath'])
            fixed.mkdir(parents=True)
            try:
                for document in input_documents:
                    self._save_revision(document)
                    self._copy_file(self._safe(document['path']), fixed / document['path'])
                for relative in self._referenced_files(input_documents, sources, input_relations):
                    source = self._safe(relative)
                    if source.is_file():
                        self._copy_file(source, fixed / relative)
                for resource in (demo_inputs.get('framework'), demo_inputs.get('baseArtifact')):
                    if resource:
                        self._snapshot_directory(resource['path'], fixed, resource['fileHashes'], False, [])
                # Framework DESIGN.md is authoritative, including when nested in an imported Demo.
                design = fixed / demo_inputs['framework']['path'] / 'DESIGN.md' if demo_inputs else self._safe('DESIGN.md')
                if design.is_file():
                    self._copy_file(design, fixed / 'DESIGN.md')
                run['inputFileHashes'] = self._inventory(fixed)
                self._write('runs/' + run['id'] + '.json', run)
            except Exception:
                shutil.rmtree(fixed)
                raise
            return run

    def finish_run(self, run_id, status, outputs=None, error=None):
        valid_id(run_id)
        if status not in ('completed', 'failed', 'partial', 'cancelled', 'blocked'):
            raise FlowError('Unsupported run completion status')
        with self._transaction():
            run = self._read('runs/' + run_id + '.json')
            if not run:
                raise FlowError('Unknown run', 404)
            if run['status'] != 'running':
                raise FlowError('Run is already finished', 409)
            recorded_outputs = run.get('outputs', []) if outputs is None else outputs
            self._run_output_paths({'outputs': recorded_outputs})
            run.update(status=status, outputs=recorded_outputs, error=error, finishedAt=now())
            self._write('runs/' + run_id + '.json', run)
            return run

    def _run_output_paths(self, run):
        outputs = run.get('outputs', [])
        artifact_ids = {a['id'] for a in self._read('artifacts.json', {'items': []})['items']}
        paths = outputs.get('paths', []) if isinstance(outputs, dict) else outputs
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise FlowError('Run output paths must be a list of project-relative paths')
        result = []
        for path in paths:
            if path in artifact_ids:
                continue  # Legacy output lists contained artifact IDs.
            target = self._safe(path)
            relative = target.relative_to(self.root)
            if relative.parts[0] == 'versions' or (relative.parts[0] == '.prototype-flow'
                    and relative.parts[1:2] != ('run-work',)):
                raise FlowError('Run outputs cannot include project metadata or history')
            result.append(relative.as_posix())
        return result

    def resume_run(self, run_id, version=None):
        """Fork a task from fixed inputs, never overwrite a live or historical run."""
        valid_id(run_id)
        with self._transaction():
            base = self._verify_snapshot(version)[0] if version and version != 'working' else self.root
            original = self._read('runs/' + run_id + '.json', base=base)
            if not original:
                raise FlowError('Run is not available in this version', 404)
            source = self._safe(original['inputPath'], base=base, must_exist=True)
            if self._inventory(source) != original.get('inputFileHashes', {}):
                raise FlowError('Fixed run input changed; cannot resume', 409)
            run = copy.deepcopy(original)
            run.update(id=uid('RUN'), status='running', createdAt=now(), outputs=[],
                       resumedFrom={'runId': run_id, 'versionId': version or 'working'})
            for key in ('finishedAt', 'error', 'snapshotOutputs', 'recoveredOutputs'):
                run.pop(key, None)
            run['inputPath'] = '.prototype-flow/run-inputs/' + run['id']
            self._copy_tree(source, self._safe(run['inputPath']))
            recovered = []
            saved_outputs = original.get('snapshotOutputs', []) if base != self.root else [
                {'sourcePath': p, 'snapshotPath': p} for p in self._run_output_paths(original)]
            for output in saved_outputs:
                source = self._safe(output['snapshotPath'], base=base, must_exist=True)
                relative = '.prototype-flow/run-work/' + run['id'] + '/' + output['sourcePath']
                target = self._safe(relative)
                if source.is_dir():
                    self._copy_tree(source, target)
                else:
                    self._copy_file(source, target)
                recovered.append({'sourcePath': output['sourcePath'], 'path': relative})
            run['recoveredOutputs'] = recovered
            run['outputs'] = {'paths': [item['path'] for item in recovered]}
            self._write('runs/' + run['id'] + '.json', run)
            return run

    def versions(self):
        directory = self._safe('versions')
        if not directory.exists():
            return []
        versions = []
        for path in directory.glob('*/manifest.json'):
            self._safe(path.relative_to(self.root))
            data = json.loads(path.read_text(encoding='utf-8'))
            versions.append({k: v for k, v in data.items() if k != 'files'})
        return sorted(versions, key=lambda v: v['createdAt'], reverse=True)

    def snapshot(self, name, description='', recovery=False):
        if not isinstance(name, str) or not name.strip():
            raise FlowError('Version name is required')
        with self._transaction():
            self._reindex()
            project = self._project()
            version_id = uid('V')
            destination = self._safe('versions/' + version_id)
            destination.mkdir(parents=True)
            stage = destination / 'project'
            stage.mkdir()
            issues = []
            try:
                library = self._safe(project['libraryRoot'])
                library_hashes = self._inventory(library)
                document_hashes = {d['path']: d['fullHash'] for d in self._scan()[0]}
                self._copy_tree(library, stage / project['libraryRoot'])
                for framework in self._frameworks()['items']:
                    self._snapshot_directory(framework['path'], stage, framework['fileHashes'], recovery, issues)
                for artifact in self._read('artifacts.json')['items']:
                    self._snapshot_directory(artifact['path'], stage, artifact['fileHashes'], recovery, issues)
                    if artifact.get('inputPath'):
                        self._snapshot_directory(artifact['inputPath'], stage,
                                                 artifact.get('inputFileHashes', {}), recovery, issues)
                    for document in artifact.get('inputDocuments', []):
                        revision_path = '.prototype-flow/revisions/' + valid_id(document['id']) + '/' + document['revision'] + '.md'
                        source = self._safe(revision_path)
                        if source.is_file():
                            self._copy_file(source, stage / revision_path)
                for path in sorted(self._safe('.prototype-flow/runs').glob('*.json')):
                    run = self._read('runs/' + path.name)
                    valid_id(run['id'])
                    self._snapshot_directory(run['inputPath'], stage, run.get('inputFileHashes', {}), recovery, issues)
                    run['snapshotOutputs'] = []
                    for relative in self._run_output_paths(run):
                        source = self._safe(relative)
                        captured = '.prototype-flow/run-outputs/' + run['id'] + '/' + relative
                        target = stage / captured
                        if source.is_dir():
                            hashes = self._inventory(source)
                            self._copy_tree(source, target)
                            if self._inventory(target) != hashes or self._inventory(source) != hashes:
                                raise FlowError('Run output changed during snapshot', 409)
                        elif source.is_file():
                            expected = digest(source.read_bytes())
                            self._copy_file(source, target)
                            if digest(target.read_bytes()) != expected or digest(source.read_bytes()) != expected:
                                raise FlowError('Run output changed during snapshot', 409)
                        else:
                            issues.append({'code': 'run-output-missing', 'runId': run['id'], 'path': relative})
                            continue
                        run['snapshotOutputs'].append({'sourcePath': relative, 'snapshotPath': captured})
                    self._write_bytes(stage / '.prototype-flow/runs' / path.name, (canonical(run) + '\n').encode())
                for relative in self._referenced_files():
                    origin = self._safe(relative)
                    if origin.is_file():
                        self._copy_file(origin, stage / relative)
                meta_names = ('project.json', 'sources.json', 'requirement-index.json', 'relations.json',
                              'artifacts.json', 'frameworks.json', 'impact.json', 'maintenance.json')
                for filename in meta_names:
                    origin = self._safe('.prototype-flow/' + filename)
                    if origin.exists():
                        target = stage / '.prototype-flow' / filename
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(origin, target)
                # Capture presentation status only. Live bindings/baselines never enter snapshots.
                feishu = self._read('feishu.json', {})
                if feishu:
                    summary = {'snapshotOnly': True, 'capturedAt': now(), 'direction': 'local-to-feishu',
                               'bindings': {did: {key: value for key, value in binding.items()
                                                  if key in ('url', 'localRevision', 'status', 'syncedAt')}
                                            for did, binding in feishu.get('bindings', {}).items()}}
                    self._write_bytes(stage / '.prototype-flow/feishu.json', (canonical(summary) + '\n').encode())
                evidence = self.validate()
                evidence['warnings'].extend(issues)
                if self._inventory(library) != library_hashes or self._inventory(stage / project['libraryRoot']) != library_hashes:
                    raise FlowError('Library changed during snapshot; retry with current files', 409)
                for relative, expected_hash in document_hashes.items():
                    if digest((stage / relative).read_text(encoding='utf-8')) != expected_hash:
                        raise FlowError('PRD changed during snapshot; retry with current files', 409)
                inventory = self._inventory(stage)
                manifest = {'schemaVersion': 1, 'id': version_id, 'name': name.strip(), 'description': description,
                            'createdAt': now(), 'inputRevision': project['revision'],
                            'modules': project['modules'], 'validation': evidence, 'files': inventory,
                            'recoveryBackup': recovery}
                self._write_bytes(destination / 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
                return manifest
            except Exception:
                shutil.rmtree(destination)
                raise

    def _snapshot_directory(self, relative, stage, expected, recovery, issues):
        origin = self._safe(relative)
        actual = self._inventory(origin) if origin.is_dir() else None
        if actual != expected:
            if not recovery:
                raise FlowError('Registered artifact or fixed input changed before snapshot', 409,
                                {'path': relative})
            issues.append({'code': 'recovery-content-changed', 'path': relative,
                           'expectedHash': digest(canonical(expected)),
                           'actualHash': digest(canonical(actual)) if actual is not None else None})
        if actual is None:
            # Preserve a directory accidentally replaced by a regular file, too.
            if origin.is_file():
                self._copy_file(origin, stage / relative)
            return
        self._copy_tree(origin, stage / relative)
        if self._inventory(stage / relative) != actual or self._inventory(origin) != actual:
            raise FlowError('Files changed while creating snapshot', 409, {'path': relative})

    def _copy_file(self, source, target):
        self._safe(source.relative_to(self.root))
        self._safe(target.relative_to(self.root))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def _document_references(self, documents):
        paths = set()
        for document in documents:
            for target in markdown_links(document['content']):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                relative = Path(os.path.normpath(str(Path(document['path']).parent / unquote(parsed.path))))
                paths.add(self._safe(relative).relative_to(self.root).as_posix())
        return paths

    def _referenced_files(self, documents=None, sources=None, relations=None):
        """Capture local source/screenshot files and their Markdown dependency closure."""
        paths = set()
        sources = self._read('sources.json', {'items': []}) if sources is None else sources
        relations = self._read('relations.json') if relations is None else relations
        documents = self._scan()[0] if documents is None else documents
        for source in sources['items']:
            for key in ('path', 'archivePath'):
                if source.get(key):
                    paths.add(self._safe(source[key]).relative_to(self.root).as_posix())
        for binding in relations['bindings']:
            if binding.get('screenshot'):
                paths.add(self._safe(binding['screenshot']).relative_to(self.root).as_posix())
        paths.update(self._document_references(documents))
        pending = list(paths)
        visited = {document['path'] for document in documents}
        while pending:
            relative = pending.pop()
            if relative in visited:
                continue
            visited.add(relative)
            path = self._safe(relative)
            if path.suffix.lower() == '.md' and path.is_file():
                linked = self._document_references([{'path': relative, 'content': path.read_text('utf-8')}])
                pending.extend(linked - paths)
                paths.update(linked)
        return sorted(paths)

    def _copy_tree(self, source, target):
        self._inventory(source)
        self._safe(target.relative_to(self.root))
        shutil.copytree(source, target, dirs_exist_ok=True)

    def _verify_snapshot(self, version_id):
        base = self.content_root(version_id)
        manifest = json.loads((base.parent / 'manifest.json').read_text(encoding='utf-8'))
        if self._inventory(base) != manifest['files']:
            raise FlowError('Historical snapshot changed on disk; operation refused', 409)
        return base, manifest

    def compare(self, from_version, to_version='working'):
        with self._transaction(read_only=True):
            left = self.state(from_version)
            right = self.state(to_version)
            a, b = ({r['id']: r for r in s['requirements']} for s in (left, right))
            reqs = {'added': [b[k] for k in sorted(set(b) - set(a))],
                    'removed': [a[k] for k in sorted(set(a) - set(b))],
                    'changed': [{'id': k, 'before': a[k], 'after': b[k]} for k in sorted(set(a) & set(b))
                                if a[k]['hash'] != b[k]['hash'] or a[k]['moduleId'] != b[k]['moduleId']]}
            docs_a, docs_b = ({d['id']: d for d in s['documents']} for s in (left, right))
            docs = []
            for did in sorted(set(docs_a) | set(docs_b)):
                before, after = docs_a.get(did), docs_b.get(did)
                if (before or {}).get('fullHash') != (after or {}).get('fullHash'):
                    docs.append({'id': did, 'before': before, 'after': after,
                                 'diff': '\n'.join(difflib.unified_diff((before or {}).get('content', '').splitlines(),
                                    (after or {}).get('content', '').splitlines(), fromfile=str(from_version), tofile=str(to_version), lineterm=''))})
            bind_a, bind_b = ({r['id']: r for r in s['relations'].get('bindings', [])} for s in (left, right))
            screenshots = []
            for bid in sorted(set(bind_a) | set(bind_b)):
                before, after = bind_a.get(bid), bind_b.get(bid)
                def shot_hash(binding, version):
                    path = (binding or {}).get('screenshot')
                    if not path:
                        return None
                    candidate = self._safe(path, base=self.content_root(version))
                    return digest(candidate.read_bytes()) if candidate.is_file() else None
                ha, hb = shot_hash(before, from_version), shot_hash(after, to_version)
                if ha != hb or before != after:
                    screenshots.append({'id': bid, 'before': before, 'after': after, 'beforeHash': ha, 'afterHash': hb})
            return {'from': from_version, 'to': to_version, 'requirements': reqs, 'documents': docs, 'screenshots': screenshots,
                    'frameworks': {'before': left.get('frameworks'), 'after': right.get('frameworks')}}

    def restore(self, version_id):
        with self._transaction():
            base, manifest = self._verify_snapshot(version_id)
            fixed_directories = {}
            for framework in self._frameworks(base)['items']:
                fixed_directories[framework['path']] = framework['fileHashes']
            for artifact in self._read('artifacts.json', base=base)['items']:
                fixed_directories[artifact['path']] = artifact['fileHashes']
                if artifact.get('inputPath'):
                    fixed_directories[artifact['inputPath']] = artifact.get('inputFileHashes', {})
            for path in sorted(self._safe('.prototype-flow/runs', base=base).glob('*.json')):
                run = self._read('runs/' + path.name, base=base)
                fixed_directories[run['inputPath']] = run.get('inputFileHashes', {})
            for relative, hashes in fixed_directories.items():
                origin = self._safe(relative, base=base)
                if not origin.is_dir() or self._inventory(origin) != hashes:
                    raise FlowError('Target version contains damaged artifacts or fixed inputs; inspect its recovery files instead', 409)
            previous_revision = self._project()['revision']
            backup = self.snapshot('恢复前备份 ' + version_id, recovery=True)
            historical_project = self._project(base)
            current_project = self._project()
            current_library = self._safe(current_project['libraryRoot'])
            source_library = self._safe(historical_project['libraryRoot'], base=base)
            # Keep untracked local files. Only remove previously managed document paths
            # absent from the snapshot; all are captured in the pre-restore backup.
            old_documents = {m['documentPath'] for m in current_project['modules']}
            new_documents = {m['documentPath'] for m in historical_project['modules']}
            for rel in old_documents - new_documents:
                candidate = self._safe(rel)
                if candidate.is_file():
                    candidate.unlink()
            self._copy_tree(source_library, self._safe(historical_project['libraryRoot']))
            # Copy referenced captures outside the library using the snapshot manifest;
            # never restore realtime ledgers or replace unrelated user files.
            for relative in manifest['files']:
                first = Path(relative).parts[0]
                if first in ('.prototype-flow', 'demos', 'demo-framework') or relative.startswith(historical_project['libraryRoot'] + '/'):
                    continue
                self._copy_file(self._safe(relative, base=base), self._safe(relative))
            revision_directory = base / '.prototype-flow/revisions'
            if revision_directory.exists():
                self._copy_tree(revision_directory, self._safe('.prototype-flow/revisions'))
            input_directory = base / '.prototype-flow/run-inputs'
            if input_directory.exists():
                for source in sorted(input_directory.iterdir()):
                    target = self._safe('.prototype-flow/run-inputs/' + source.name)
                    if target.exists() and (not target.is_dir() or self._inventory(target) != self._inventory(source)):
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    self._copy_tree(source, target)
            for artifact in self._read('artifacts.json', base=base)['items'] + self._frameworks(base)['items']:
                origin = self._safe(artifact['path'], base=base)
                target = self._safe(artifact['path'])
                if target.exists() and self._inventory(target) != artifact['fileHashes']:
                    # Current artifact bytes are already backed up. Replace this managed
                    # directory so later-added files do not change the historical demo.
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                self._copy_tree(origin, target)
            for filename in ('sources.json', 'requirement-index.json', 'relations.json', 'artifacts.json', 'impact.json'):
                self._write(filename, self._read(filename, base=base))
            self._write('frameworks.json', self._frameworks(base))
            historical_project.update(revision=previous_revision + 1, updatedAt=now(), restoredFrom=version_id,
                                      restoreBackup=backup['id'], maintainerPath=current_project.get('maintainerPath'))
            self._write('project.json', historical_project)
            # feishu.json, feishu-plans/ and runs/ intentionally remain untouched.
            self._maintain()
            return self._state()

    def validate(self, stage='all', document_ids=None):
        if stage not in ('all', 'prd'):
            raise FlowError('Validation stage must be all or prd')
        with self._transaction(read_only=True):
            errors, warnings = [], []
            try:
                documents, requirements = self._scan()
                ids = {r['id'] for r in requirements}
                self._check_requirement_lifecycle(
                    {r['id'] for r in self._read('requirement-index.json', {'items': []})['items']},
                    ids, self._read('relations.json'))
                sources = {s['id'] for s in self._read('sources.json', {'items': []})['items']}
                relations = self._evaluated_relations() if stage == 'all' else self._read('relations.json')
                retired = {rid for x in relations['supersessions'] for rid in x.get('from', [])}
                selected = [req for req in requirements if document_ids is None or req['documentId'] in document_ids]
                for req in selected:
                    missing_sources = set(req['sourceIds']) - sources
                    if missing_sources:
                        warnings.append({'code': 'source-missing', 'id': req['id'], 'references': sorted(missing_sources)})
                    missing = set(req['dependsOn']) - ids
                    if missing:
                        warnings.append({'code': 'dependency-needs-review' if missing <= retired else 'dependency-missing',
                                         'id': req['id'], 'references': sorted(missing)})
                artifacts = self._read('artifacts.json')['items']
                artifact_ids = {a['id'] for a in artifacts}
                if not selected:
                    warnings.append({'code': 'no-requirements', 'message': 'PRD 尚未完成需求拆分'})
                if stage == 'prd':
                    checked_docs = [doc for doc in documents if document_ids is None or doc['id'] in document_ids]
                    paths = set(self._document_references(checked_docs))
                    selected_sources = {sid for req in selected for sid in req['sourceIds']}
                    for source in self._read('sources.json', {'items': []})['items']:
                        if document_ids is None or source['id'] in selected_sources:
                            if source.get('path'):
                                paths.add(source['path'])
                    for relative in sorted(paths):
                        if not self._safe(relative).is_file():
                            warnings.append({'code': 'referenced-file-missing', 'path': relative})
                else:
                    errors.extend(self._flow_step_errors(relations, ids))
                    frameworks = self._frameworks()
                    framework_by_id = {f['id']: f for f in frameworks['items']}
                    if not framework_by_id:
                        warnings.append({'code': 'no-framework', 'message': '生成新 Demo 前需建立项目共享框架'})
                    if frameworks['currentFrameworkId'] and frameworks['currentFrameworkId'] not in framework_by_id:
                        errors.append({'code': 'framework-current-missing'})
                    for framework in frameworks['items']:
                        path = self._safe(framework['path'])
                        if not path.is_dir() or self._inventory(path) != framework['fileHashes']:
                            errors.append({'code': 'framework-mutated', 'id': framework['id']})
                    if not artifacts:
                        warnings.append({'code': 'no-demo', 'message': '尚未登记 Demo 产物'})
                    for relative in self._referenced_files():
                        if not self._safe(relative).is_file():
                            warnings.append({'code': 'referenced-file-missing', 'path': relative})
                    for artifact in artifacts:
                        path = self._safe(artifact['path'])
                        framework = framework_by_id.get(artifact.get('frameworkId'))
                        if artifact.get('frameworkId'):
                            if not framework:
                                errors.append({'code': 'artifact-framework-missing', 'id': artifact['id']})
                            elif self._inventory(path / '_framework') != framework['fileHashes']:
                                errors.append({'code': 'artifact-framework-mismatch', 'id': artifact['id']})
                            if artifact.get('status') in ('verified', 'current'):
                                try:
                                    self._framework_review_file(artifact, path)
                                except FlowError:
                                    warnings.append({'code': 'framework-review-unarchived', 'id': artifact['id'],
                                                     'message': '旧记录的框架验证报告未保存在 Demo 包内，历史证据需复核'})
                        else:
                            warnings.append({'code': 'framework-unbound', 'id': artifact['id'],
                                             'message': '历史 Demo 未绑定共享框架，下次生成前需提取接入'})
                        if not path.is_dir():
                            errors.append({'code': 'artifact-missing', 'id': artifact['id']})
                        elif self._inventory(path) != artifact['fileHashes']:
                            errors.append({'code': 'artifact-mutated', 'id': artifact['id']})
                        if not artifact.get('evidence'):
                            warnings.append({'code': 'artifact-unverified', 'id': artifact['id']})
                    for group in ('flows', 'bindings'):
                        for item in relations[group]:
                            if set(item.get('requirementIds', [])) - ids:
                                errors.append({'code': 'relation-requirement-missing', 'id': item['id']})
                            if item.get('status') == 'needs-review':
                                warnings.append({'code': 'relation-needs-review', 'id': item['id']})
                            if group == 'bindings':
                                if item.get('artifactId') not in artifact_ids:
                                    errors.append({'code': 'binding-artifact-missing', 'id': item['id']})
                                if item.get('screenshot') and not self._safe(item['screenshot']).is_file():
                                    warnings.append({'code': 'screenshot-missing', 'id': item['id']})
                                if not item.get('verified'):
                                    warnings.append({'code': 'entry-unverified', 'id': item['id']})
                if self._read('maintenance.json', {}).get('status') != 'ok':
                    warnings.append({'code': 'maintenance-pending', 'message': '文档已保存，文档库维护未完成'})
            except (FlowError, OSError, ValueError, KeyError) as exc:
                errors.append({'code': 'invalid-project', 'message': str(exc)})
            return {'ok': not errors, 'errors': errors, 'warnings': warnings}
