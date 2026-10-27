#!/usr/bin/env python3
"""Prototype Flow project maintenance. AI writing/generation stays in the Skill."""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True

from pf_core import FlowError, ProjectStore


# Lifecycle writes can opt into one reusable, read-only requirement map.
# Queries and cloud operations keep their existing side-effect boundaries.
REQUIREMENT_MAP_COMMANDS = frozenset({
    'init', 'intake', 'save', 'module', 'module-stage', 'source', 'relations',
    'artifact', 'framework', 'requirement', 'refresh', 'restore',
    'run-start', 'run-resume', 'run-finish', 'demo-edit', 'demo-save',
    'demo-prepare', 'demo-finalize', 'demo-freeze', 'demo-restore',
})


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def selected(value, *keys):
    return {key: value[key] for key in keys if key in value}


def document_summary(document):
    result = selected(document, 'id', 'path', 'title', 'moduleId', 'revision', 'status', 'readOnly')
    if 'content' in document:
        result['contentBytes'] = len(document['content'].encode('utf-8'))
    return result


def module_summary(module):
    return selected(module, 'id', 'title', 'documentId', 'documentPath', 'stage', 'stageUpdatedAt')


def state_summary(state):
    """Keep local CLI writes small; the workbench still receives complete state."""
    result = selected(state, 'historical', 'versionId', 'maintenanceStatus',
                      'changedRequirementIds', 'newRequirementIds', 'removedRequirementIds', 'operation')
    result['project'] = selected(state['project'], 'id', 'name', 'revision', 'libraryRoot', 'mode',
                                 'restoredFrom', 'restoreBackup')
    result['modules'] = [module_summary(module) for module in state['project'].get('modules', [])]
    result['documents'] = [selected(document, 'id', 'title', 'moduleId', 'path', 'revision')
                           for document in state['documents']]
    result['counts'] = {
        'modules': len(state['project'].get('modules', [])),
        'documents': len(state['documents']), 'requirements': len(state['requirements']),
        'sources': len(state.get('sources', {}).get('items', [])),
        'artifacts': len(state.get('artifacts', {}).get('items', [])),
    }
    result['frameworks'] = {'currentFrameworkId': state.get('frameworks', {}).get('currentFrameworkId'),
                            'count': len(state.get('frameworks', {}).get('items', []))}
    return result


def compact_result(command, value):
    if command in ('init', 'refresh', 'restore'):
        return state_summary(value)
    if command == 'demo-assemble':
        result = selected(value, 'runId', 'draftId', 'output', 'savePath', 'reportPath')
        result.update(assembledOnly=True, **selected(value['validationReport'],
            'proposedReverificationBindingIds', 'unverifiedBindingIds', 'verificationPerformed'))
        return result
    if command in ('save', 'intake'):
        result = selected(value, 'impactedRequirementIds', 'requirementIds', 'sourceId',
                          'maintenanceStatus', 'validation')
        result['document'] = document_summary(value['document'])
        if 'module' in value:
            result['module'] = module_summary(value['module'])
        if 'requirementIds' in value:
            result['counts'] = {'requirements': len(value['requirementIds'])}
        return result
    if command == 'module':
        return document_summary(value)
    if command == 'module-stage':
        return module_summary(value)
    if command == 'relations':
        return {'counts': {key: len(value.get(key, [])) for key in ('flows', 'bindings', 'supersessions')},
                'ids': {key: [item['id'] for item in value.get(key, [])]
                        for key in ('flows', 'bindings', 'supersessions')}}
    if command in ('artifact', 'demo-freeze'):
        result = selected(value, 'id', 'title', 'path', 'entryHtml', 'status', 'runId', 'inputRevision',
                          'frameworkId', 'baseArtifactId', 'sourceDemoPath', 'activated',
                          'kind', 'draftRevision', 'frozenFrom', 'reused', 'validation')
        result['counts'] = {'requirements': len(value.get('requirementHashes', {})),
                            'documents': len(value.get('documentHashes', {})),
                            'files': len(value.get('fileHashes', {}))}
        return result
    if command == 'framework':
        return selected(value, 'id', 'title', 'path', 'entryHtml', 'basedOn', 'sourceArtifactId', 'changeSummary')
    if command == 'snapshot':
        result = selected(value, 'id', 'name', 'description', 'createdAt', 'inputRevision', 'validation')
        result['path'] = 'versions/' + value['id']
        result['counts'] = {'modules': len(value.get('modules', [])), 'files': len(value.get('files', {}))}
        return result
    if command in ('run-start', 'run-finish', 'run-resume', 'demo-edit'):
        result = selected(value, 'id', 'stage', 'status', 'inputRevision', 'inputPath', 'requirementIds',
                          'createdAt', 'finishedAt', 'error', 'resumedFrom', 'recoveredOutputs', 'sharedDocumentIds', 'contextScope',
                          'change', 'metrics', 'measurements', 'changedFiles', 'draft',
                          'draftId', 'artifactId', 'draftRevision', 'beforeRevision', 'path',
                          'kind', 'checkpointArtifactId', 'recoveryCheckpoint', 'recoveryRevision',
                          'artifactTitle', 'scopeExpandedToAll', 'affectedBindingIds', 'affectedModules', 'bindings', 'saveTemplate')
        result['counts'] = {'documents': len(value.get('documents', [])),
                            'outputs': len(value.get('outputs', []))}
        if value.get('framework'):
            result['framework'] = selected(value['framework'], 'id', 'path', 'entryHtml')
            result['baseArtifact'] = selected(value.get('baseArtifact') or {}, 'id', 'path', 'entryHtml')
            result.update(frameworkBaselineId=value.get('frameworkBaselineId'),
                          artifactBaselineId=value.get('artifactBaselineId'))
        return result
    return value


