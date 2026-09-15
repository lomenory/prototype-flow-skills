"""Small, derived document navigation for Prototype Flow projects."""
from pathlib import Path
from urllib.parse import quote


MARKER = '<!-- prototype-flow:document-map -->'


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def document_map(project, index, sources):
    """Use registered identities and explicit dependencies, never infer relations."""
    modules = {module['id']: module for module in project['modules']}
    requirements = index.get('items', [])
    by_id = {item['id']: item for item in requirements}
    lines = ['# 项目文档导航', '', MARKER, '',
             '由 Prototype Flow 根据项目索引生成。按本次任务选择文档；正文保存会自动更新导航。',
             '外部编辑或维护失败后使用 `flow.py refresh <project-dir>`，无需重复全库整理。', '',
             '| 文档 | 模块 ID | 阶段 | 需求数 | 来源 ID | 依赖模块 |',
             '| --- | --- | --- | --- | --- | --- |']
    library = Path(project['libraryRoot'])
    for document in index.get('documents', []):
        module = modules[document['moduleId']]
        reqs = [item for item in requirements if item['documentId'] == document['id']]
        source_ids = sorted({source for item in reqs for source in item.get('sourceIds', [])})
        dependencies = sorted({by_id[rid]['moduleId'] for item in reqs for rid in item.get('dependsOn', [])
                               if rid in by_id and by_id[rid]['moduleId'] != module['id']})
        relative = Path(document['path']).relative_to(library).as_posix()
        link = quote('../' + relative, safe='/')
        title = cell(document['title']).replace('[', '\\[').replace(']', '\\]')
        lines.append('| [%s](%s) | %s | %s | %s | %s | %s |' % (
            title, link, cell(module['id']), cell(module.get('stage', 'draft')), len(reqs),
            cell(', '.join(source_ids)), cell(', '.join(dependencies))))
    lines.extend(['', '## 资料来源', '', '| ID | 名称 | 定位 | 本地文件 |', '| --- | --- | --- | --- |'])
    for source in sources.get('items', []):
        lines.append('| %s | %s | %s | %s |' % tuple(cell(source.get(key, ''))
                     for key in ('id', 'label', 'locator', 'path')))
    lines.extend(['', '业务要求以 PRD Markdown 为准；未决项保留在对应 PRD。',
                  '其他研究和决策资料按需查看 `03-research/`、`04-decisions/`。', ''])
    return '\n'.join(lines)


def legacy_guide(text):
    """Replace only known generated directions; retain authored additions."""
    replacements = {
        '2. Read `INDEX.md` for the full catalog.':
            '2. Open only the documents relevant to the current task; no second catalog read is needed.',
        '4. After edits, run `refresh --sync-related --dashboard` so links, index, AI map, and dashboard stay current.':
            '4. Prototype Flow updates navigation on save. Use `flow.py refresh <project-dir>` only after external edits or maintenance failure.',
        '- Record major scope, workflow, metric, permission, billing, privacy, dependency, or launch changes in `CHANGELOG.md`.':
            '- Record significant business decisions and their reasons in the affected PRD or decision notes.',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def maintain(store):
    project = store._project()
    library = Path(project['libraryRoot'])
    index = store._read('requirement-index.json', {'documents': [], 'items': []})
    sources = store._read('sources.json', {'items': []})
    path = store._safe(library / '00-ai-context/DOC_MAP.md')
    store._write_bytes(path, document_map(project, index, sources).encode('utf-8'))

    # Keep legacy entry paths usable without maintaining duplicate catalogs.
    old_index = store._safe(library / 'INDEX.md')
    if old_index.is_file():
        text = old_index.read_text('utf-8')
        if text.startswith('# PRD Library Index\n\nGenerated:') and '## Active Documents' in text:
            store._write_bytes(old_index, '# 文档导航\n\n[项目文档导航](00-ai-context/DOC_MAP.md)\n'.encode('utf-8'))
    guide = store._safe(library / '00-ai-context/AI_GUIDE.md')
    if guide.is_file():
        text = guide.read_text('utf-8')
        store._write_bytes(guide, legacy_guide(text).encode('utf-8'))
    return {'status': 'ok', 'engine': 'builtin', 'navigationPath': path.relative_to(store.root).as_posix()}
