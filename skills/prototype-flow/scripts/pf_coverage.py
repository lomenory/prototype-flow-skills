"""Read-only requirement coverage of one explicitly selected Demo baseline.

Bindings record observed page states, not the complete set of business requirements.
Only a requirement's versioned ``demoCoverage`` declaration supplies a denominator.
"""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pf_core import FlowError, valid_id
from pf_queries import _artifact_inputs, _selected
from pf_evidence import changed_keys, merge_review_reasons, review_reason


CONTRACT = 'prototype-flow.coverage/1'
STATUS_LABELS = {'not-generated': '尚未生成', 'generating': '生成中', 'blocked': '生成受阻',
                 'partial': '部分生成', 'generated': '已生成 · 待验证', 'verified': '已验证',
                 'stale': '需求或产物已变化', 'unknown': '覆盖范围待明确'}


def validate_demo_coverage(value):
    """Validate an explicit, nonempty set of expected page states; never infer one."""
    if (not isinstance(value, dict) or set(value) != {'schemaVersion', 'items'}
            or type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1
            or not isinstance(value.get('items'), list) or not value['items']):
        raise FlowError('demoCoverage requires schemaVersion:1 and nonempty items')
    ids, targets = set(), set()
    for item in value['items']:
        if (not isinstance(item, dict)
                or set(item) - {'id', 'title', 'screenId', 'stateId', 'fixtureId'}
                or not {'id', 'title', 'screenId', 'stateId'}.issubset(item)
                or not isinstance(item.get('title'), str) or not item['title'].strip()
                or 'fixtureId' in item and not isinstance(item['fixtureId'], str)):
            raise FlowError('demoCoverage items require id, title, screenId and stateId')
        for key in ('id', 'screenId', 'stateId'):
            valid_id(item[key])
        target = (item['screenId'], item['stateId'], item.get('fixtureId'))
        # An omitted fixture means any fixture; overlapping declarations cannot
        # turn one observed page state into two covered acceptance targets.
        if item['id'] in ids or any(target[:2] == previous[:2] and (
                target[2] is None or previous[2] is None or target[2] == previous[2]) for previous in targets):
            raise FlowError('demoCoverage IDs and page-state targets must be unique')
        ids.add(item['id'])
        targets.add(target)
    return copy.deepcopy(value)


def _declaration(requirement):
    if 'demoCoverage' not in requirement:
        return None, '尚未声明此需求应覆盖的页面状态，无法判断是否完整。'
    try:
        return validate_demo_coverage(requirement['demoCoverage']), None
    except FlowError:
        return None, '此需求的 Demo 覆盖声明无效，需核对预期页面状态。'


def _latest_tasks(store, base, project, runs, requirements, documents):
    """Check selected Demo tasks against all their declared input dependencies."""
    candidates = [run for run in runs if run.get('stage') == 'demo']
    resumed = {run.get('resumedFrom', {}).get('runId') for run in candidates}
    candidates.sort(key=lambda run: (run.get('createdAt') or '', run.get('inputRevision') or 0,
                                     run.get('id') or ''), reverse=True)
    scope_ids = {req['id'] for req in requirements}
    selected = {}
    for run in candidates:
        if run.get('id') in resumed:
            continue
        for rid in run.get('requirementIds', []):
            if rid not in scope_ids or rid in selected:
                continue
            selected[rid] = run
    # Display scope is narrower than a task's fixed input scope. Reading a
    # dependency never assigns its node a task, but changing/deleting it must
    # prevent the task from appearing current. This helper reads only declared
    # input documents, and the surrounding read session reuses their bytes.
    chosen_runs = list({run['id']: run for run in selected.values()}.values())
    doc_hashes, req_hashes = _artifact_inputs(store, base, project, chosen_runs) if chosen_runs else ({}, {})
    req_hashes.update({req['id']: req.get('hash') for req in requirements})
    doc_hashes.update({doc['id']: doc.get('businessHash') for doc in documents})
    tasks = {}
    for rid, run in selected.items():
        stale = any(req_hashes.get(key) != expected for key, expected in run.get('requirementHashes', {}).items()) or any(
            doc_hashes.get(key) != expected for key, expected in run.get('documentHashes', {}).items())
        tasks[rid] = {**_selected(run, 'id', 'status', 'createdAt', 'finishedAt', 'error'), 'stale': stale}
    return tasks


