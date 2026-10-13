"""Read-only requirement graph shared by conversation snapshots and the live view."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from pf_core import FlowError, canonical, digest, valid_id

CONTRACT = 'prototype-flow.requirement-map/1'
REQUIREMENT_LABELS = {'draft': '草稿', 'proposed': '待确认', 'confirmed': '已确认',
                      'approved': '已确认', 'archived': '已归档'}
TASK_LABELS = {'running': '生成中', 'blocked': '受阻', 'failed': '失败', 'partial': '部分完成',
               'completed': '任务已结束', 'cancelled': '已取消'}
ITEM_LABELS = {'not-generated': '未生成', 'generated': '待验证', 'verified': '已验证', 'stale': '需更新'}


def _requirement_text(content):
    text = re.sub(r'^#{1,6}\s+[^\n]+\n*', '', content or '', count=1).strip()
    heading = re.search(r'(?m)^(?:#{1,6}\s*|\*\*)?(?:验收条件|验收标准)(?:\*\*)?\s*[:：]?\s*$', text)
    acceptance = []
    if heading:
        remaining = text[heading.end():].strip()
        next_heading = re.search(r'(?m)^#{1,6}\s+', remaining)
        suffix = ''
        if next_heading:
            suffix = remaining[next_heading.start():]
            remaining = remaining[:next_heading.start()]
        acceptance = [re.sub(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)', '', line).strip()
                      for line in remaining.splitlines() if line.strip()]
        text = (text[:heading.start()].strip() + ('\n\n' + suffix if suffix else '')).strip()
    description = text[:3000] + ('\n…（正文较长，完整内容见 PRD）' if len(text) > 3000 else '')
    return description, acceptance


def _model_requirement(req, coverage, sources):
    counts = coverage.get('coverage', {})
    description, acceptance = _requirement_text(req.get('content', ''))
    task = coverage.get('task')
    if task:
        task = {**task, 'label': TASK_LABELS.get(task.get('status'), task.get('status', '')),
                'summary': task.get('error') or task.get('summary') or ''}
    return {'id': req['id'], 'title': req['title'], 'status': req.get('status', 'draft'),
        'statusLabel': ('内容待复核' if req.get('analysisStatus') == 'pending' else
                        REQUIREMENT_LABELS.get(req.get('status'), req.get('status', '草稿'))),
        'description': description, 'businessAcceptance': acceptance, 'task': task,
        'coverage': {**counts, 'state': coverage.get('status', 'unknown'),
            'label': coverage.get('label', '覆盖未知'), 'summary': coverage.get('reason') or counts.get('reason', ''),
            'stale': coverage.get('status') == 'stale'},
        'acceptance': [{'id': item['id'], 'text': item.get('title') or item['id'],
            'state': 'missing' if item.get('status') == 'not-generated' else item.get('status', 'unknown'),
            'label': ITEM_LABELS.get(item.get('status'), '待核对'),
            'bindingIds': list(item.get('bindingIds', [])),
            **{key: item[key] for key in ('screenId', 'stateId', 'fixtureId') if key in item}}
            for item in counts.get('items', [])],
        'pages': [{**page, 'state': 'stale' if page['stale'] else 'verified' if page['verified'] else
                   'generated' if page['generated'] else 'unknown',
                   'label': '旧记录 · 待更新' if page['stale'] else '已验证' if page['verified'] else
                   '已生成 · 待验证' if page['generated'] else '入口不可用'} for page in coverage.get('pages', [])],
        'sources': [{'id': source['id'], 'title': source.get('label') or source['id'], 'excerpt': source.get('locator') or ''}
                    for source in sources if source['id'] in req.get('sourceIds', [])]}


def requirement_map_state(store, module_id=None, requirement_id=None, version=None):
    """Read one complete bounded graph. No writes, guessed completion, or pagination."""
    from pf_review import _document
    from pf_coverage import requirement_coverage
    for value in (module_id, requirement_id):
        if value:
            valid_id(value)
    historical = version not in (None, '', 'working')
    with store._transaction(read_only=True), store._read_session():
        base = store._verify_snapshot(version)[0] if historical else store.root
        project = store._project(base)
        modules = [m for m in project['modules'] if not module_id or m['id'] == module_id]
        if module_id and not modules:
            raise FlowError('模块在此版本中不存在', 404)
        index = store._read('requirement-index.json', {'items': [], 'documents': []}, base=base)
        documents, requirements = [], []
        for module in modules:
            document, items = _document(store, base, module)
            documents.append(document)
            requirements.extend(items)
        ids = [r['id'] for r in requirements]
        if len(ids) != len(set(ids)):
            raise FlowError('Duplicate project requirement ID')
        if len(requirements) > 200:
            raise FlowError('需求图超过 200 个需求，请使用 --module 缩小范围', 413)
        relations = store._read('relations.json', {}, base=base)
        retired = {rid for item in relations.get('supersessions', []) for rid in item.get('from', [])}
        # The selected node is a viewing hint, not the data scope. An explicit
        # retirement must still deliver the new graph so an open inspector can
        # explain its removal instead of leaving an apparently current old node.
        if requirement_id and requirement_id not in ids and requirement_id not in retired:
            raise FlowError('需求在当前范围中不存在，请重新定位', 404)
        old = {r['id'] for r in index['items'] if r['documentId'] in {d['id'] for d in documents}}
        if old - set(ids) - retired or set(ids) & retired:
            raise FlowError('需求生命周期发生外部变化，请先核对显式变更', 409)
        old_requirements = {r['id']: r for r in index['items']}
        old_documents = {d['id']: d for d in index['documents']}
        changed = any(old_documents.get(d['id'], {}).get('fullHash') != d['revision'] for d in documents)
        pending = set(store._read('impact.json', {}, base=base).get('requirementIds', []))
        for req in requirements:
            doc = next(d for d in documents if d['id'] == req['documentId'])
            if (old_requirements.get(req['id'], {}).get('hash') != req['hash'] or
                    old_documents.get(doc['id'], {}).get('businessHash') != doc['businessHash']):
                pending.add(req['id'])
        pending = set(store._pending_after_confirmation(project, documents, requirements, pending))
        for req in requirements:
            req['analysisStatus'] = 'pending' if req['id'] in pending else 'current'
        coverage = requirement_coverage(store, requirements, documents, version=version)
        by_id = {row['requirementId']: row for row in coverage['requirements']}
        sources = store._read('sources.json', {'items': []}, base=base)['items']
        scope = {'view': 'requirement-map', 'moduleId': module_id,
                 'requirementId': requirement_id, 'versionId': version or 'working'}
        model = {'contract': CONTRACT, 'scopeKey': digest(canonical({'projectId': project['id'], **scope})),
            'title': '需求地图', 'context': project['name'],
            'sourceLabel': ('历史版本 · ' + version if historical else '当前工作稿 · R' + str(project['revision'])),
            'artifact': coverage.get('artifact'), 'summary': coverage.get('summary', {}),
            'modules': [{'id': module['id'], 'title': module['title'],
                'requirements': [_model_requirement(req, by_id[req['id']], sources)
                                 for req in requirements if req['moduleId'] == module['id']]}
                        for module in modules]}
        basis = {'documents': [{key: d[key] for key in ('id', 'revision', 'businessHash')} for d in documents],
                 'requirements': [{key: r[key] for key in ('id', 'hash')} for r in requirements]}
        source = digest(canonical({'scope': scope, 'basis': basis, 'model': model}))
        return {'schemaVersion': 1, 'snapshotId': str(uuid.uuid4()),
            'observedAt': datetime.now(timezone.utc).isoformat(),
            'project': {'id': project['id'], 'name': project['name'], 'rootHint': str(store.root),
                        'storedRevision': project['revision']},
            'versionId': version or 'working', 'historical': historical, 'scope': scope,
            'sourceFingerprint': source, 'basis': basis, 'data': {'requirementMap': model}, 'page': None,
            'freshness': {'checkedDocumentIds': [d['id'] for d in documents], 'externalChanges': changed,
                          'artifactIntegrity': 'selected', 'otherIntegrityUnchecked': True}, 'actions': []}
