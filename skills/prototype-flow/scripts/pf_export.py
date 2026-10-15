"""Read-only delivery packages for explicitly confirmed modules."""
from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from pf_core import FlowError, markdown_links


def _package_path(relative):
    path = PurePosixPath(relative)
    if '\\' in relative or path.is_absolute() or not path.parts or '..' in path.parts:
        raise FlowError('打包资源路径无效：' + relative, 403)
    return path


def _resource_overrides(value, selected):
    if value is None:
        return {}
    if (not isinstance(value, dict) or set(value) != {'schemaVersion', 'artifacts'}
            or type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1
            or not isinstance(value.get('artifacts'), dict) or not value['artifacts']):
        raise FlowError('资源声明须为 schemaVersion:1 与非空 artifacts 映射')
    artifacts = {artifact['id']: artifact for artifact in selected}
    unknown = set(value['artifacts']) - set(artifacts)
    if unknown:
        raise FlowError('资源声明包含未交付的 Demo：' + ', '.join(sorted(unknown)), 409)
    for artifact_id, declaration in value['artifacts'].items():
        if not isinstance(declaration, dict):
            raise FlowError('Demo 资源声明须为对象：' + artifact_id)
        if artifacts[artifact_id].get('resourceManifest') is not None:
            raise FlowError('已登记资源清单的 Demo 不接受导出覆盖：' + artifact_id, 409)
    return value['artifacts']


def _derived_resource_record(store, root, artifact, state, declaration):
    from pf_resources import build_manifest

    bindings = (artifact['frozenRelations'].get('bindings', []) if 'frozenRelations' in artifact else
                [binding for binding in state['relations']['bindings'] if binding['artifactId'] == artifact['id']])
    entries = {artifact['entryHtml']}
    entries.update(unquote(urlsplit(binding['route']).path) or artifact['entryHtml']
                   for binding in bindings if binding.get('route'))
    required_archive = {'DESIGN.md'} if 'DESIGN.md' in artifact['fileHashes'] else set()
    required_archive.update(path for binding in bindings for path in binding.get('verificationScope', {}).get('files', []))
    references = [binding.get('screenshot') for binding in bindings]
    references.append((artifact.get('evidence', {}).get('frameworkReview') or {}).get('source'))
    prefix = artifact['path'] + '/'
    required_archive.update(path[len(prefix):] for path in references if isinstance(path, str) and path.startswith(prefix))
    manifest = build_manifest(store, store._safe(artifact['path'], base=root), supplied=declaration,
                              entries=sorted(entries), required_archive=sorted(required_archive))
    managed = set(manifest['runtimeFiles']) | set(manifest['archiveFiles'])
    if not managed.issubset(artifact['fileHashes']):
        raise FlowError('派生资源声明包含原 Demo 未登记的文件', 409)
    return dict(artifact, resourceManifest=manifest,
                fileHashes={path: artifact['fileHashes'][path] for path in sorted(managed)})