def _entry(store, base, artifact, binding, inventory):
    """Check actual registered HTML bytes, without starting a preview service."""
    route = binding.get('route')
    if not isinstance(route, str) or not route:
        return False
    try:
        store._validate_route(route)
        relative = unquote(urlsplit(route).path) or artifact.get('entryHtml', 'index.html')
        if Path(relative).suffix.lower() not in ('.html', '.htm') or any(
                part.startswith('.') for part in Path(relative).parts):
            return False
        path = store._safe(relative, base=store._safe(artifact['path'], base=base))
        expected = artifact.get('fileHashes', {}).get(relative)
        return bool(expected and path.is_file() and inventory.get(relative) == expected)
    except (FlowError, OSError, ValueError):
        return False


def _matches(target, page):
    return (target['screenId'] == page.get('screenId') and target['stateId'] == page.get('stateId')
            and ('fixtureId' not in target or target['fixtureId'] == page.get('fixtureId')))


def _coverage(requirement, pages):
    declaration, reason = _declaration(requirement)
    result = {'known': declaration is not None, 'total': None, 'generated': 0, 'verified': 0,
              'recordedGenerated': 0, 'recordedVerified': 0, 'items': [], 'reason': reason}
    if declaration is None:
        # These are observed-page counts, not a percentage of an unknown target.
        result.update(generated=sum(page['generated'] for page in pages),
                      verified=sum(page['verified'] for page in pages),
                      recordedGenerated=len(pages),
                      recordedVerified=sum(page['registeredVerified'] for page in pages))
        return result
    result['total'] = len(declaration['items'])
    for target in declaration['items']:
        matching = [page for page in pages if _matches(target, page)]
        generated = any(page['generated'] for page in matching)
        verified = any(page['verified'] for page in matching)
        recorded_verified = any(page['registeredVerified'] for page in matching)
        state = ('verified' if verified else 'generated' if generated else
                 'stale' if any(page['stale'] for page in matching) else 'not-generated')
        result['items'].append({**target, 'status': state, 'bindingIds': [page['id'] for page in matching],
                                'generated': generated, 'verified': verified})
        result['generated'] += generated
        result['verified'] += verified
        result['recordedGenerated'] += bool(matching)
        result['recordedVerified'] += recorded_verified
    return result


def _status(coverage, pages, task, selection_reason):
    if task and not task['stale']:
        if task.get('status') == 'running':
            return 'generating', '正在生成此需求的 Demo；完成情况以实际页面与验证记录为准。'
        if task.get('status') in ('blocked', 'failed', 'partial'):
            return 'blocked', '此需求最近的 Demo 任务尚未完成，请查看任务原因与已有页面。'
    if any(page['stale'] for page in pages):
        return 'stale', '已有页面或验证依据已过期，旧记录保留，当前有效覆盖需重新核对。'
    if selection_reason:
        return 'unknown', selection_reason
    if not coverage['known']:
        return ('unknown', coverage['reason']) if pages else ('not-generated', '尚无此需求的页面记录。' + coverage['reason'])
    if coverage['verified'] == coverage['total']:
        return 'verified', '已声明的页面状态均有当前有效验证记录。'
    if coverage['generated'] == coverage['total']:
        return 'generated', '已声明的页面状态均有可读取的登记入口，仍需完成验证。'
    if coverage['generated']:
        return 'partial', '部分预期页面状态已有入口，其余页面仍待生成。'
    return 'not-generated', '已声明的页面状态尚无当前有效入口。'


