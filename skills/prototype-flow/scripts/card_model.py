"""Deterministic, purpose-driven content for conversation cards.

Review snapshots remain the hidden request baseline. This model contains only
readable content and the controls required by the explicitly chosen purpose.
"""
from __future__ import annotations

import re
from pf_core import FlowError

PURPOSES = ('read', 'edit', 'select', 'continue', 'compare', 'result')
SCOPES = {'prd': 'PRD', 'demo': 'Demo', 'prd-and-demo': 'PRD 与 Demo'}
STATUSES = {'draft': '草稿', 'proposed': '内容待确认', 'confirmed': '内容已确认',
    'approved': '内容已确认', 'archived': '已归档', 'running': '进行中',
    'completed': '已完成', 'partial': '部分完成', 'failed': '失败',
    'blocked': '受阻', 'cancelled': '已取消', 'saved': '已保存',
    'success': '已完成', 'pending': '待处理'}
STAGES = {'intake': '资料整理', 'prd': 'PRD 整理', 'draft': 'PRD 草稿',
    'review': '内容待确认', 'demo': 'Demo 制作', 'validation': '交付待验收',
    'confirmed': '交付已确认', 'legacy-import': '既有资料接入'}


def _text(value):
    return str(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ''


def _reason(value):
    if isinstance(value, dict):
        return _text(value.get('message')) or _text(value.get('reason'))
    return _text(value)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else [value] if value else []


def _status(value):
    return STATUSES.get(_text(value), '状态未登记')


def _stage(value):
    return STAGES.get(_text(value), '项目任务')


def _clean_markdown(value):
    value = _text(value).strip()
    value = re.sub(r'^#{1,6}\s+', '', value)
    value = re.sub(r'^\s*(?:[-*+]\s+|\d+[.)、]\s*)', '', value)
    value = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', lambda m: m.group(1) or m.group(2), value)
    value = re.sub(r'`([^`]+)`', r'\1', value)
    return value.strip()


def _requirement_sections(requirement):
    title = requirement.get('title', '')
    paragraphs, acceptance, current = [], [], []
    in_acceptance = False

    def flush():
        if current:
            paragraphs.append(' '.join(current))
            current.clear()

    for line in _text(requirement.get('excerpt')).splitlines():
        cleaned = _clean_markdown(line)
        if not cleaned:
            flush()
            continue
        if line.lstrip().startswith('#') and cleaned == title:
            flush()
            continue
        if re.fullmatch(r'(?:验收(?:条件|要求|标准)|Acceptance criteria)\s*[:：]?', cleaned, re.I):
            flush()
            in_acceptance = True
            continue
        if line.lstrip().startswith('#'):
            flush()
            in_acceptance = False
        if in_acceptance:
            acceptance.append(cleaned)
        else:
            current.append(cleaned)
    flush()
    supplied = requirement.get('acceptance')
    if supplied:
        for item in supplied if isinstance(supplied, list) else [supplied]:
            value = _clean_markdown(_reason(item))
            if value and value not in acceptance:
                acceptance.append(value)
    sections = []
    if paragraphs:
        sections.append({'title': '业务规则', 'type': 'text', 'paragraphs': paragraphs})
    if acceptance:
        sections.append({'title': '验收条件', 'type': 'list', 'items': acceptance})
    return sections


def _task_sections(record):
    sections, facts = [], []
    outputs = _mapping(record.get('outputs'))
    summary = _text(outputs.get('summary')) or _text(record.get('summary'))
    if summary:
        sections.append({'title': '任务进展', 'type': 'text', 'paragraphs': [summary]})
    facts.extend([{'label': '阶段', 'value': _stage(record.get('stage'))},
                  {'label': '状态', 'value': _status(record.get('status'))}])
    count = len(record.get('requirementIds', []))
    if count:
        facts.append({'label': '涉及需求', 'value': f'{count} 项'})
    for key, label, unit in (('artifactIds', 'Demo 产物', '个'), ('bindingIds', '关联页面', '个')):
        if isinstance(outputs.get(key), list) and outputs[key]:
            facts.append({'label': label, 'value': f'{len(outputs[key])} {unit}'})
    sections.append({'title': '任务状态', 'type': 'facts', 'items': facts})
    if record.get('error'):
        sections.append({'title': '当前阻碍', 'type': 'text',
            'paragraphs': [_reason(record['error']) or '任务记录了错误，需在对话中进一步核对。']})
    return sections


def _task_substantive(record):
    outputs = _mapping(record.get('outputs'))
    return bool(_text(outputs.get('summary')) or _text(record.get('summary')) or record.get('error')
        or outputs.get('artifactIds') or outputs.get('bindingIds') or record.get('status') in ('partial', 'blocked', 'failed')
        or len(record.get('requirementIds', [])) > 1)


def _read_sections(snapshot):
    data, view = snapshot['data'], snapshot['scope']['view']
    if data.get('requirement'):
        sections = _requirement_sections(data['requirement'])
        bindings = data.get('bindings') or []
        if bindings:
            sections.append({'title': '关联页面', 'type': 'records', 'collapsed': True,
                'items': [{'title': _text(item.get('title')) or '关联页面',
                    'detail': _text(item.get('evidence', {}).get('label')) or '尚未验证'} for item in bindings]})
        return sections
    if data.get('task'):
        return _task_sections(data['task'])
    items = data.get('items') or []
    if not items:
        return []
    if view == 'tasks':
        return [{'title': '已登记任务', 'type': 'records', 'items': [
            {'title': _text(item.get('title')) or _stage(item.get('stage')),
             'detail': _text(_mapping(item.get('outputs')).get('summary')) or _status(item.get('status'))} for item in items]}]
    if view == 'module':
        return [{'title': '模块需求', 'type': 'records', 'items': [
            {'title': _text(item.get('title')) or '未命名需求',
             'detail': f"{_status(item.get('status'))} · {item.get('pageCount', 0)} 个关联页面"} for item in items]}]
    return [{'title': '项目模块', 'type': 'records', 'items': [
        {'title': _text(item.get('title')) or '未命名模块',
         'detail': _text(item.get('stageLabel')) or _stage(item.get('stage'))} for item in items]}]


def _changes(data):
    changes = []
    for item in data.get('items') or []:
        before, after = [], []
        for line in _text(item.get('diffExcerpt')).splitlines():
            if line.startswith(('--- ', '+++ ', '@@')):
                continue
            if line.startswith('-'):
                before.append(line[1:])
            elif line.startswith('+'):
                after.append(line[1:])
        changes.append({'title': _text(item.get('title')) or '文档变化', 'before': before,
            'after': after, 'excerpted': bool(item.get('excerpted'))})
    return changes


def _result_sections(data):
    receipt = _mapping(data.get('receipt')) or data
    summary = _text(receipt.get('summary')) or _text(receipt.get('message'))
    requirements = receipt.get('changedRequirementIds') or receipt.get('requirementIds') or receipt.get('impactedRequirementIds')
    validation = _mapping(receipt.get('validation'))
    document = _mapping(receipt.get('document'))
    remaining = receipt.get('remaining') or receipt.get('nextSteps') or []
    substantive = bool(requirements or receipt.get('changedFiles') or document.get('title') or document.get('path')
        or remaining or receipt.get('error') or validation.get('errors') or validation.get('warnings'))
    if not summary:
        if not substantive:
            return [], ''
        summary = '已返回执行记录，请核对以下内容。'
    sections = [{'title': '完成情况', 'type': 'text', 'paragraphs': [summary]}]
    facts = []
    if receipt.get('status'):
        facts.append({'label': '状态', 'value': _status(receipt['status'])})
    if isinstance(requirements, list) and requirements:
        facts.append({'label': '涉及需求', 'value': f'{len(requirements)} 项'})
    if _text(document.get('title')):
        facts.append({'label': '文档', 'value': _text(document['title'])})
    check_scope = _text(validation.get('scope')) or _text(validation.get('checkedScope'))
    if isinstance(validation.get('scope'), list):
        check_scope = '、'.join(_text(item) for item in validation['scope'] if _text(item))
    checked = ('通过' if check_scope else '通过（记录未注明检查范围）') if validation.get('ok') is True \
        else '未通过' if validation.get('ok') is False else '未提供检查记录'
    facts.append({'label': '登记检查', 'value': checked})
    if check_scope:
        facts.append({'label': '检查范围', 'value': check_scope})
    sections.append({'title': '结果记录', 'type': 'facts', 'items': facts})
    changed_files = [_text(item) or _text(_mapping(item).get('title')) or _text(_mapping(item).get('path'))
                     for item in _list(receipt.get('changedFiles'))]
    if any(changed_files):
        sections.append({'title': '变更文件', 'type': 'list', 'items': [item for item in changed_files if item]})
    issues = []
    if receipt.get('error'):
        issues.append(_reason(receipt['error']) or '操作记录了错误，需在对话中核对。')
    for key in ('errors', 'warnings'):
        for issue in _list(validation.get(key)):
            issues.append(_reason(issue) or '检查记录包含未说明事项。')
    for item in _list(remaining):
        if _reason(item):
            issues.append(_reason(item))
    if issues:
        sections.append({'title': '待处理事项', 'type': 'list', 'items': issues})
    return sections, summary


def _enabled(snapshot, intent):
    return any(item.get('intent') == intent and item.get('enabled') is True for item in snapshot['actions'])


def _action(intent, verb, target=None):
    return {'intent': intent, 'verb': verb, 'target': target or {}}


def _demo_available(snapshot):
    basis = snapshot['basis'].get('demo')
    return (isinstance(basis, dict) and basis.get('contract') == 'prototype-flow.demo-edit-baseline/1'
        and isinstance(basis.get('baselineHash'), str) and bool(basis['baselineHash'])
        and isinstance(basis.get('project'), dict) and isinstance(basis.get('scope'), dict)
        and bool(basis['scope'])
        and basis['project'].get('id') == snapshot['project']['id']
        and basis.get('versionId') == 'working')


def prepare_card(snapshot, purpose=None, force_card=False, requested_scope='prd'):
    """Prepare readable card content without reading files or changing business data."""
    view, data = snapshot['scope']['view'], snapshot['data']
    purpose = purpose if purpose is not None else view if view in ('compare', 'result') else 'read'
    if purpose not in PURPOSES:
        raise FlowError('卡片目的无效')
    if requested_scope not in SCOPES:
        raise FlowError('请求范围无效')
    if snapshot['historical'] and purpose in ('edit', 'continue'):
        raise FlowError('历史内容只读，不能修改或继续任务', 409)
    title = _text(_mapping(data.get('requirement')).get('title')) or _text(_mapping(data.get('module')).get('title')) \
        or _text(_mapping(data.get('task')).get('title')) or snapshot['project']['name']
    if data.get('task') and not _text(data['task'].get('title')):
        title = _stage(data['task'].get('stage'))
    project = snapshot['project']['name']
    read_titles = {'requirement': f'了解{title}规则', 'module': f'查看{title}需求',
        'overview': '了解项目模块状态', 'history': '查看所选历史版本',
        'tasks': '查看已登记任务', 'task': f'查看{title}进展'}
    model = {'contract': 'prototype-flow.card/2', 'kind': 'read', 'purpose': purpose,
        'title': read_titles.get(view, title), 'context': f'{project} · {title}' if title != project else project,
        'sections': [], 'changes': [], 'primary': None, 'secondary': None, 'form': None,
        'source': {'label': '历史稿 · 只读' if snapshot['historical'] else '当前稿', 'observedAt': snapshot['observedAt']},
        'rendered': True}
    request_receipt = False
    if purpose == 'read':
        model['sections'] = _read_sections(snapshot)
        simple_task = data.get('task') and not _task_substantive(data['task'])
        simple_tasks = view == 'tasks' and len(data.get('items') or []) == 1 and not _task_substantive(data['items'][0])
        if not model['sections'] or simple_task or simple_tasks:
            model.update(rendered=False, text=(f"{title}：{_status((data.get('task') or (data.get('items') or [{}])[0]).get('status'))}。"
                if simple_task or simple_tasks else f'{title}：当前范围没有可展示内容。'))
        if data.get('requirement') and _enabled(snapshot, 'open-demo'):
            entry = data.get('demoEntry') or {}
            model['secondary'] = _action('open-demo', '查看 Demo', {'requirementIds': [data['requirement']['id']],
                'artifactId': entry.get('artifactId'), 'bindingIds': [entry['bindingId']] if entry.get('bindingId') else []})
    elif purpose == 'compare':
        if view != 'compare':
            raise FlowError('比较卡片需要版本比较快照')
        model['kind'] = 'compare'
        model['title'] = '核对 PRD 变化'
        model['changes'] = _changes(data)
        if not model['changes']:
            model.update(rendered=False, text=f'{title}：当前比较范围内没有 PRD 正文变化。')
    elif purpose == 'result':
        model['kind'] = 'result'
        model['title'] = '核对执行结果'
        receipt = _mapping(data.get('receipt')) or data
        request_receipt = receipt.get('kind') == 'request' or receipt.get('status') in ('copied', 'generated', 'issued', 'sent')
        if request_receipt:
            labels = {'copied': '复制', 'generated': '生成', 'issued': '发起', 'sent': '发送'}
            model.update(rendered=False, text=f"请求已{labels.get(receipt.get('status'), '准备')}，业务结果尚未返回。")
        else:
            model['sections'], summary = _result_sections(data)
            if not summary:
                model.update(rendered=False, text='结果已返回，未提供可展示的完成摘要。')
    else:
        model['kind'] = 'action'
        form = {'intent': 'inspect', 'targetKind': 'requirement', 'selection': 'multiple',
            'targets': [], 'selectedIds': [], 'instruction': None, 'scopes': [],
            'scope': requested_scope, 'requestedScope': requested_scope, 'target': {}}
        if purpose == 'edit':
            if view not in ('module', 'requirement') or not _enabled(snapshot, 'change'):
                raise FlowError('当前快照不支持修改请求', 409)
            records = [data['requirement']] if view == 'requirement' and data.get('requirement') else data.get('items') or []
            if not records:
                raise FlowError('当前范围没有可修改需求', 409)
            model['title'] = f'调整{title}规则'
            demo_available = _demo_available(snapshot)
            form.update(intent='change', selection='fixed' if view == 'requirement' else 'multiple',
                instruction={'required': True, 'label': '修改说明', 'placeholder': '说明要调整的规则，以及调整后的预期行为。'},
                scopes=[{'value': key, 'label': label} for key, label in SCOPES.items() if key == 'prd' or demo_available],
                target={'moduleId': snapshot['scope'].get('moduleId') or records[0].get('moduleId')})
            if view == 'requirement':
                form['selectedIds'] = [records[0]['id']]
            if requested_scope != 'prd' and not demo_available:
                form['scopeNote'] = '当前快照没有有效 Demo 基线，暂不能生成此范围请求。可明确改选 PRD，或先读取目标 Demo 的完整基线。'
            model['primary'] = _action('change', '修改', form['target'])
        elif purpose == 'continue':
            record = data.get('task') or {}
            run_id = snapshot['scope'].get('runId') or record.get('id')
            if view != 'task' or not run_id or not _enabled(snapshot, 'continue-run'):
                raise FlowError('当前任务不能继续', 409)
            records = [{'id': run_id, 'title': _text(record.get('title')) or _stage(record.get('stage')),
                'detail': f"{_status(record.get('status'))}{' · ' + _reason(record['error']) if record.get('error') and _reason(record['error']) else ''}"}]
            model['title'] = f'继续{title}'
            form.update(intent='continue-run', targetKind='run', selection='fixed', selectedIds=[run_id], target={'runId': run_id})
            model['primary'] = _action('continue-run', '继续任务', form['target'])
        else:
            if not _enabled(snapshot, 'inspect'):
                raise FlowError('当前快照不支持对象选择', 409)
            records = data.get('items') or []
            if not records:
                model.update(rendered=False, text=f'{title}：当前范围没有可选择对象。')
            if view in ('overview', 'history'):
                form['targetKind'] = 'module'
            elif view == 'tasks':
                form['targetKind'] = 'run'
            elif view == 'compare':
                form['targetKind'] = 'document'
            elif view != 'module':
                raise FlowError('此快照没有可选择的对象列表')
            form['selection'] = 'multiple' if form['targetKind'] == 'requirement' else 'single'
            form['target'] = {'moduleId': snapshot['scope'].get('moduleId')} if view == 'module' else {}
            model['primary'] = _action('inspect', '查看所选详情', form['target'])
            model['title'] = '选择要查看的对象'
        for record in records:
            item = {'id': record['id'], 'title': _text(record.get('title')) or
                (_stage(record.get('stage')) if form['targetKind'] == 'run' else '未命名对象')}
            if purpose == 'select' and form['targetKind'] == 'run' and record.get('status'):
                item['detail'] = _status(record['status'])
            elif purpose == 'continue':
                item['detail'] = record['detail']
            form['targets'].append(item)
        model['form'] = form
    page = _mapping(snapshot.get('page'))
    cursor = page.get('nextCursor')
    if (purpose in ('read', 'select', 'edit', 'compare') and view not in ('requirement', 'task', 'result')
            and isinstance(data.get('items'), list) and isinstance(cursor, str) and cursor):
        count = len(data['items'])
        total = page.get('total') if type(page.get('total')) is int else count
        model['source']['label'] += f' · 本页 {count} / 总计 {total} 项'
        if model['secondary'] is None and _enabled(snapshot, 'read-latest'):
            model['secondary'] = _action('read-latest', '后续内容', {'cursor': cursor})
    if force_card and not model['rendered'] and not request_receipt and not (model['kind'] == 'action' and not model['form']['targets']):
        model['rendered'] = True
        model['sections'] = [{'title': '', 'type': 'text', 'paragraphs': [model['text']]}]
    return model