def module_package(store, module_id, version=None, resource_manifest=None, receipt=None):
    # Keep CLI writes out while collecting one coherent set of project bytes.
    with store._transaction(read_only=True):
        state = store.state(version=version)
        module = next((m for m in state['project']['modules'] if m['id'] == module_id), None)
        if not module:
            raise FlowError('模块不存在', 404)
        document = next((d for d in state['documents'] if d['id'] == module['documentId']), None)
        requirements = [r for r in state['requirements'] if r['moduleId'] == module_id]
        confirmation = module.get('stageEvidence') or {}
        if (module.get('stage') != 'confirmed' or not document
                or confirmation.get('type') != 'user-confirmation'
                or not confirmation.get('summary') or not confirmation.get('source')
                or confirmation.get('businessHash') != document['businessHash']
                or any(confirmation.get('requirementHashes', {}).get(r['id']) != r['hash'] for r in requirements)):
            raise FlowError('仅支持打包已确认且内容未变更的模块，请刷新项目后查看。', 409)

        ids = {r['id'] for r in requirements}
        artifacts = state['artifacts']['items']
        linked = {b['artifactId'] for b in state['relations']['bindings'] if ids.intersection(b.get('requirementIds', []))}
        selected = [a for a in artifacts if a['id'] in linked]
        if len(selected) != len(linked):
            raise FlowError('关联 Demo 不存在，请先补齐 Demo。', 409)
        if not selected:
            # A complete registered Demo can be delivered before screenshot bindings exist.
            selected = next(([a] for a in reversed(artifacts)
                             if a.get('syncStatus') == 'current'
                             and a.get('documentHashes', {}).get(document['id']) == document['businessHash']
                             and ids.issubset(a.get('requirementHashes', {}))), [])
        if not selected:
            raise FlowError('该模块尚无对应 Demo，请先生成并登记完整 Demo 后下载。', 409)
        deliverable = []
        by_id = {artifact['id']: artifact for artifact in artifacts}
        for artifact in selected:
            if artifact.get('kind') == 'working-draft':
                frozen = by_id.get(artifact.get('lastFrozenArtifactId'))
                preserved_source = (frozen is not None and artifact.get('draftRevision') == 0
                    and artifact.get('lastFrozenRevision') == 0
                    and artifact.get('draftSourceArtifactId') == frozen['id']
                    and artifact.get('fileHashes') == frozen.get('fileHashes'))
                if (artifact.get('editStatus') == 'editing' or artifact.get('integrityStatus') != 'intact'
                        or not frozen or frozen.get('kind') == 'working-draft'
                        or (not preserved_source and frozen.get('frozenFrom') != {
                            'artifactId': artifact['id'], 'revision': artifact.get('draftRevision')})):
                    raise FlowError('工作稿尚未冻结为交付版本，请让 Agent 保存并冻结当前 Demo 后下载。', 409)
                artifact = frozen
            if artifact['id'] not in {item['id'] for item in deliverable}:
                deliverable.append(artifact)
        selected = deliverable
        covered = set()
        for artifact in selected:
            if artifact.get('syncStatus') != 'current' or artifact.get('integrityStatus') != 'intact':
                raise FlowError('关联 Demo 已变更、缺失或依据旧稿，请更新 Demo 后下载。', 409)
            if artifact.get('documentHashes', {}).get(document['id']) != document['businessHash']:
                raise FlowError('Demo 与当前 PRD 不一致，请更新 Demo 后下载。', 409)
            covered.update(artifact.get('requirementHashes', {}))
        if not ids.issubset(covered):
            raise FlowError('Demo 尚未覆盖该模块的全部需求，请补齐后下载。', 409)

        root = store.content_root(version=version)
        overrides = _resource_overrides(resource_manifest, selected)
        from pf_resources import runtime_files, validate_manifest
        records, resource_modes = [], []
        for artifact in selected:
            _package_path(artifact['path'])
            for relative in artifact['fileHashes']:
                _package_path(relative)
            record = (_derived_resource_record(store, root, artifact, state, overrides[artifact['id']])
                      if artifact['id'] in overrides else artifact)
            manifest = validate_manifest(record, require_complete=True)
            mode = ('derived-runtime' if artifact['id'] in overrides else
                    'runtime-only' if manifest is not None else 'legacy-full')
            records.append(record)
            resource_modes.append({'artifactId': artifact['id'], 'resourceMode': mode})
        library_root = PurePosixPath(state['project']['libraryRoot'])
        files = {}

        def add(relative, expected=None):
            path = _package_path(relative)
            file = store._safe(relative, base=root, must_exist=True)
            if not store._is_file(file):
                raise FlowError('打包资源不是文件：' + relative, 409)
            data = store._file_bytes(file)
            if expected and hashlib.sha256(data).hexdigest() != expected:
                raise FlowError('打包期间文件发生变化，请刷新后重试。', 409)
            # Finder metadata may already be in an immutable artifact manifest.
            # Verify it as usual, but omit it from the delivery ZIP. Other dotfiles
            # can be required Demo resources and must retain their relative paths.
            if path.name != '.DS_Store':
                files[relative] = data
            return data

        entries = []
        artifact_files = {}
        for artifact in records:
            artifact_files.update({artifact['path'] + '/' + relative: expected
                                   for relative, expected in artifact['fileHashes'].items()})
            for relative in runtime_files(artifact):
                add(artifact['path'] + '/' + relative, artifact['fileHashes'][relative])
            entry = artifact['path'] + '/' + artifact['entryHtml']
            if entry not in files:
                raise FlowError('Demo 入口缺失，请重新登记完整 Demo。', 409)
            entries.append(entry)

        # Retain project-relative paths, including Markdown images and linked PRDs.
        pending = [(document['path'], document['fullHash'])]
        visited = set()
        referenced_archive = set()
        while pending:
            path, expected = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            data = add(path, expected)
            if PurePosixPath(path).suffix.lower() != '.md':
                continue
            markdown = data.decode('utf-8')
            for target in markdown_links(markdown):
                parsed = urlsplit(target.strip('<>'))
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                decoded = unquote(parsed.path)
                relative = posixpath.normpath(posixpath.join(posixpath.dirname(path), decoded))
                if library_root not in PurePosixPath(relative).parents:
                    # Explicit PRD links can add archive resources from selected
                    # Demos without making those files part of their runtime set.
                    if relative in artifact_files:
                        if relative not in files:
                            referenced_archive.add(relative)
                        pending.append((relative, artifact_files[relative]))
                        continue
                    raise FlowError('PRD 引用超出可打包范围：' + target, 409)
                pending.append((relative, None))

        readme = '\n'.join([
            '# ' + module['title'] + ' · Demo 与 PRD', '',
            '版本：' + (version or '当前工作稿') + '；项目修订：R' + str(state['project']['revision']), '',
            '## PRD', '', '- ' + document['path'], '', '## Demo 入口', '',
            *['- ' + entry for entry in entries], '',
            '解压完整 ZIP 后，保留目录结构。可先用浏览器打开上述 HTML。',
            '如 Demo 使用模块脚本或本地数据请求，请在解压目录运行：', '',
            '```sh', 'python3 -m http.server 8000 --bind 127.0.0.1', '```', '',
            '再访问 http://127.0.0.1:8000/ 加上上述 Demo 入口路径。', '',
            '## Demo 资源范围', '',
            *['- ' + item['artifactId'] + '：' + item['resourceMode'] for item in resource_modes], '',
            'runtime-only：按已登记清单提供预览运行资源。',
            'derived-runtime：按本次明确声明从旧 Demo 只读派生运行资源，原版本未修改。',
            'legacy-full：旧 Demo 未登记资源分类，保留原完整目录（不含 .DS_Store），未声称已裁剪。',
            'PRD 明确引用的 Demo 归档资料会保留原相对路径；共享 Demo 的运行资源仍可包含其他模块页面。',
            *(['', '### PRD 附带引用', '', *['- ' + path for path in sorted(referenced_archive)]]
              if referenced_archive else []), '',
            '原有外部链接与在线服务仍需联网；下载不会把它们转为离线资源。', '',
        ])
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('README.md', readme)
            for path, data in sorted(files.items()):
                archive.writestr(path, data)
        title = re.sub(r'[^\w\-\u4e00-\u9fff]+', '-', module['title']).strip('-') or module_id
        if receipt is not None:
            modes = {item['resourceMode'] for item in resource_modes}
            receipt.update(resourceMode=next(iter(modes)) if len(modes) == 1 else 'mixed',
                           artifacts=resource_modes, prdReferencedFiles=sorted(referenced_archive))
        return output.getvalue(), title + '-' + (version or 'R' + str(state['project']['revision'])) + '.zip'