def requirement_coverage(store, requirements, documents, version=None, artifact_id=None):
    """Project real coverage for a single baseline, without modifying project files.

    ``requirements`` and ``documents`` must be the current Markdown-derived
    records for the requested view. Artifact input dependencies are read as well.
    An explicit artifact is authoritative; otherwise only the current registry
    pointer (or legacy currentDraftId fallback) is selected, never the newest file.
    """
    historical = version not in (None, '', 'working')
    if artifact_id:
        valid_id(artifact_id)
    with store._transaction(read_only=True), store._read_session():
        base = store._verify_snapshot(version)[0] if historical else store.root
        project = store._project(base)
        registry = store._read('artifacts.json', {'items': []}, base=base)
        chosen_id = artifact_id or registry.get('currentArtifactId') or registry.get('currentDraftId')
        candidates = [item for item in registry['items'] if item.get('id') == chosen_id] if chosen_id else []
        selection_reason = None
        if chosen_id and len(candidates) != 1:
            selection_reason = '当前 Demo 指针无法唯一定位产物，需核对当前生成版本。'
        elif not chosen_id and registry['items']:
            selection_reason = '尚未指定当前 Demo，不能混合多个候选或历史产物判断覆盖。'
        artifact = copy.deepcopy(candidates[0]) if len(candidates) == 1 else None
        pages = []
        if artifact:
            doc_hashes, req_hashes = _artifact_inputs(store, base, project, [artifact])
            doc_hashes.update({doc['id']: doc['businessHash'] for doc in documents})
            req_hashes.update({req['id']: req['hash'] for req in requirements})
            artifact['staleRequirementIds'] = sorted(rid for rid, expected in artifact.get('requirementHashes', {}).items()
                                                      if req_hashes.get(rid) != expected)
            artifact['staleDocumentIds'] = sorted(did for did, expected in artifact.get('documentHashes', {}).items()
                                                   if doc_hashes.get(did) != expected)
            directory = store._safe(artifact['path'], base=base)
            inventory = store._resource_inventory(directory, artifact)
            intact = directory.is_dir() and inventory == artifact.get('fileHashes')
            draft = artifact.get('kind') == 'working-draft'
            editing = draft and (not intact or artifact.get('activeRunId') or artifact.get('editStatus') != 'ready')
            input_stale = bool(artifact['staleRequirementIds'] or artifact['staleDocumentIds'])
            artifact.update(integrityStatus='intact' if intact else 'editing' if draft and directory.is_dir() else 'changed',
                            syncStatus='editing' if editing else 'invalid' if not intact else 'stale' if input_stale else 'current')
            live = store._read('relations.json', {'bindings': []}, base=base)['bindings']
            frozen = not draft and 'frozenRelations' in artifact
            source = artifact['frozenRelations'].get('bindings', []) if frozen else live
            wanted = {req['id'] for req in requirements}
            bindings = [copy.deepcopy(binding) for binding in source if binding.get('artifactId') == artifact['id']
                        and wanted.intersection(binding.get('requirementIds', []))]
            if frozen:
                evaluated = {binding['id']: copy.deepcopy(binding) for binding in bindings}
                for binding in evaluated.values():
                    if binding.get('verified'):
                        try:
                            valid = bool(binding.get('verificationHash')) and binding['verificationHash'] == store._binding_fingerprint(
                                binding, base=base, artifacts={artifact['id']: artifact})
                        except (FlowError, OSError, UnicodeError):
                            valid = False
                        if not valid:
                            binding.update(verified=False, status='needs-review', verificationStatus='fingerprint-changed')
            else:
                evaluated = {binding['id']: binding for binding in store._evaluated_relations(
                    base=base, binding_ids={binding['id'] for binding in bindings},
                    artifact_inventories={artifact['id']: inventory})['bindings']}
            for original in bindings:
                binding = evaluated[original['id']]
                entry_available = _entry(store, base, artifact, binding, inventory)
                inputs_known = all(rid in artifact.get('requirementHashes', {}) for rid in binding.get('requirementIds', []))
                stale = bool(input_stale or not intact or editing or not inputs_known or not entry_available
                             or binding.get('status') == 'needs-review')
                generated = entry_available and not stale
                verified = generated and not stale and binding.get('verified') is True and binding.get('verificationStatus') != 'unchecked'
                reasons = merge_review_reasons(binding.get('reviewReasons', [])) if not binding.get('verified') else []
                if artifact['staleRequirementIds']:
                    reasons.append(review_reason('requirement-input', requirementIds=artifact['staleRequirementIds']))
                if not inputs_known:
                    reasons.append(review_reason('requirement-input', requirementIds=sorted(
                        rid for rid in binding.get('requirementIds', []) if rid not in artifact.get('requirementHashes', {}))))
                if artifact['staleDocumentIds']:
                    reasons.append(review_reason('shared-document', documentIds=artifact['staleDocumentIds']))
                if not intact:
                    reasons.append(review_reason('dependency-content', paths=changed_keys(artifact.get('fileHashes', {}), inventory)))
                if editing:
                    reasons.append(review_reason('draft-editing'))
                if not entry_available:
                    reasons.append(review_reason('entry-unavailable'))
                if not verified and not reasons:
                    reasons.append(review_reason('evidence-changed' if original.get('verified') else 'prior-needs-review'))
                # Keep saved explanations and live invalidation causes in one projection.
                # Old bindings have no extra fields; their existing validity stays unchanged.
                unique_reasons = merge_review_reasons(reasons)
                pages.append({**_selected(binding, 'id', 'title', 'artifactId', 'screenId', 'stateId', 'fixtureId',
                    'route', 'screenshot', 'requirementIds', 'verificationStatus', 'evidence', 'verificationInheritedFrom',
                    'reviewChange', 'reviewRevision'),
                    'title': binding.get('title') or binding.get('screenId') or '关联页面',
                    'entryAvailable': entry_available, 'generated': bool(generated), 'verified': bool(verified),
                    'registeredVerified': original.get('verified') is True or original.get('registeredVerified') is True,
                    'stale': stale, 'historical': historical, 'reviewReasons': unique_reasons})
        directory = store._safe('.prototype-flow/runs', base=base)
        runs = [store._read('runs/' + path.name, base=base) for path in directory.glob('*.json')]
        tasks = _latest_tasks(store, base, project, runs, requirements, documents)
        rows = []
        for requirement in requirements:
            related = [page for page in pages if requirement['id'] in page.get('requirementIds', [])]
            coverage = _coverage(requirement, related)
            task = tasks.get(requirement['id'])
            status, reason = _status(coverage, related, task, selection_reason)
            rows.append({'requirementId': requirement['id'], 'status': status, 'label': STATUS_LABELS[status],
                         'reason': reason, 'coverage': coverage, 'pages': related, 'task': task})
        counts = Counter(row['status'] for row in rows)
        return {'contract': CONTRACT, 'versionId': version or 'working', 'historical': historical,
                'artifact': _selected(artifact, 'id', 'title', 'kind', 'draftRevision', 'integrityStatus', 'syncStatus',
                                      'staleRequirementIds', 'staleDocumentIds') if artifact else None,
                'selectionReason': selection_reason, 'requirements': rows,
                'summary': {'total': len(rows), 'byStatus': dict(counts),
                    'coverageKnown': sum(row['coverage']['known'] for row in rows),
                    'generated': sum(row['coverage']['known'] and row['coverage']['generated'] == row['coverage']['total'] for row in rows),
                    'verified': sum(row['coverage']['known'] and row['coverage']['verified'] == row['coverage']['total'] for row in rows)}}
