"""Explicit content-backed copies of generated files; standard library only.

The shared manifest describes recoverable bytes.  The ignored local manifest
records files present on this computer, so deletion never becomes recovery by
accident.  Callers own transactions for changes to project metadata.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from pf_core import FlowError, digest


START = '# prototype-flow:content-storage:start'
END = '# prototype-flow:content-storage:end'


def _parts(value):
    if (not isinstance(value, str) or not value or '\\' in value
            or any(c in value for c in ('\n', '\r', '\x00'))
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise FlowError('Storage paths must be safe project-relative paths', 403, value)
    return value.split('/')


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise FlowError('Invalid storage content hash', 409, value)
    return value


def _join(directory, relative):
    return relative if directory == '.' else directory + '/' + relative


def _read_json(store, name, base=None):
    path = store._safe('.prototype-flow/' + name, base=base)
    # Existing physical paths return immediately from resolve(), preventing
    # recursion while retaining the store's concurrent-change detection.
    if not path.exists():
        return None
    cache, key = _cache(store, 'json', path)
    if cache is not None and key in cache:
        return cache[key]
    try:
        value = json.loads(store._file_bytes(path).decode('utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FlowError('Cannot read storage manifest: ' + name, 409, str(exc))
    if cache is not None:
        cache[key] = value
    return value


def _cache(store, kind, path):
    """Cache parsed/derived metadata only inside the current read operation."""
    session = store._reads
    if session is None:
        return None, None
    stamp = store._file_stamp(path) if path.exists() else None
    return session.setdefault('storage', {}), (kind, path, stamp)


def _location(store, path):
    """Return (physical path, project/snapshot base, base-relative path)."""
    path = Path(path)
    if path.is_absolute():
        try:
            relative = path.relative_to(store.root)
        except ValueError:
            raise FlowError('Storage path escapes project', 403)
    else:
        relative = path
    if '..' in relative.parts or '\\' in str(relative):
        raise FlowError('Storage path escapes project', 403)
    physical = store.root if not relative.parts else store._safe(relative)
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == 'versions' and parts[2] == 'project':
        base = store._safe(Path(*parts[:3]))
        logical = Path(*parts[3:]).as_posix() if len(parts) > 3 else ''
    else:
        base, logical = store.root, relative.as_posix() if parts else ''
    return physical, base, logical


def _config(store, base=None):
    base = Path(base or store.root)
    value = _read_json(store, 'storage.json', base=base)
    if value is None:
        return None
    if (not isinstance(value, dict) or type(value.get('schemaVersion')) is not int
            or value['schemaVersion'] != 1 or value.get('mode') != 'content'
            or not isinstance(value.get('groups'), dict)):
        raise FlowError('Invalid content storage manifest', 409)
    return value


def enabled(store, base=None):
    return _config(store, base) is not None


def _groups(store, base=None, config=None):
    base = Path(base or store.root)
    cache, key = (None, None) if config is not None else _cache(
        store, 'groups', store._safe('.prototype-flow/storage.json', base=base))
    if cache is not None and key in cache:
        return cache[key]
    config = config if config is not None else _config(store, base)
    groups = {} if config is None else config['groups']
    seen = {}
    for key, group in groups.items():
        if (not isinstance(key, str) or not key or not isinstance(group, dict)
                or not isinstance(group.get('kind'), str) or not group['kind'].strip()
                or not isinstance(group.get('files'), dict) or not group['files']):
            raise FlowError('Invalid content storage group', 409, key)
        if group.get('path') != '.':
            _parts(group.get('path'))
            store._safe(group['path'], base=base)
        names = group['files']
        for relative, sha in names.items():
            parts = _parts(relative)
            if any('/'.join(parts[:i]) in names for i in range(1, len(parts))):
                raise FlowError('Storage files have conflicting parent paths', 409, relative)
            _hash(sha)
            logical = _join(group['path'], relative)
            store._safe(logical, base=base)
            generated = ('.prototype-flow/run-inputs/', '.prototype-flow/run-outputs/',
                         '.prototype-flow/run-work/')
            metadata = (logical == '.prototype-flow' or
                        (logical.startswith('.prototype-flow/') and not logical.startswith(generated)))
            if logical == '.gitignore' or logical.startswith('versions/') or metadata:
                raise FlowError('Storage copies cannot replace immutable data or storage metadata', 403)
            if logical in seen and seen[logical] != sha:
                raise FlowError('Storage groups disagree about file content', 409, logical)
            seen[logical] = sha
    result = groups, seen
    if cache is not None:
        cache[key] = result
    return result


def _local(store, base=None):
    if base is not None and Path(base) != store.root:
        return frozenset()
    cache, key = _cache(store, 'local', store._safe('.prototype-flow/storage-local.json'))
    if cache is not None and key in cache:
        return cache[key]
    value = _read_json(store, 'storage-local.json')
    if value is None:
        return frozenset()
    if (not isinstance(value, dict) or value.get('schemaVersion') != 1
            or not isinstance(value.get('present'), list)
            or any(not isinstance(name, str) for name in value['present'])):
        raise FlowError('Invalid local storage presence manifest', 409)
    for relative in value['present']:
        _parts(relative)
    result = frozenset(value['present'])
    if cache is not None:
        cache[key] = result
    return result


def _write_local(store, present):
    store._write('storage-local.json', {'schemaVersion': 1, 'present': sorted(present)})


def _ignore(store, config):
    _, files = _groups(store, config=config)
    path = store._safe('.gitignore')
    content = store._file_bytes(path).decode('utf-8') if path.is_file() else ''
    if content.count(START) != content.count(END) or content.count(START) > 1:
        raise FlowError('Invalid managed storage block in .gitignore', 409)
    generated = ['/.prototype-flow/storage-local.json', '/local_tasks/']
    generated += ['/' + re.sub(r'([*?\[\] !#])', r'\\\1', name) for name in sorted(files)]
    block = START + '\n' + '\n'.join(generated) + '\n' + END
    if START in content:
        start, end = content.index(START), content.index(END) + len(END)
        if end < start:
            raise FlowError('Invalid managed storage block in .gitignore', 409)
        content = content[:start] + block + content[end:]
    else:
        content += ('\n' if content and not content.endswith('\n') else '') + block + '\n'
    store._write_bytes(path, content.encode('utf-8'))


def initialize(store):
    config = _config(store)
    if config is None:
        config = {'schemaVersion': 1, 'mode': 'content', 'groups': {}}
        store._write('storage.json', config)
    _ignore(store, config)
    return config


def _blob(store, sha, base=None):
    path = store._safe('.prototype-flow/draft-blobs/' + _hash(sha), base=base)
    if not path.is_file() or store._file_digest(path) != sha:
        raise FlowError('Storage content blob is missing or changed', 409, sha)
    return path


def capture_bytes(store, data, expected_hash=None, base=None):
    if not isinstance(data, bytes):
        raise FlowError('Storage content must be bytes')
    sha = digest(data)
    if expected_hash is not None and sha != _hash(expected_hash):
        raise FlowError('Storage source changed before capture', 409)
    path = store._safe('.prototype-flow/draft-blobs/' + sha, base=base)
    if path.exists():
        _blob(store, sha, base)
    else:
        store._write_bytes(path, data)
    return sha


def register(store, key, kind, path, hashes):
    config = _config(store)
    if config is None:
        raise FlowError('Content storage is not enabled; migrate explicitly first', 409)
    path = '.' if path == '.' else '/'.join(_parts(path))
    protected = ('.prototype-flow/draft-blobs', '.prototype-flow/revisions', 'versions')
    if any(path == name or path.startswith(name + '/') for name in protected):
        raise FlowError('Storage copies cannot contain immutable project data', 403)
    record = {'kind': kind, 'path': path, 'files': dict(hashes) if isinstance(hashes, dict) else hashes}
    if not isinstance(key, str) or not key:
        raise FlowError('Storage group key must be a nonempty string')
    next_groups = dict(config['groups'])
    if hashes == {}:
        next_groups.pop(key, None)
    else:
        next_groups[key] = record
    candidate = dict(config, groups=next_groups)
    _, files = _groups(store, config=candidate)
    present = set(_local(store))
    for relative, sha in record['files'].items():
        logical = _join(path, relative)
        if logical in ('.prototype-flow/storage.json', '.prototype-flow/storage-local.json', '.gitignore'):
            raise FlowError('Storage copies cannot replace their own metadata', 403)
        source = store._safe(logical)
        if source.exists():
            if not source.is_file():
                raise FlowError('Storage source must be a regular file', 409, logical)
            capture_bytes(store, store._file_bytes(source), sha)
            present.add(logical)
        elif logical in present:
            raise FlowError('Previously materialized storage source was deleted', 409, logical)
        else:
            _blob(store, sha)
    store._write('storage.json', candidate)
    _write_local(store, present.intersection(files))
    _ignore(store, candidate)
    return record


def resolve(store, path):
    physical, base, logical = _location(store, path)
    if physical.exists():
        return physical
    _, files = _groups(store, base)
    if logical not in files or logical in _local(store, base):
        return physical
    return _blob(store, files[logical], base)


def is_file(store, path):
    return resolve(store, path).is_file()


def is_dir(store, path):
    physical, base, logical = _location(store, path)
    if physical.exists():
        return physical.is_dir()
    _, files = _groups(store, base)
    present = _local(store, base)
    prefix = logical + '/' if logical else ''
    available = [name for name in files if name.startswith(prefix) and name not in present]
    for name in available:
        _blob(store, files[name], base)
    return bool(available)


def has_virtual_files(store, directory):
    """Cheap cache discriminator; byte integrity is checked when files are read."""
    _, base, logical = _location(store, directory)
    _, files = _groups(store, base)
    present = _local(store, base)
    prefix = logical + '/' if logical else ''
    return any(name.startswith(prefix) and name not in present
               and not store._safe(name, base=base).is_file() for name in files)


def inventory(store, directory, actual):
    """Merge omitted registered files without masking real changes/deletions."""
    physical, base, logical = _location(store, directory)
    _, files = _groups(store, base)
    present = _local(store, base)
    prefix = logical + '/' if logical else ''
    result = dict(actual)
    for name, sha in files.items():
        if not name.startswith(prefix) or name in present:
            continue
        relative = name[len(prefix):]
        if not relative or relative in result:
            continue
        source = store._safe(name, base=base)
        if not source.exists():
            _blob(store, sha, base)
            result[relative] = sha
    return result


def forget_materialized(store, paths):
    present = set(_local(store))
    for path in paths:
        _, base, logical = _location(store, path)
        if base != store.root:
            raise FlowError('Cannot change historical storage presence', 403)
        present.discard(logical)
    _write_local(store, present)


def _physical_inventory(store, directory):
    if not directory.is_dir() or directory.is_symlink():
        raise FlowError('Storage destination must be a regular directory', 409)
    result = {}
    for current, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            if path.is_symlink():
                raise FlowError('Symbolic links are not permitted in storage copies', 403)
        for name in files:
            path = Path(current) / name
            if not path.is_file():
                raise FlowError('Storage copies require regular files', 409)
            result[path.relative_to(directory).as_posix()] = digest(path.read_bytes())
    return result


def _output(path):
    path = Path(path).expanduser().absolute()
    if '..' in path.parts:
        raise FlowError('Storage output must not contain parent traversal', 403)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise FlowError('Symbolic links are not permitted in storage output', 403)
    return path


def _materialize_evidence(store, record, target, sources):
    """Evidence shares source directories with editable files and other groups."""
    missing = []
    for name, sha in record['files'].items():
        destination = target.joinpath(*_parts(name))
        for parent in (destination, *destination.parents):
            if parent.is_symlink():
                raise FlowError('Symbolic links are not permitted in evidence copies', 403)
        if destination.exists():
            if not destination.is_file() or digest(destination.read_bytes()) != sha:
                raise FlowError('Existing evidence changed; no files were overwritten', 409, name)
        else:
            missing.append(name)
    if not missing:
        return 'unchanged'
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pf-materialize-', dir=target.parent) as temporary:
        stage = Path(temporary)
        for name in missing:
            staged = stage.joinpath(*_parts(name))
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sources[name], staged)
            if digest(staged.read_bytes()) != record['files'][name]:
                raise FlowError('Storage content changed during materialization', 409, name)
        for name in missing:
            destination = target.joinpath(*_parts(name))
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Atomic create-if-absent: never replace a file created after preflight.
            try:
                os.link(stage.joinpath(*_parts(name)), destination)
            except FileExistsError:
                raise FlowError('Evidence destination appeared during materialization', 409, name)
    return 'restored'


def materialize(store, key, output=None):
    groups, _ = _groups(store)
    if key not in groups:
        raise FlowError('Unknown content storage group', 404, key)
    record = groups[key]
    original = store.root if record['path'] == '.' else store._safe(record['path'])
    target = original if output is None else _output(output)
    sources = {name: _blob(store, sha) for name, sha in record['files'].items()}
    if record['kind'] == 'evidence' and target == original:
        status = _materialize_evidence(store, record, target, sources)
    elif target.exists():
        if _physical_inventory(store, target) != record['files']:
            raise FlowError('Existing storage copy changed; no files were overwritten', 409)
        status = 'unchanged'
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.pf-materialize-', dir=target.parent) as temporary:
            stage = Path(temporary) / 'content'
            stage.mkdir()
            for name, source in sources.items():
                destination = stage.joinpath(*_parts(name))
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            if _physical_inventory(store, stage) != record['files']:
                raise FlowError('Storage content changed during materialization', 409)
            if target.exists() or target.is_symlink():
                raise FlowError('Storage destination appeared during materialization', 409)
            stage.rename(target)
        status = 'restored'
    if target == original:
        store._forget_tree(target)
        present = set(_local(store))
        present.update(_join(record['path'], name) for name in record['files'])
        _write_local(store, present)
    return {'key': key, 'path': str(target), 'status': status, 'files': len(record['files'])}
