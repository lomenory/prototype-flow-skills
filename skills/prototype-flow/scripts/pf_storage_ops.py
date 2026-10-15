"""Explicit storage inspection, compatibility migration and complete Demo export."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from pf_core import FlowError, digest
import pf_storage as storage


def _problem(blockers, category, identity, operation):
    try:
        return operation()
    except (FlowError, OSError, ValueError, TypeError, KeyError) as exc:
        blockers.append({'category': category, 'id': identity, 'message': str(exc),
                         'details': getattr(exc, 'details', None)})
        return None


def _hashes(store, path, values):
    if not isinstance(values, dict):
        raise FlowError('Storage file hashes must be a mapping', 409, path)
    directory = store.root if path == '.' else store._safe(path)
    checked = {}
    for relative, sha in values.items():
        storage._parts(relative)
        storage._hash(sha)
        store._safe(relative, base=directory)
        checked[relative] = sha
    return checked


def _revision_objects(store):
    """Validate every old revision reference without touching its identity or bytes."""
    result = set()
    directory = store._safe('.prototype-flow/draft-revisions')
    if not directory.exists():
        return result
    for path in sorted(directory.rglob('*.json')):
        store._safe(path.relative_to(store.root))
        value = json.loads(store._file_bytes(path).decode('utf-8'))
        artifact = value.get('artifact', {})
        hashes = _hashes(store, artifact.get('path'), value.get('fileHashes', {}))
        if artifact.get('fileHashes') is not None and hashes != artifact['fileHashes']:
            raise FlowError('Draft revision file hashes disagree with its artifact', 409,
                            path.relative_to(store.root).as_posix())
        external = _hashes(store, '.', value.get('externalFiles', {}))
        for sha in set(hashes.values()) | set(external.values()):
            blob = storage._blob(store, sha)
            if digest(store._file_bytes(blob)) != sha:
                raise FlowError('Draft recovery object is missing or changed', 409, sha)
            result.add(sha)
    return result


def _group_summary(store, key, record, present):
    absent = 0
    directory = store.root if record['path'] == '.' else store._safe(record['path'])
    for relative in record['files']:
        logical = storage._join(record['path'], relative)
        if not store._safe(relative, base=directory).exists() and logical not in present:
            absent += 1
    return {'key': key, 'kind': record['kind'], 'path': record['path'],
            'files': len(record['files']), 'unmaterializedFiles': absent}


def _verify_objects(store, groups, blockers):
    hashes = {sha for group in groups.values() for sha in group['files'].values()}
    for sha in sorted(hashes):
        def verify(sha=sha):
            blob = storage._blob(store, sha)
            if digest(store._file_bytes(blob)) != sha:
                raise FlowError('Storage content object is missing or changed', 409, sha)
        _problem(blockers, 'content-object', sha, verify)
    return hashes


def _verify_local(store, groups, blockers):
    present = storage._local(store)
    _, files = storage._groups(store, config={'schemaVersion': 1, 'mode': 'content', 'groups': groups})
    for logical, expected in sorted(files.items()):
        def verify(logical=logical, expected=expected):
            path = store._safe(logical)
            if path.exists():
                if not path.is_file() or store._file_digest(path) != expected:
                    raise FlowError('Materialized storage content was modified', 409, logical)
            elif logical in present:
                raise FlowError('Materialized storage content was deleted', 409, logical)
        _problem(blockers, 'local-copy', logical, verify)


def _result(store, mode, groups, blockers, revision_objects=()):
    present = storage._local(store)
    descriptions = [_group_summary(store, key, record, present) for key, record in sorted(groups.items())]
    unique = {sha for group in groups.values() for sha in group['files'].values()}
    logical = {storage._join(group['path'], name) for group in groups.values() for name in group['files']}
    absent = sum(not store._safe(name).exists() and name not in present for name in logical)
    deleted = sum(not store._safe(name).exists() and name in present for name in logical)
    return {'ok': not blockers, 'mode': mode, 'groupCount': len(groups),
            'fileReferences': sum(len(group['files']) for group in groups.values()),
            'uniqueObjects': len(unique), 'unmaterializedFiles': absent,
            'missingMaterializedFiles': deleted,
            'retainedRevisionObjects': len(revision_objects), 'groups': descriptions,
            'blockers': blockers}


def _plan(store):
    store._project()
    config = storage._config(store)
    existing, _ = storage._groups(store, config=config)
    legacy = config is None
    blockers, proposed = [], {}
    _verify_objects(store, existing, blockers)
    _verify_local(store, existing, blockers)
    revision_objects = _problem(blockers, 'draft-history', 'draft-revisions',
                                lambda: _revision_objects(store)) or set()

    def add(key, kind, path, hashes):
        hashes = _hashes(store, path, hashes)
        if not hashes:
            return
        record = {'kind': kind, 'path': path, 'files': hashes}
        if key in proposed and proposed[key] != record:
            raise FlowError('Storage sources disagree about the same group', 409, key)
        candidate = dict(existing, **proposed)
        candidate[key] = record
        storage._groups(store, config={'schemaVersion': 1, 'mode': 'content', 'groups': candidate})
        proposed[key] = record

    def fixed_input(record):
        path = record.get('inputPath')
        if not path:
            return
        hashes = _hashes(store, path, record.get('inputFileHashes', {}))
        if store._inventory(store._safe(path)) != hashes:
            raise FlowError('Fixed task input is missing or changed', 409, path)
        run_id = record.get('runId') or Path(path).name
        add('input:' + run_id, 'inputs', path, hashes)

    relations = store._read('relations.json', {'bindings': []})
    artifacts = store._read('artifacts.json', {'items': []})
    for artifact in artifacts.get('items', []):
        identity = artifact.get('id', '<unknown>')

        def inspect_artifact(artifact=artifact):
            path = artifact['path']
            hashes = _hashes(store, path, artifact['fileHashes'])
            if artifact.get('kind') == 'working-draft' and artifact.get('activeRunId'):
                raise FlowError('Draft has an active edit; save or finish the task before migration',
                                409, artifact['activeRunId'])
            if store._resource_inventory(store._safe(path), artifact) != hashes:
                raise FlowError('Demo files differ from the saved artifact', 409, path)
            prefix = path + '/'
            bindings = list((artifact.get('frozenRelations') or {}).get('bindings', []))
            bindings += [item for item in relations.get('bindings', [])
                         if item.get('artifactId') == artifact['id']]
            sources = [item.get('screenshot') for item in bindings]
            sources.append((artifact.get('evidence') or {}).get('frameworkReview', {}).get('source'))
            for source in sources:
                if not source or source.startswith(prefix):
                    continue
                source_path = store._safe(source)
                if not store._is_file(source_path):
                    raise FlowError('Explicit Demo evidence is missing', 409, source)
                add('external:' + digest(source)[:16], 'evidence',
                    source_path.parent.relative_to(store.root).as_posix(),
                    {source_path.name: store._file_digest(source_path)})
            if artifact.get('kind') != 'working-draft':
                add('artifact:' + artifact['id'], 'frozen', path, hashes)
            else:
                manifest = artifact.get('resourceManifest')
                if manifest is not None:
                    archive = manifest.get('archiveFiles', [])
                else:
                    archive = []
                    for source in sources:
                        if not source or not source.startswith(prefix):
                            continue
                        source_path = store._safe(source)
                        if not store._is_file(source_path):
                            raise FlowError('Explicit draft evidence is missing', 409, source)
                        archive.append(source[len(prefix):])
                add('evidence:' + artifact['id'], 'evidence', path,
                    {name: hashes[name] for name in archive})
            fixed_input(artifact)

        _problem(blockers, 'artifact', identity, inspect_artifact)

    runs = store._safe('.prototype-flow/runs')
    if runs.exists():
        for path in sorted(runs.glob('*.json')):
            def inspect_run(path=path):
                store._safe(path.relative_to(store.root))
                fixed_input(json.loads(store._file_bytes(path).decode('utf-8')))
            _problem(blockers, 'run-input', path.stem, inspect_run)

    if legacy:
        local = store._safe('local_tasks')
        if local.exists():
            _problem(blockers, 'local-archive', 'local_tasks', lambda: add(
                'archive:legacy-local-tasks', 'archive', 'local_tasks', store._inventory(local)))
    all_groups = dict(existing, **proposed)
    result = _result(store, 'legacy' if legacy else 'content', all_groups, blockers, revision_objects)
    result.update(action='migration-plan', applied=False, existingGroupCount=len(existing),
                  plannedGroupCount=len(proposed), preservesHistory=True,
                  deletesFiles=False, changesGitIndex=False)
    return result, proposed


def status(store):
    with store._transaction(read_only=True), store._read_session():
        store._project()
        config = storage._config(store)
        if config is None:
            result, _ = _plan(store)
            result['action'] = 'status'
            return result
        groups, _ = storage._groups(store, config=config)
        blockers = []
        _verify_objects(store, groups, blockers)
        _verify_local(store, groups, blockers)
        revisions = _problem(blockers, 'draft-history', 'draft-revisions',
                             lambda: _revision_objects(store)) or set()
        result = _result(store, 'content', groups, blockers, revisions)
        result['action'] = 'status'
        return result


def migrate(store, execute=False):
    if not execute:
        with store._transaction(read_only=True), store._read_session():
            result, _ = _plan(store)
            return result
    with store._transaction(), store._rollback_writes(), store._read_session():
        result, groups = _plan(store)
        if result['blockers']:
            raise FlowError('Storage migration has unresolved blockers; no project content was changed',
                            409, result)
        storage.initialize(store)
        for key, record in sorted(groups.items()):
            storage.register(store, key, record['kind'], record['path'], record['files'])
        result.update(mode='content', action='migrated', applied=True)
        return result


def _export_target(store, output):
    path = Path(output).expanduser()
    if not path.is_absolute() or '..' in path.parts:
        raise FlowError('Demo export requires an absolute directory without parent traversal', 403)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise FlowError('Symbolic links are not permitted in Demo export paths', 403)
    if path.exists():
        raise FlowError('Demo export destination already exists', 409)
    try:
        relative = path.relative_to(store.root)
    except ValueError:
        pass
    else:
        if len(relative.parts) < 2 or relative.parts[0] != 'local_tasks':
            raise FlowError('Exports inside the project must use a new local_tasks directory', 403)
        store._safe(relative)
    return path


def export_demo(store, artifact_id, output):
    target = _export_target(store, output)
    # Keep the source session open through staging. Publishing follows the session's
    # final consistency check, so a concurrent source change cannot leave a package.
    with tempfile.TemporaryDirectory(prefix='prototype-flow-export-') as temporary:
        staged = Path(temporary) / 'demo'
        staged.mkdir()
        with store._transaction(read_only=True), store._read_session():
            store._project()
            artifact = next((item for item in store._read('artifacts.json', {'items': []})['items']
                             if item.get('id') == artifact_id), None)
            if artifact is None:
                raise FlowError('Unknown Demo artifact', 404, artifact_id)
            source = store._safe(artifact['path'])
            hashes = _hashes(store, artifact['path'], artifact.get('fileHashes'))
            if not hashes or store._resource_inventory(source, artifact) != hashes:
                raise FlowError('Demo content is missing or changed; export was not created', 409, artifact_id)
            if artifact.get('entryHtml', 'index.html') not in hashes:
                raise FlowError('Demo export has no registered entry HTML', 409, artifact_id)
            for relative, expected in sorted(hashes.items()):
                data = store._file_bytes(store._safe(relative, base=source))
                if digest(data) != expected:
                    raise FlowError('Demo content changed during export', 409, relative)
                destination = staged.joinpath(*storage._parts(relative))
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            if storage._physical_inventory(store, staged) != hashes:
                raise FlowError('Demo export failed staged integrity verification', 409)
        # Stage beside the final target to make final publication one rename even
        # when the generic temporary directory and destination use different disks.
        _export_target(store, output)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.pf-export-', dir=target.parent) as publication:
            ready = Path(publication) / 'demo'
            shutil.copytree(staged, ready)
            if storage._physical_inventory(store, ready) != hashes:
                raise FlowError('Demo export failed publication integrity verification', 409)
            _export_target(store, output)
            ready.rename(target)
    return {'artifactId': artifact_id, 'path': str(target), 'entryHtml': artifact.get('entryHtml', 'index.html'),
            'files': len(hashes), 'mode': 'full', 'includesArchive': True}
