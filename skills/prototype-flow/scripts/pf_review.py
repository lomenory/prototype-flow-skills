"""Scoped, read-only snapshots for optional conversation cards."""
from __future__ import annotations

import base64
import difflib
import json
import uuid
from datetime import datetime, timezone

from pf_core import FlowError, business_text, digest, parse_requirements, split_frontmatter, valid_id
from pf_queries import _run_summary, _selected, query_state

VIEWS = ('overview', 'module', 'requirement', 'tasks', 'task', 'history', 'compare')
STAGES = {'intake': '资料整理', 'draft': 'PRD 草稿', 'review': '内容待确认',
          'demo': 'Demo 制作', 'validation': '交付待验收', 'confirmed': '交付已确认'}


def page_evidence(binding, artifact):
    """Same labels and precedence as the workbench's pageEvidence()."""
    usable = bool(artifact) and artifact.get('syncStatus') != 'invalid' and (
        not artifact.get('integrityStatus') or artifact['integrityStatus'] in ('intact', 'unchecked')
        or artifact.get('kind') == 'working-draft' and artifact['integrityStatus'] == 'editing')
    invalid = not usable
    stale = bool(artifact) and artifact.get('syncStatus') == 'stale'
    editing = bool(artifact) and artifact.get('kind') == 'working-draft' and (
        artifact.get('integrityStatus') == 'editing' or artifact.get('editStatus') == 'editing')
    registered = binding.get('verificationStatus') == 'unchecked' and binding.get('registeredVerified')
    label = ('产物文件已变化 · 待核对' if invalid else '工作稿正在调整 · 证据待更新' if editing
             else '需求已更新 · 待复核' if stale else '缺少验证记录' if binding.get('verificationStatus') == 'missing-fingerprint'
             else '截图或入口已变 · 待验证' if binding.get('verificationStatus') == 'fingerprint-changed'
             else '关联证据待复核' if binding.get('status') == 'needs-review'
             else '验证已登记 · 待检查文件' if registered else '已验证' if binding.get('verified') else '尚未验证')
    return {'label': label, 'invalid': invalid, 'needsReview': bool(invalid or editing or stale
        or binding.get('status') == 'needs-review' or not binding.get('verified') and not registered)}


def _document(store, base, module):
    path = store._safe(module['documentPath'], base=base, must_exist=True)
    content = store._file_bytes(path).decode('utf-8')
    meta, _, _ = split_frontmatter(content)
    if meta.get('documentId') != module['documentId'] or meta.get('moduleId') != module['id']:
        raise FlowError('Document identity changed outside an explicit operation', 409,
                        {'path': module['documentPath']})
    document = {'id': module['documentId'], 'moduleId': module['id'], 'path': module['documentPath'],
                'title': str(meta.get('title', module['title'])), 'revision': digest(content),
                'businessHash': digest(business_text(content)), 'content': content}
    return document, parse_requirements(content, document['id'], module['id'])


def _page(items, scope, source, limit, cursor):
    offset = 0
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            if token['scope'] != scope or token['source'] != source:
                raise FlowError('查询来源或范围已变化，请重新读取第一页', 409, {'code': 'cursor-stale'})
            offset = token['offset']
            if type(offset) is not int or offset < 0 or offset > len(items):
                raise ValueError('offset')
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise FlowError('分页游标无效', 400) from exc
    selected = items[offset:offset + limit]
    next_offset = offset + len(selected)
    next_cursor = (base64.urlsafe_b64encode(json.dumps({'scope': scope, 'source': source,
                    'offset': next_offset}, sort_keys=True).encode()).decode()
                   if next_offset < len(items) else None)
    return selected, {'limit': limit, 'total': len(items), 'nextCursor': next_cursor}


def _entry(store, version, requirement):
    from pf_server import resolve_demo_entry
    try:
        result = resolve_demo_entry(store, version=version, requirement_id=requirement, check_files=True)
        return {'status': 'available', 'versionId': result['versionId'],
                'artifactId': result['artifact']['id'], 'bindingId': (result.get('binding') or {}).get('id')}
    except FlowError as exc:
        return {'status': (exc.details or {}).get('code', 'unavailable') if isinstance(exc.details, dict) else 'unavailable',
                'reason': str(exc), 'details': exc.details}


