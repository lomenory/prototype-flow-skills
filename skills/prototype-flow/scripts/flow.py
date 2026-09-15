#!/usr/bin/env python3
"""Prototype Flow project maintenance. AI writing/generation stays in the Skill."""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

sys.dont_write_bytecode = True

from pf_core import FlowError, ProjectStore


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def parser():
    p = argparse.ArgumentParser(description='Prototype Flow：本地 PRD、Demo 关联、版本和飞书单向同步')
    sub = p.add_subparsers(dest='command', required=True)

    deps = sub.add_parser('dependencies', help='检查依赖并从 GitHub 安装缺失的 Skill')
    deps.add_argument('--stage', choices=['core', 'prd', 'demo', 'feishu', 'all'], default='core')
    deps.add_argument('--project', help='目标项目目录，用于查找项目内已有 Skill')
    deps.add_argument('--dest', help='指定唯一查找和安装目录；默认复用已安装 Skill')
    deps.add_argument('--check', action='store_true', help='只检查，不访问网络或写入文件')

    def command(name, description):
        cmd = sub.add_parser(name, help=description, description=description)
        cmd.add_argument('root', help='项目根目录')
        return cmd

    cmd = command('init', '初始化或接入项目，不自动连接飞书')
    cmd.add_argument('--name', required=True)
    cmd.add_argument('--mode', choices=['local', 'feishu'], default='local')
    cmd.add_argument('--library-root', default='prd-library')
    cmd.add_argument('--maintainer-path', help='现有 prd-doc-maintainer Skill 路径或脚本路径')
    cmd = command('serve', '启动本机工作台与独立只读 Demo 预览；Ctrl+C 停止')
    cmd.add_argument('--port', type=int, default=0)
    cmd.add_argument('--preview-port', type=int, default=0)
    cmd = command('state', '读取项目状态；支持历史版本')
    cmd.add_argument('--version')
    cmd = command('document', '读取完整 PRD 及保存基线')
    cmd.add_argument('id')
    cmd.add_argument('--version')
    cmd = command('save', '基于指定修订保存 PRD，冲突时保留双方内容')
    cmd.add_argument('id')
    cmd.add_argument('--file', required=True)
    cmd.add_argument('--base-revision', required=True)
    cmd = command('module', '新增模块和 PRD')
    cmd.add_argument('--title', required=True)
    cmd.add_argument('--id')
    cmd = command('module-stage', '记录模块工作阶段；已确认需要明确的用户确认记录')
    cmd.add_argument('id')
    cmd.add_argument('--stage', required=True, choices=['intake', 'draft', 'review', 'demo', 'validation', 'confirmed'])
    cmd.add_argument('--evidence-file', help='阶段依据 JSON；confirmed 需要 type=user-confirmation、summary 和 source')
    cmd = command('source', '登记资料出处和可选的文本提取结果')
    cmd.add_argument('--label', required=True)
    cmd.add_argument('--kind', default='document')
    cmd.add_argument('--locator', required=True)
    cmd.add_argument('--file', help='已提取为 UTF-8 的正文，不把未读取的二进制资料伪报为已分析')
    cmd.add_argument('--id')
    cmd = command('relations', '校验并保存需求、流程与截图关联')
    cmd.add_argument('--file', required=True)
    cmd = command('artifact', '注册依据固定修订生成的完整 Demo')
    cmd.add_argument('--file', required=True)
    cmd = command('requirement', '显式新增、拆分、合并、移动或移除需求')
    cmd.add_argument('--operation', required=True, choices=['add', 'split', 'merge', 'move', 'remove'])
    cmd.add_argument('--ids', nargs='*', default=[])
    cmd.add_argument('--parts-file')
    cmd.add_argument('--target-module')
    cmd.add_argument('--base-revision', type=int, help='当前 project.revision 整数；文档 save 使用全文修订字符串')
    cmd = command('snapshot', '保存完整、不可变的项目版本')
    cmd.add_argument('--name', required=True)
    cmd.add_argument('--description', default='')
    command('versions', '列出项目历史版本')
    cmd = command('compare', '比较历史版本、需求变化、正文和截图')
    cmd.add_argument('--from', dest='from_version', required=True)
    cmd.add_argument('--to', dest='to_version', default='working')
    cmd = command('restore', '基于历史创建工作修订，保留当前飞书同步记录')
    cmd.add_argument('version')
    command('validate', '检查稳定 ID、关联、资源和版本一致性')
    command('refresh', '发现外部修改并刷新文档库和需求索引')
    cmd = command('run-start', '固定一次 AI 工作的输入修订和需求范围')
    cmd.add_argument('--stage', required=True)
    cmd.add_argument('--requirements', nargs='*')
    cmd = command('run-finish', '记录实际完成项和失败项，不伪造验证证据')
    cmd.add_argument('id')
    cmd.add_argument('--status', required=True, choices=['completed', 'partial', 'failed', 'blocked'])
    cmd.add_argument('--outputs-file')
    cmd.add_argument('--error')

    fs = sub.add_parser('feishu', help='飞书单向展示同步；实际写入仅由 sync --execute 触发')
    fsub = fs.add_subparsers(dest='feishu_command', required=True)
    for name in ('configure', 'bind', 'prepare', 'sync', 'status'):
        cmd = fsub.add_parser(name)
        cmd.add_argument('root')
        cmd.add_argument('--identity', choices=['user', 'bot'], default='user')
        if name == 'configure':
            cmd.add_argument('--parent-token')
            cmd.add_argument('--navigation-title')
        elif name == 'bind':
            cmd.add_argument('document_id')
            cmd.add_argument('--remote', required=True)
            cmd.add_argument('--accept-existing', action='store_true')
        elif name == 'prepare':
            cmd.add_argument('--documents', nargs='*')
            cmd.add_argument('--include-navigation', action='store_true')
        elif name == 'sync':
            cmd.add_argument('plan_id')
            cmd.add_argument('--execute', action='store_true', help='执行计划中的云端写入；仅在该范围已获用户授权时使用')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'dependencies':
            from pf_dependencies import ensure_dependencies
            result = ensure_dependencies(args.stage, args.project, args.dest, args.check)
            output(result)
            return 0 if result['ok'] else 1
        store = ProjectStore(Path(args.root).expanduser().resolve())
        command = args.command
        if command == 'init':
            result = store.init(args.name, args.mode, args.library_root, args.maintainer_path)
        elif command == 'serve':
            from pf_server import WorkbenchServer
            store.state()  # Fail early if the project was not initialized.
            server = WorkbenchServer(store, args.port, args.preview_port)
            event = threading.Event()
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda *_: event.set())
            output(server.start())
            try:
                while not event.wait(1):
                    pass
            finally:
                server.close()
            return 0
        elif command == 'state':
            result = store.state(args.version)
        elif command == 'document':
            result = store.document(args.id, args.version)
        elif command == 'save':
            result = store.save_document(args.id, Path(args.file).read_text('utf-8'), args.base_revision)
        elif command == 'module':
            result = store.add_module(args.title, args.id)
        elif command == 'module-stage':
            result = store.set_module_stage(args.id, args.stage, read_json(args.evidence_file) if args.evidence_file else None)
        elif command == 'source':
            content = Path(args.file).read_text('utf-8') if args.file else None
            result = store.add_source(args.label, args.kind, args.locator, content, args.id)
        elif command == 'relations':
            result = store.update_relations(read_json(args.file))
        elif command == 'artifact':
            result = store.register_artifact(read_json(args.file))
        elif command == 'requirement':
            result = store.transform_requirements(args.operation, args.ids,
                read_json(args.parts_file) if args.parts_file else None,
                args.target_module, args.base_revision)
        elif command == 'snapshot':
            result = store.snapshot(args.name, args.description)
        elif command == 'versions':
            result = store.versions()
        elif command == 'compare':
            result = store.compare(args.from_version, args.to_version)
        elif command == 'restore':
            result = store.restore(args.version)
        elif command == 'validate':
            result = store.validate()
            output(result)
            return 0 if result.get('ok') else 1
        elif command == 'refresh':
            result = store.refresh()
        elif command == 'run-start':
            result = store.start_run(args.stage, args.requirements)
        elif command == 'run-finish':
            result = store.finish_run(args.id, args.status,
                read_json(args.outputs_file) if args.outputs_file else None, args.error)
        elif command == 'feishu':
            from pf_feishu import FeishuSync, LarkCLITransport
            sync = FeishuSync(store, LarkCLITransport(identity=args.identity))
            action = args.feishu_command
            if action == 'configure':
                result = sync.configure(args.parent_token, args.navigation_title)
            elif action == 'bind':
                result = sync.bind(args.document_id, args.remote, args.accept_existing)
            elif action == 'prepare':
                result = sync.prepare(args.documents, args.include_navigation)
            elif action == 'sync':
                result = sync.sync(args.plan_id, allow_write=args.execute)
            else:
                result = sync.status()
        else:
            raise FlowError('未知操作')
        output(result)
        return 0
    except (FlowError, ValueError, FileNotFoundError, PermissionError) as exc:
        output({'error': str(exc), 'details': getattr(exc, 'details', None)})
        return 1


if __name__ == '__main__':
    sys.exit(main())
