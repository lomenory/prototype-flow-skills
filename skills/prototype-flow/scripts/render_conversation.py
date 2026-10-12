#!/usr/bin/env python3
"""Render a versioned review snapshot as an optional, offline HTML fragment."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
from pf_core import FlowError

ASSETS = Path(__file__).resolve().parents[1] / 'assets/conversation-ui'


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('schemaVersion') != 1:
        raise FlowError('不支持的展示协议')
    for field in ('snapshotId', 'observedAt', 'versionId'):
        if not isinstance(snapshot.get(field), str) or not snapshot[field]:
            raise FlowError('展示快照缺少字段：' + field)
    for field in ('project', 'scope', 'basis', 'data', 'freshness'):
        if not isinstance(snapshot.get(field), dict):
            raise FlowError('展示快照字段无效：' + field)
    for field in ('id', 'name', 'rootHint'):
        if not isinstance(snapshot['project'].get(field), str):
            raise FlowError('项目身份字段无效')
    if not isinstance(snapshot.get('actions'), list) or any(not isinstance(a, dict) for a in snapshot['actions']):
        raise FlowError('展示动作字段无效')
    intents = {'inspect', 'change', 'read-latest', 'open-demo', 'open-workbench', 'compare', 'continue-run', 'export-module'}
    if any(a.get('intent') not in intents or type(a.get('enabled')) is not bool for a in snapshot['actions']):
        raise FlowError('展示动作意图或状态无效')
    if type(snapshot.get('historical')) is not bool or type(snapshot['project'].get('storedRevision')) is not int:
        raise FlowError('历史状态或落盘修订无效')
    for field in ('items', 'bindings'):
        values = snapshot['data'].get(field, [])
        if not isinstance(values, list) or any(not isinstance(i, dict) or not isinstance(i.get('id'), str) for i in values):
            raise FlowError('展示对象列表无效：' + field)
    for field, fingerprint in (('documents', 'revision'), ('requirements', 'hash')):
        values = snapshot['basis'].get(field, [])
        if not isinstance(values, list) or any(not isinstance(i, dict) or not isinstance(i.get('id'), str)
            or not isinstance(i.get(fingerprint), str) for i in values):
            raise FlowError('读取基线无效：' + field)
    if snapshot.get('scope', {}).get('view') not in ('overview', 'module', 'requirement', 'tasks', 'task', 'history', 'compare', 'result'):
        raise FlowError('展示视图无效')
    return snapshot


def render(snapshot, output, host_actions=False):
    validate_snapshot(snapshot)
    target = Path(output)
    if not target.is_absolute():
        raise FlowError('输出路径必须明确指定为绝对路径')
    if target.exists() or target.is_symlink():
        raise FlowError('请为新快照使用独立文件名，不覆盖旧卡片', 409)
    root_id = 'pf-review-' + uuid.uuid4().hex
    payload = json.dumps({'snapshot': snapshot, 'hostActions': bool(host_actions)}, ensure_ascii=False)
    # JSON is data, never source HTML. In particular close-script strings remain inert.
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    markup = (ASSETS / 'fragment.html').read_text('utf-8')
    markup = markup.replace('__ROOT_ID__', root_id)
    markup = markup.replace('__STYLE__', (ASSETS / 'style.css').read_text('utf-8'))
    markup = markup.replace('__SCRIPT__', (ASSETS / 'conversation.js').read_text('utf-8').replace('__ROOT_ID__', root_id))
    markup = markup.replace('__SNAPSHOT_JSON__', payload)  # Insert source data last; never expand its marker-like text.
    size = len(markup.encode('utf-8'))
    if size > 256 * 1024:
        raise FlowError('卡片超过 256 KiB，请缩小查询范围或分页', 413)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        stream.write(markup)
    return {'path': str(target), 'bytes': size, 'snapshotId': snapshot['snapshotId'],
            'hostActions': host_actions}


def main():
    parser = argparse.ArgumentParser(description='渲染可选对话卡片；独立 HTML 默认只复制请求')
    parser.add_argument('--file', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--host-actions', action='store_true', help='仅用于已完成真实宿主验收的内嵌 reference')
    args = parser.parse_args()
    try:
        result = render(json.loads(Path(args.file).read_text('utf-8')), args.output, args.host_actions)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (FlowError, ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc), 'status': getattr(exc, 'status', 400)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