def review_state(store, view='overview', module_id=None, requirement_id=None, run_id=None,
                 version=None, from_version=None, to_version='working', limit=20, cursor=None, query=None):
    if view not in VIEWS or type(limit) is not int or not 1 <= limit <= 50:
        raise FlowError('视图无效或 limit 不在 1 到 50 之间')
    for value in (module_id, requirement_id, run_id):
        if value:
            valid_id(value)
    if view == 'module' and not module_id or view == 'requirement' and not requirement_id or view == 'task' and not run_id:
        raise FlowError('该视图需要明确的对象 ID')
    if view == 'history' and version in (None, '', 'working'):
        raise FlowError('历史视图需要明确的版本')
    if view == 'compare' and not from_version:
        raise FlowError('比较视图需要 --from 版本')
    historical = version not in (None, '', 'working')
    scope = {'view': view, 'moduleId': module_id, 'requirementId': requirement_id,
             'runId': run_id, 'versionId': version or 'working', 'from': from_version,
             'to': to_version, 'query': query or ''}
    with store._transaction(read_only=True), store._read_session():
        base = store._verify_snapshot(version)[0] if historical else store.root
        project = store._project(base)
        index = store._read('requirement-index.json', {'items': [], 'documents': []}, base=base)
        modules = project['modules']
        selected_module = next((m for m in modules if m['id'] == module_id), None) if module_id else None
        if module_id and not selected_module:
            raise FlowError('模块在此版本中不存在', 404, {'id': module_id})
        if requirement_id:
            indexed = next((r for r in index['items'] if r['id'] == requirement_id), None)
            if not indexed:
                raise FlowError('需求在此版本中不存在，请重新定位当前对象', 404, {'id': requirement_id})
            owner = next((m for m in modules if m['documentId'] == indexed['documentId']), None)
            if not owner or selected_module and owner['id'] != selected_module['id']:
                raise FlowError('需求归属与请求范围不一致', 409)
            selected_module = owner
        documents, requirements, changed = [], [], False
        if view not in ('tasks', 'task'):
            for module in ([selected_module] if selected_module else modules):
                doc, reqs = _document(store, base, module)
                documents.append(doc)
                requirements.extend(reqs)
                old_doc = next((d for d in index['documents'] if d['id'] == doc['id']), {})
                changed |= old_doc.get('fullHash') != doc['revision']
            ids = [r['id'] for r in requirements]
            if len(ids) != len(set(ids)):
                raise FlowError('Duplicate project requirement ID')
            retired = {rid for item in store._read('relations.json', {}, base=base).get('supersessions', []) for rid in item.get('from', [])}
            old = {r['id'] for r in index['items'] if r['documentId'] in {d['id'] for d in documents}}
            if (old - set(ids) - retired) or set(ids) & retired:
                raise FlowError('需求生命周期发生外部变化，请先核对显式变更', 409)
        basis = {'documents': [_selected(d, 'id', 'revision', 'businessHash') for d in documents],
                 'requirements': [_selected(r, 'id', 'hash') for r in requirements]}
        raw_relations = store._read('relations.json', {'bindings': []}, base=base)
        artifacts = store._read('artifacts.json', {'items': []}, base=base)
        needed_ids = {r['id'] for r in requirements}
        bindings = [dict(b) for b in raw_relations['bindings'] if needed_ids.intersection(b.get('requirementIds', []))]
        for binding in bindings:
            if binding.get('verified'):
                binding.update(registeredVerified=True, verified=False, verificationStatus='unchecked')
        pending = set(store._read('impact.json', {}, base=base).get('requirementIds', []))
        old_requirements = {r['id']: r for r in index['items']}
        for req in requirements:
            if old_requirements.get(req['id'], {}).get('hash') != req['hash']:
                pending.add(req['id'])
            doc = next(d for d in documents if d['id'] == req['documentId'])
            old_doc = next((d for d in index['documents'] if d['id'] == doc['id']), {})
            if old_doc.get('businessHash') != doc['businessHash']:
                pending.add(req['id'])
        pending = set(store._pending_after_confirmation(project, documents, requirements, pending))
        for req in requirements:
            req['analysisStatus'] = 'pending' if req['id'] in pending else 'current'
        # Project stages describe the observed PRD too, without persisting a refresh.
        for module in modules:
            if module.get('stage') == 'confirmed' and any(r['moduleId'] == module['id'] and r['id'] in pending for r in requirements):
                module['stage'] = 'review'
        def summary(req):
            return {**_selected(req, 'id', 'title', 'moduleId', 'documentId', 'status', 'analysisStatus', 'hash'),
                    'pageCount': sum(req['id'] in b.get('requirementIds', []) for b in bindings)}
        data, items, page = {}, [], None
        def attention_items():
            result = [{**summary(r), 'kind': 'requirement', 'requirementId': r['id'],
                       'reason': '内容待复核' if r.get('status') in ('confirmed', 'approved') else '待分析'}
                      for r in requirements if r['id'] in pending]
            for binding in bindings:
                artifact = next((a for a in artifacts['items'] if a['id'] == binding['artifactId']), None)
                if artifact:
                    doc_hashes = {d['id']: d['businessHash'] for d in documents}
                    req_hashes = {r['id']: r['hash'] for r in requirements}
                    stale = any(did in doc_hashes and expected != doc_hashes[did]
                                for did, expected in artifact.get('documentHashes', {}).items()) or any(
                        rid in req_hashes and expected != req_hashes[rid] for rid, expected in artifact.get('requirementHashes', {}).items())
                    artifact = {**artifact, 'integrityStatus': 'unchecked', 'syncStatus': 'stale' if stale else 'current'}
                evidence = page_evidence(binding, artifact)
                if evidence['needsReview']:
                    result.append({'id': binding['id'], 'kind': 'binding', 'title': binding.get('title') or '关联页面',
                        'bindingId': binding['id'], 'artifactId': binding['artifactId'], 'reason': evidence['label']})
            for module in ([selected_module] if selected_module else modules):
                if module.get('stage') in ('review', 'validation'):
                    result.append({'id': module['id'], 'kind': 'module', 'moduleId': module['id'],
                                   'title': module['title'], 'reason': STAGES[module['stage']]})
            maintenance = store._read('maintenance.json', {}, base=base)
            if maintenance.get('status') in ('failed', 'pending') or maintenance.get('ok') is False:
                result.append({'id': 'maintenance', 'kind': 'maintenance', 'title': '文档导航维护',
                    'reason': maintenance.get('error') or maintenance.get('message') or '维护未完成，需 Agent 检查'})
            return result
        if view in ('overview', 'history'):
            items = [{**_selected(m, 'id', 'title', 'stage', 'documentId'), 'stageLabel': STAGES.get(m.get('stage'), m.get('stage')),
                      'requirementCount': sum(r['moduleId'] == m['id'] for r in requirements)} for m in modules]
            data['pending'] = attention_items()
            runs = [store._read('runs/' + p.name, base=base) for p in store._safe('.prototype-flow/runs', base=base).glob('*.json')]
            runs.sort(key=lambda r: (r.get('finishedAt') or r.get('createdAt') or '', r['id']), reverse=True)
            data['recentTasks'] = [{**_run_summary(r), 'runId': r['id']} for r in runs[:5]]
            seen, resumed = set(), {r.get('resumedFrom', {}).get('runId') for r in runs}
            for run in runs:
                key = (run.get('stage'), tuple(sorted(run.get('requirementIds', []))))
                if key in seen or run['id'] in resumed:
                    continue
                seen.add(key)
                if run.get('status') in ('failed', 'partial', 'blocked'):
                    data['pending'].append({'id': run['id'], 'kind': 'run', 'title': STAGES.get(run.get('stage'), run.get('stage')) + '任务',
                        'runId': run['id'], 'reason': run.get('error') or run['status']})
            data['pending'] = data['pending'][:20]
        elif view == 'module':
            data['module'] = _selected(selected_module, 'id', 'title', 'stage', 'documentId')
            items = [summary(r) for r in requirements]
            data['pending'] = attention_items()[:20]
        elif view == 'requirement':
            req = next((r for r in requirements if r['id'] == requirement_id), None)
            if not req:
                raise FlowError('需求已移除或改变，请重新定位', 404)
            data['requirement'] = {**summary(req), **_selected(req, 'dependsOn', 'sourceIds', 'acceptance'),
                                   'excerpt': req.get('content', '')[:4000], 'excerpted': True}
            bindings = [b for b in bindings if requirement_id in b.get('requirementIds', [])]
            from pf_server import resolve_demo_entry
            try:
                resolved = resolve_demo_entry(store, version=version, requirement_id=requirement_id, check_files=False)
                chosen_id = resolved['artifact']['id']
            except FlowError as exc:
                chosen_id = exc.details.get('artifactId') if isinstance(exc.details, dict) else None
            chosen = next((a for a in artifacts['items'] if a['id'] == chosen_id), None)
            if chosen and chosen.get('kind') != 'working-draft' and 'frozenRelations' in chosen:
                bindings = [b for b in bindings if b['artifactId'] != chosen_id] + [
                    b for b in chosen['frozenRelations'].get('bindings', []) if requirement_id in b.get('requirementIds', [])]
            checked_bindings = []
            for binding in bindings:
                try:
                    checked = resolve_demo_entry(store, version=version, binding_id=binding['id'],
                        within_artifact=binding['artifactId'])['binding']
                except FlowError as exc:
                    checked = {**binding, 'verified': False, 'status': 'needs-review', 'verificationStatus': 'entry-invalid', 'entryError': str(exc)}
                checked_bindings.append(checked)
            bindings = checked_bindings
            artifact_records = {aid: query_state(store, 'artifacts', aid, version)['artifacts']['items'][0]
                                for aid in {b['artifactId'] for b in bindings}
                                if any(a['id'] == aid for a in artifacts['items'])}
            data['bindings'] = [{**_selected(b, 'id', 'title', 'artifactId', 'route', 'screenId', 'stateId',
                'primaryRequirementIds', 'requirementIds', 'verificationStatus', 'verified', 'screenshot'),
                'evidence': page_evidence(b, artifact_records.get(b['artifactId']))} for b in bindings]
            data['demoEntry'] = _entry(store, version, requirement_id)
            sources = store._read('sources.json', {'items': []}, base=base)['items']
            data['sources'] = [_selected(s, 'id', 'label', 'kind', 'locator') for s in sources if s['id'] in req.get('sourceIds', [])]
            basis['requirements'] = [_selected(req, 'id', 'hash')]
            if not historical:
                from pf_drafts import demo_edit_basis
                try:
                    demo_basis = demo_edit_basis(store, requirement_ids=[requirement_id])
                    if not chosen_id or (demo_basis.get('artifact') or {}).get('id') != chosen_id:
                        raise FlowError('此需求的演示产物不是当前编辑源，请先明确编辑产物；已保留独立查看入口', 409)
                    basis['demo'] = demo_basis
                except FlowError as exc:
                    reason = str(exc)
                    data['demoEditUnavailable'] = ('当前 Demo 尚未登记共享框架，暂不能从卡片发起 Demo 修改，可在对话中继续处理。'
                        if 'framework' in reason.casefold() else '当前编辑源与此需求的 Demo 不一致，请在对话中明确编辑对象。'
                        if '此需求的演示产物' in reason else '当前 Demo 有未完成的编辑任务，请在对话中继续或结束该任务。'
                        if 'unfinished edit' in reason else '当前工作稿有未保存修改，请在对话中先处理已有工作。'
                        if 'unsaved changes' in reason else 'Demo 编辑基线暂不可用，请在对话中核对活动任务、未保存修改及当前依据。')
                    data['demoEditDetails'] = {'reason': reason, 'status': exc.status}
        elif view in ('tasks', 'task'):
            if run_id:
                record = store._read('runs/' + run_id + '.json', base=base)
                if not record:
                    raise FlowError('任务在此版本中不存在', 404)
                runs = [record]
            else:
                runs = [store._read('runs/' + p.name, base=base) for p in store._safe('.prototype-flow/runs', base=base).glob('*.json')]
            if module_id:
                owned = {r['id'] for r in index['items'] if r['documentId'] == selected_module['documentId']}
                runs = [r for r in runs if owned.intersection(r.get('requirementIds', []))]
                if run_id and not runs:
                    raise FlowError('任务归属与请求范围不一致', 409)
            items = [_run_summary(r) for r in runs]
            if view == 'task':
                data['task'] = items[0]
                items = []
        else:
            source_base = store._verify_snapshot(from_version)[0] if from_version != 'working' else store.root
            target_base = store._verify_snapshot(to_version)[0] if to_version != 'working' else store.root
            left, right = {}, {}
            for target_base_, table in ((source_base, left), (target_base, right)):
                for module in store._project(target_base_)['modules']:
                    if module_id and module['id'] != module_id:
                        continue
                    document, _ = _document(store, target_base_, module)
                    table[document['id']] = document
            for did in sorted(set(left) | set(right)):
                before, after = left.get(did, {}), right.get(did, {})
                if before.get('revision') == after.get('revision'):
                    continue
                diff = '\n'.join(difflib.unified_diff(before.get('content', '').splitlines(), after.get('content', '').splitlines(), n=3))
                items.append({'id': did, 'title': after.get('title') or before.get('title'),
                              'beforeRevision': before.get('revision'), 'afterRevision': after.get('revision'),
                              'diffExcerpt': diff[:6000], 'excerpted': len(diff) > 6000})
            data.update(fromVersion=from_version, toVersion=to_version)
        if query:
            needle = query.casefold()
            items = [i for i in items if needle in json.dumps(_selected(i, 'id', 'title', 'stage', 'status'), ensure_ascii=False).casefold()]
        source = digest(json.dumps({'scope': scope, 'basis': basis, 'items': items, 'data': data,
            'relations': bindings, 'project': project}, ensure_ascii=False, sort_keys=True))
        items.sort(key=lambda i: i['id'])
        if view not in ('requirement', 'task'):
            items, page = _page(items, scope, source, limit, cursor)
            data['items'] = items
            if view == 'module':
                basis['requirements'] = [r for r in basis['requirements'] if r['id'] in {i['id'] for i in items}]
        elif cursor:
            raise FlowError('详情视图不使用分页游标')
        actions = [{'intent': name, 'enabled': True} for name in ('inspect', 'read-latest', 'open-workbench')]
        if view == 'requirement':
            actions += [{'intent': 'open-demo', 'enabled': data['demoEntry']['status'] == 'available', 'reason': data['demoEntry'].get('reason')},
                        {'intent': 'change', 'enabled': not historical, 'reason': '历史内容只读' if historical else None}]
        if view == 'module':
            actions += [{'intent': 'change', 'enabled': not historical, 'reason': '历史内容只读' if historical else None},
                        {'intent': 'export-module', 'enabled': selected_module.get('stage') == 'confirmed', 'reason': '需已确认且完整的冻结 Demo'}]
        if view == 'task':
            actions += [{'intent': 'continue-run', 'enabled': data['task']['status'] != 'completed'}]
        if view in ('overview', 'history'):
            actions += [{'intent': 'compare', 'enabled': historical, 'reason': '需要明确历史版本'}]
        return {'schemaVersion': 1, 'snapshotId': str(uuid.uuid4()),
                'observedAt': datetime.now(timezone.utc).isoformat(),
                'project': {'id': project['id'], 'name': project['name'], 'rootHint': str(store.root), 'storedRevision': project['revision']},
                'versionId': version or 'working', 'historical': historical, 'scope': scope, 'basis': basis,
                'sourceFingerprint': source, 'data': data, 'page': page,
                'freshness': {'checkedDocumentIds': [d['id'] for d in documents],
                    'externalChanges': changed if documents else None,
                    'artifactIntegrity': 'selected' if view == 'requirement' else 'unchecked',
                    'otherIntegrityUnchecked': True}, 'actions': actions}