def error_summary(value):
    """Keep conflict identities and baselines without echoing both PRD bodies."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in ('content', 'draft') and isinstance(item, str):
                result[key + 'Bytes'] = len(item.encode('utf-8'))
            else:
                result[key] = error_summary(item)
        return result
    if isinstance(value, list):
        return [error_summary(item) for item in value]
    return value


def parser():
    p = argparse.ArgumentParser(description='Prototype Flow：本地 PRD、Demo 关联、版本和飞书单向同步')
    sub = p.add_subparsers(dest='command', required=True)

    deps = sub.add_parser('dependencies', help='检查依赖、安装缺失 Skill，或显式备份升级')
    deps.add_argument('--stage', choices=['core', 'prd', 'demo', 'feishu', 'all'], default='core')
    deps.add_argument('--project', help='目标项目目录，用于查找项目内已有 Skill')
    deps.add_argument('--dest', help='指定唯一查找和安装目录；也可设置 PROTOTYPE_FLOW_SKILLS_DIR')
    deps.add_argument('--check', action='store_true', help='只检查，不访问网络或写入文件')
    deps.add_argument('--upgrade', action='store_true', help='按固定依赖锁升级；须明确目标目录，替换前完整备份')

    def command(name, description):
        cmd = sub.add_parser(name, help=description, description=description)
        cmd.add_argument('root', help='项目根目录')
        cmd.add_argument('--full', action='store_true', help='输出完整结果；默认省略正文和项目明细，document 始终保留全文')
        if name in REQUIREMENT_MAP_COMMANDS:
            presentation = cmd.add_mutually_exclusive_group()
            presentation.add_argument('--requirement-map', action='store_true',
                                      help='本次写入后准备或复用需求图服务并返回入口；默认仅执行数据操作')
            presentation.add_argument('--no-requirement-map', action='store_false', dest='requirement_map',
                                      help='兼容原参数：本次不准备需求图服务；不停止已打开的图')
            cmd.set_defaults(requirement_map=False)
        return cmd

    cmd = command('init', '初始化或接入项目，不自动连接飞书')
    cmd.add_argument('--name', required=True)
    cmd.add_argument('--mode', choices=['local', 'feishu'], default='local')
    cmd.add_argument('--library-root', default='prd-library')
    cmd.add_argument('--maintainer-path', help='兼容旧配置参数；当前使用内置文档库维护')
    cmd.add_argument('--empty', action='store_true', help='新项目不创建占位总览，供随后 intake 一次入库')
    cmd = command('intake', '一次保存新资料、完整 PRD 和批量需求，并维护和校验')
    cmd.add_argument('--file', required=True, help='包含 title、content、requirements 和可选 source 的 JSON')
    cmd = command('serve', '按需启动本机项目工作台；Demo 点击时独立预览；Ctrl+C 仅停止工作台')
    cmd.add_argument('--port', type=int, default=0)
    cmd.add_argument('--preview-port', type=int, default=0)
    cmd.add_argument('--reuse', action='store_true', help='验证并复用同项目的现有服务；没有可用服务时启动')
    cmd = command('requirement-map', '准备或复用本地实时需求图，并读取同款对话快照')
    cmd.add_argument('--module')
    cmd.add_argument('--requirement')
    cmd.add_argument('--version', help='历史版本保持固定快照，不跟随当前稿')
    cmd.add_argument('--port', type=int, default=0)
    cmd.add_argument('--stop', action='store_true', help='停止本项目需求图与共用工作台服务；Demo 预览独立保留')
    cmd = command('state', '读取项目摘要或指定任务/产物；--full 返回所选范围完整记录，支持历史版本')
    cmd.add_argument('--version')
    cmd.add_argument('--section', choices=['runs', 'artifacts', 'bindings'], help='只读取任务、产物或页面绑定，省略无关 PRD 正文')
    cmd.add_argument('--id', help='只读取指定任务、产物或绑定；必须同时提供 --section')
    cmd = command('review-state', '按范围读取可选对话卡片快照；不保存或启动服务')
    cmd.add_argument('--view', choices=['overview', 'module', 'requirement', 'requirement-map', 'tasks', 'task', 'history', 'compare'], default='overview')
    cmd.add_argument('--module')
    cmd.add_argument('--requirement')
    cmd.add_argument('--run')
    cmd.add_argument('--version')
    cmd.add_argument('--from', dest='from_version')
    cmd.add_argument('--to', dest='to_version', default='working')
    cmd.add_argument('--limit', type=int, default=20)
    cmd.add_argument('--cursor')
    cmd.add_argument('--query')
    cmd = command('preview', '独立启动或复用只读 Demo 预览，不打开工作台')
    cmd.add_argument('--reuse', action='store_true')
    cmd.add_argument('--port', type=int, default=0)
    cmd = command('service', '查看本项目正在运行的服务版本；显式 --restart 才重启服务')
    cmd.add_argument('--kind', choices=['workbench', 'preview'], default='workbench')
    cmd.add_argument('--restart', action='store_true', help='重启准确匹配本项目的服务，默认保留原端口')
    cmd.add_argument('--port', type=int, default=0, help='仅重启时可指定端口')
    cmd = command('demo-entry', '从已运行的独立预览解析准确 Demo URL')
    target = cmd.add_mutually_exclusive_group(required=True)
    target.add_argument('--current', action='store_true', help='稳定的当前 Demo 入口，附当前稿、PRD 与冻结信息')
    target.add_argument('--requirement')
    target.add_argument('--binding')
    target.add_argument('--artifact')
    cmd.add_argument('--within-artifact')
    cmd.add_argument('--version')
    cmd = command('export-module', '只读导出已确认模块的完整交付包')
    cmd.add_argument('id')
    cmd.add_argument('--output', required=True)
    cmd.add_argument('--version')
    cmd.add_argument('--resource-manifest', help='旧 Demo 的只读运行资源声明 JSON，按最终冻结 Demo ID 放入 artifacts 映射')
    cmd.add_argument('--format', choices=['project_bundle', 'single_html'], default='project_bundle',
                     help='project_bundle 为原工程 ZIP；single_html 为不含 PRD 的单 HTML 演示版')
    cmd = command('storage', '检查内容存储、显式迁移旧项目、展开资源或导出独立 Demo 文件夹')
    cmd.add_argument('--action', required=True, choices=['status', 'migrate', 'materialize', 'export'])
    cmd.add_argument('--group', help='materialize 使用的存储组编号，从 status 结果读取')
    cmd.add_argument('--artifact', help='export 使用的已登记 Demo 产物 ID')
    cmd.add_argument('--output', help='展开或导出的绝对目标目录；export 必填，已有不同内容拒绝覆盖')
    cmd.add_argument('--apply', action='store_true', help='仅 migrate：校验并启用内容存储；默认只返回迁移计划')
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
    cmd = command('framework', '登记不可变共享框架候选；随已验证 Demo 一起启用')
    cmd.add_argument('--file', required=True)
    cmd = command('demo-edit', '固定本轮需求并接续同一 Demo 工作稿；不创建完整历史版本')
    scope = cmd.add_mutually_exclusive_group()
    scope.add_argument('--requirements', nargs='+', help='本次直接修改的需求 ID')
    scope.add_argument('--bindings', nargs='+', help='从指定页面绑定推导本次需求范围')
    scope.add_argument('--all-requirements', action='store_true', help='明确选择全项目需求')
    cmd.add_argument('--documents', nargs='*', help='额外影响本次工作稿的共享规则文档 ID')
    cmd.add_argument('--change-file', help='本次修改范围 JSON：tier、summary、affectedBindingIds')
    cmd.add_argument('--title', help='本轮完成后的产物标题；随 demo-save 成功原子更新，省略时保留当前标题')
    cmd.add_argument('--expected-file', help='Demo 读取基线 JSON；在同一事务内、创建任务或工作稿前核对')
    cmd = command('demo-save', '保存工作稿修订、更新受影响证据并结束本轮任务')
    cmd.add_argument('id', help='demo-edit 返回的任务 ID')
    cmd.add_argument('--file', required=True, help='保存内容 JSON；artifact、bindings、bindingPatches、flows、moduleStages、outputs、measurements 均可选')
    cmd = command('demo-assemble', '从本轮实际证据组装保存候选；不保存工作稿、不补造验证结果')
    cmd.add_argument('id', help='demo-edit 返回的任务 ID')
    cmd.add_argument('--file', required=True, help='报告路径、截图映射和可选摘要 JSON')
    cmd.add_argument('--output', required=True, help='项目 local_tasks/ 下尚不存在的目录，写入 save.json 与 validation-report.json')
    cmd = command('demo-freeze', '将已保存工作稿冻结为独立完整 Demo 版本')
    cmd.add_argument('--artifact', help='工作稿 ID；默认当前工作稿')
    cmd.add_argument('--title', help='冻结版本的可读标题')
    cmd = command('demo-restore', '从恢复记录还原工作稿，形成新的工作稿修订')
    cmd.add_argument('id', help='工作稿 ID')
    cmd.add_argument('--revision', required=True, type=int, help='要恢复的工作稿修订号')
    cmd = command('demo-prepare', '从任务固定的完整 Demo 和框架复制新的工作目录')
    cmd.add_argument('id', help='固定输入的任务 ID')
    cmd.add_argument('--path', required=True, help='尚不存在的 demos/<新目录>')
    cmd.add_argument('--from-output', help='从该续作任务 recoveredOutputs 中的目录继续准备完整 Demo')
    cmd = command('demo-finalize', '一次登记完整产物、更新关联、定向检查并结束任务；失败回滚登记')
    cmd.add_argument('id', help='当前运行中的 Demo 任务 ID')
    cmd.add_argument('--file', required=True, help='artifact、bindings、flows 和可选 measurements JSON')
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
    cmd = command('validate', '检查当前稿稳定 ID、关联与资源；历史版本在读取和恢复时校验')
    cmd.add_argument('--stage', choices=['all', 'prd'], default='all',
                     help='prd 仅检查 PRD 来源、引用和稳定 ID；默认 all 保留完整检查')
    cmd.add_argument('--artifacts', nargs='+', help='只检查这些 Demo、相关绑定与必要依赖')
    cmd.add_argument('--bindings', nargs='+', help='只检查这些绑定及其 Demo，不附带同 Demo 的其他绑定')
    command('refresh', '发现外部修改并刷新文档库和需求索引')
    cmd = command('run-start', '固定一次 AI 工作的输入修订和需求范围')
    cmd.add_argument('--stage', required=True)
    cmd.add_argument('--requirements', nargs='*')
    cmd.add_argument('--documents', nargs='*', help='额外影响本次产物的共享规则文档 ID')
    cmd.add_argument('--full-context', action='store_true', help='固定全项目文档与资源；默认只固定所选需求及依赖的上下文')
    cmd.add_argument('--framework', help='本次使用的框架版本；默认当前版本或唯一首版候选')
    cmd.add_argument('--base-artifact', help='保留业务成果的完整 Demo；默认当前版本或唯一已有产物')
    cmd.add_argument('--base-demo', help='首次接入尚未登记的 demos/<目录>；与 --base-artifact 互斥')
    cmd.add_argument('--base-entry', default='index.html', help='首次接入 Demo 的 HTML 入口，默认 index.html')
    cmd.add_argument('--change-file', help='本次修改范围 JSON：tier、summary、affectedBindingIds')
    cmd = command('run-resume', '从当前或历史任务固定输入创建独立续作，不覆盖原任务')
    cmd.add_argument('id')
    cmd.add_argument('--version', help='从指定历史版本读取任务；省略时读取当前任务')
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
        cmd.add_argument('--full', action='store_true', help='错误时保留完整调试明细')
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
            result = ensure_dependencies(args.stage, args.project, args.dest, args.check,
                                         upgrade=args.upgrade)
            output(result)
            return 0 if result['ok'] else 1
        store = ProjectStore(Path(args.root).expanduser().resolve())
        started = time.perf_counter()
        command = args.command
        if command == 'init':
            result = store.init(args.name, args.mode, args.library_root, args.maintainer_path,
                                create_overview=not args.empty)
        elif command == 'intake':
            result = store.intake(read_json(args.file))
        elif command == 'serve':
            from pf_server import WorkbenchServer, ServiceRegistry
            registry = ServiceRegistry(store.root)
            with registry.lock():
                existing = registry.reuse() if args.reuse else None
                if existing:
                    output(existing)
                    return 0
                with store._transaction(read_only=True):
                    store._project()  # Identity only; management data is read on demand.
                server = WorkbenchServer(store, args.port, args.preview_port)
                info = server.start()
                try:
                    registry.publish(server)
                except Exception:
                    server.close()
                    raise
            event = threading.Event()
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda *_: event.set())
            output(info)
            try:
                while not event.wait(1):
                    pass
            finally:
                server.close()
                with registry.lock():
                    registry.forget(server.instance_id)
            return 0
        elif command == 'preview':
            from pf_server import preview
            result = preview(store.root, reuse=args.reuse, port=args.port)
        elif command == 'service':
            from pf_server import reconnect_service, restart_service
            if args.port and not args.restart:
                raise FlowError('--port 只能与 --restart 一起使用')
            result = (restart_service(store.root, service_kind=args.kind, port=args.port) if args.restart
                      else reconnect_service(store.root, service_kind=args.kind))
        elif command == 'requirement-map':
            if args.stop:
                if args.module or args.requirement or args.version or args.port:
                    raise FlowError('--stop 不能与范围、历史版本或端口参数同时使用')
                from pf_server import stop_workbench
                result = {'status': 'stopped' if stop_workbench(store.root) else 'not-running',
                          'projectRoot': str(store.root), 'autoUpdate': False}
            else:
                from pf_map_flow import requirement_map_entry
                result = requirement_map_entry(store, module_id=args.module,
                                               requirement_id=args.requirement,
                                               version=args.version, port=args.port)
        elif command == 'demo-entry':
            from pf_server import demo_entry
            if args.within_artifact and not args.binding:
                raise FlowError('--within-artifact 只能与 --binding 一起使用')
            result = demo_entry(store, version=args.version, requirement_id=args.requirement,
                                binding_id=args.binding, artifact_id=args.artifact,
                                within_artifact=args.within_artifact, current=args.current)
        elif command == 'review-state':
            from pf_review import review_state
            result = review_state(store, view=args.view, module_id=args.module,
                requirement_id=args.requirement, run_id=args.run, version=args.version,
                from_version=args.from_version, to_version=args.to_version,
                limit=args.limit, cursor=args.cursor, query=args.query)
        elif command == 'export-module':
            from pf_delivery import export_module
            result = export_module(store, args.id, args.output, args.version,
                                   resource_manifest=read_json(args.resource_manifest) if args.resource_manifest else None,
                                   delivery_format=args.format)
        elif command == 'storage':
            if args.apply and args.action != 'migrate':
                raise FlowError('--apply 只能与 storage --action migrate 一起使用')
            if args.group is not None and args.action != 'materialize':
                raise FlowError('--group 只能与 storage --action materialize 一起使用')
            if args.artifact is not None and args.action != 'export':
                raise FlowError('--artifact 只能与 storage --action export 一起使用')
            if args.output is not None:
                if args.action not in ('materialize', 'export'):
                    raise FlowError('--output 只能与 storage --action materialize|export 一起使用')
                if not Path(args.output).expanduser().is_absolute():
                    raise FlowError('--output 需要绝对目标目录')
            if args.action == 'status':
                result = store.storage_status()
            elif args.action == 'migrate':
                result = store.migrate_storage(execute=args.apply)
            elif args.action == 'materialize':
                if not args.group:
                    raise FlowError('storage --action materialize 需要 --group，编号从 status 结果读取')
                result = store.materialize_storage(args.group, output=args.output)
            else:
                if not args.artifact or not args.output:
                    raise FlowError('storage --action export 需要 --artifact 和 --output')
                result = store.export_demo(args.artifact, args.output)
        elif command == 'state':
            if args.id is not None and not args.section:
                raise FlowError('state --id requires --section runs, artifacts or bindings')
            if args.section:
                from pf_queries import query_state
                result = query_state(store, args.section, args.id, args.version, full=args.full)
            else:
                result = store.state(args.version, summary=not args.full)
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
        elif command == 'framework':
            result = store.register_framework(read_json(args.file))
        elif command == 'demo-edit':
            change = read_json(args.change_file) if args.change_file else None
            inferred = isinstance(change, dict) and bool(change.get('affectedBindingIds'))
            if not (args.requirements or args.bindings or args.all_requirements or inferred):
                raise FlowError('demo-edit 需要明确范围：使用 --requirements、--bindings、change.affectedBindingIds 或 --all-requirements')
            result = store.edit_demo(args.requirements, args.documents,
                                     change=change, binding_ids=args.bindings,
                                     all_requirements=args.all_requirements,
                                     artifact_title=args.title,
                                     expected=read_json(args.expected_file) if args.expected_file else None)
        elif command == 'demo-save':
            result = store.save_demo(args.id, read_json(args.file))
        elif command == 'demo-assemble':
            from pf_evidence_assembly import assemble_evidence
            result = assemble_evidence(store, args.id, read_json(args.file), output=args.output)
        elif command == 'demo-freeze':
            result = store.freeze_demo(args.artifact, args.title)
        elif command == 'demo-restore':
            result = store.restore_demo_revision(args.id, args.revision)
        elif command == 'demo-prepare':
            result = store.prepare_demo(args.id, args.path, recovered_output=args.from_output)
        elif command == 'demo-finalize':
            result = store.finalize_demo(args.id, read_json(args.file))
        elif command == 'requirement':
            result = store.transform_requirements(args.operation, args.ids,
                read_json(args.parts_file) if args.parts_file else None,
                args.target_module, args.base_revision, summary=not args.full)
        elif command == 'snapshot':
            result = store.snapshot(args.name, args.description)
        elif command == 'versions':
            result = store.versions()
        elif command == 'compare':
            result = store.compare(args.from_version, args.to_version)
        elif command == 'restore':
            result = store.restore(args.version)
        elif command == 'validate':
            result = store.validate(stage=args.stage, artifact_ids=args.artifacts, binding_ids=args.bindings)
            result['commandMetrics'] = dict(store.metrics, elapsedMs=round((time.perf_counter() - started) * 1000, 3))
            output(result)
            return 0 if result.get('ok') else 1
        elif command == 'refresh':
            result = store.refresh()
        elif command == 'run-start':
            result = store.start_run(args.stage, args.requirements, args.documents, full_context=args.full_context,
                                     framework_id=args.framework, base_artifact_id=args.base_artifact,
                                     base_demo_path=args.base_demo, base_entry=args.base_entry,
                                     change=read_json(args.change_file) if args.change_file else None)
        elif command == 'run-resume':
            result = store.resume_run(args.id, args.version)
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
        result = result if args.full else compact_result(command, result)
        if command in REQUIREMENT_MAP_COMMANDS and args.requirement_map:
            from pf_map_flow import default_requirement_map
            result['requirementMap'] = default_requirement_map(store)
        if isinstance(result, dict) and command in ('run-start', 'demo-prepare', 'artifact', 'relations',
                                                   'run-finish', 'demo-finalize', 'demo-edit', 'demo-save',
                                                   'demo-freeze', 'demo-restore', 'review-state', 'preview', 'demo-entry',
                                                   'requirement-map', 'demo-assemble', 'service', 'storage'):
            result['commandMetrics'] = dict(store.metrics, elapsedMs=round((time.perf_counter() - started) * 1000, 3))
        output(result)
        return 0
    except (FlowError, ValueError, OSError) as exc:
        details = getattr(exc, 'details', None)
        output({'error': str(exc), 'status': getattr(exc, 'status', 400),
                'details': details if getattr(args, 'full', False) else error_summary(details)})
        return 1


if __name__ == '__main__':
    sys.exit(main())
