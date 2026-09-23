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


def module_package(store, module_id, version=None):
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
        library_root = PurePosixPath(state['project']['libraryRoot'])
        files = {}

        def add(relative, expected=None):
            path = PurePosixPath(relative)
            if '\\' in relative or path.is_absolute() or not path.parts or '..' in path.parts:
                raise FlowError('打包资源路径无效：' + relative, 403)
            file = store._safe(relative, base=root, must_exist=True)
            if not file.is_file():
                raise FlowError('打包资源不是文件：' + relative, 409)
            data = file.read_bytes()
            if expected and hashlib.sha256(data).hexdigest() != expected:
                raise FlowError('打包期间文件发生变化，请刷新后重试。', 409)
            # Finder metadata may already be in an immutable artifact manifest.
            # Verify it as usual, but omit it from the delivery ZIP. Other dotfiles
            # can be required Demo resources and must retain their relative paths.
            if path.name != '.DS_Store':
                files[relative] = data
            return data

        entries = []
        for artifact in selected:
            for relative, expected in artifact['fileHashes'].items():
                add(artifact['path'] + '/' + relative, expected)
            entry = artifact['path'] + '/' + artifact['entryHtml']
            if entry not in files:
                raise FlowError('Demo 入口缺失，请重新登记完整 Demo。', 409)
            entries.append(entry)

        # Retain project-relative paths, including Markdown images and linked PRDs.
        pending = [(document['path'], document['fullHash'])]
        visited = set()
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
                    # Demo links retain their paths when they are part of a selected artifact.
                    if relative in files:
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
            '包内包含已登记 Demo 的完整资源目录。共享 Demo 保留其他模块的页面。',
            '原有外部链接与在线服务仍需联网；下载不会把它们转为离线资源。', '',
        ])
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('README.md', readme)
            for path, data in sorted(files.items()):
                archive.writestr(path, data)
        title = re.sub(r'[^\w\-\u4e00-\u9fff]+', '-', module['title']).strip('-') or module_id
        return output.getvalue(), title + '-' + (version or 'R' + str(state['project']['revision'])) + '.zip'
