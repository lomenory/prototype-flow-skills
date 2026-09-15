"""Resolve and install missing Skill dependencies from a pinned GitHub commit.

Python 3.9+ and Git; no downloaded code runs during installation.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile


SKILL_ROOT = Path(__file__).resolve().parents[1]
# Python resolves the script directory in sys.path; argv preserves a symlinked entry.
INVOCATION_ROOT = Path(__file__).absolute().parents[1]
ENTRY_SCRIPT = Path(sys.argv[0]).absolute()
if ENTRY_SCRIPT.name == 'flow.py' and ENTRY_SCRIPT.resolve().parent == SKILL_ROOT / 'scripts':
    INVOCATION_ROOT = ENTRY_SCRIPT.parent.parent
LOCK_PATH = SKILL_ROOT / 'dependencies.lock.json'
STAGES = ('core', 'prd', 'demo', 'feishu', 'all')
SKILL_DIRECTORIES = ('.agents/skills', '.claude/skills', '.cursor/skills', '.codex/skills')
SKILLS_DIR_ENV = 'PROTOTYPE_FLOW_SKILLS_DIR'


class DependencyError(ValueError):
    pass


def default_destination():
    explicit = os.environ.get(SKILLS_DIR_ENV)
    if explicit:
        return Path(explicit).expanduser()
    for root in (INVOCATION_ROOT.parent, SKILL_ROOT.parent):
        if any(root.parts[-2:] == Path(name).parts for name in SKILL_DIRECTORIES):
            return root
    configured = os.environ.get('CODEX_HOME')
    return Path(configured).expanduser() / 'skills' if configured else Path.home() / '.agents/skills'


def skill_roots(project=None, dest=None):
    """Explicit CLI/environment roots isolate both installation and runtime lookup."""
    explicit = dest if dest is not None else os.environ.get(SKILLS_DIR_ENV)
    if explicit is not None and str(explicit):
        return [Path(explicit).expanduser().resolve()]
    roots = []
    directories = list(SKILL_DIRECTORIES)
    destination = default_destination()
    for name in directories[:]:
        if destination.parts[-2:] == Path(name).parts:
            directories.remove(name)
            directories.insert(0, name)
            break
    current = Path(project or Path.cwd()).expanduser().resolve()
    for parent in (current, *current.parents):
        roots.extend(parent / name for name in directories)
        if (parent / '.git').exists():
            break
    roots.extend([INVOCATION_ROOT.parent, SKILL_ROOT.parent, destination])
    if os.environ.get('CODEX_HOME'):
        roots.append(Path(os.environ['CODEX_HOME']).expanduser() / 'skills')
    roots.extend(Path.home() / name for name in directories)
    roots.append(Path('/etc/codex/skills'))
    return list(dict.fromkeys(roots))


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise DependencyError('依赖路径无效')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')):
        raise DependencyError('依赖路径必须是目录内的相对路径')
    return path


def load_lock(path=LOCK_PATH):
    data = json.loads(Path(path).read_text('utf-8'))
    if data.get('schemaVersion') != 1:
        raise DependencyError('不支持的依赖锁文件版本')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', data.get('repository', '')):
        raise DependencyError('依赖来源必须是 GitHub owner/repo')
    if not re.fullmatch(r'[0-9a-f]{40}', data.get('ref', '')):
        raise DependencyError('依赖必须固定到完整 Git commit SHA')
    entries = data.get('dependencies')
    if not isinstance(entries, list) or not entries:
        raise DependencyError('依赖列表为空')
    names = set()
    for entry in entries:
        name = entry.get('name', '')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or name in names:
            raise DependencyError('依赖名称无效或重复')
        names.add(name)
        safe_relative(entry.get('path'))
        if not entry.get('stages') or not set(entry['stages']) <= set(STAGES):
            raise DependencyError('依赖阶段无效')
        files = entry.get('files')
        if not isinstance(files, dict) or 'SKILL.md' not in files:
            raise DependencyError('依赖缺少文件校验清单')
        for filename, checksum in files.items():
            safe_relative(filename)
            if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
                raise DependencyError('依赖文件 SHA-256 无效')
        if not entry.get('requiredFiles') or not set(entry['requiredFiles']) <= set(files):
            raise DependencyError('依赖必备文件不在校验清单中')
    return data


def selected_dependencies(lock, stage):
    if stage not in STAGES:
        raise DependencyError('未知依赖阶段：' + stage)
    return [entry for entry in lock['dependencies'] if stage == 'all' or stage in entry['stages']]


def inspect_dependency(entry, roots):
    for root in roots:
        candidate = root / entry['name']
        if not candidate.exists() and not candidate.is_symlink():
            continue
        missing = [name for name in entry['requiredFiles'] if not (candidate / name).is_file()]
        skill = candidate / 'SKILL.md'
        text = skill.read_text('utf-8') if skill.is_file() else ''
        identity = re.search(r'^name:\s*[\'\"]?' + re.escape(entry['name']) + r'[\'\"]?\s*$',
                             text.split('---', 2)[1] if text.startswith('---') and text.count('---') >= 2 else '', re.M)
        return {'name': entry['name'], 'status': 'invalid' if missing or not identity else 'available',
                'path': str(candidate), 'missingFiles': missing}
    return {'name': entry['name'], 'status': 'missing', 'path': None}


def find_skill(name, project=None):
    lock = load_lock()
    entry = next((item for item in lock['dependencies'] if item['name'] == name), None)
    if entry is None:
        return None
    state = inspect_dependency(entry, skill_roots(project))
    return Path(state['path']) if state['status'] == 'available' else None


def fetch_archive(repository, ref, paths):
    """Use existing Git credentials; never log in, clone submodules, or run hooks."""
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    try:
        with tempfile.TemporaryDirectory(prefix='prototype-flow-fetch-') as directory:
            git = ['git', '-c', 'core.hooksPath=/dev/null', '-C', directory]
            for args in (['init', '--quiet'],
                         ['fetch', '--quiet', '--depth=1', '--no-tags',
                          'https://github.com/' + repository + '.git', ref]):
                subprocess.run(git + args, env=environment, capture_output=True, check=True, timeout=60)
            actual = subprocess.run(git + ['rev-parse', 'FETCH_HEAD'], env=environment,
                                    capture_output=True, check=True, timeout=10).stdout.decode().strip()
            if actual != ref:
                raise DependencyError('下载提交与锁文件不一致')
            return subprocess.run(git + ['archive', '--format=tar', ref, '--', *paths],
                                  env=environment, capture_output=True, check=True, timeout=60).stdout
    except FileNotFoundError as exc:
        raise DependencyError('自动安装需要 Git，请先安装 Git 后重试。') from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise DependencyError('无法拉取 GitHub 固定提交；检查网络、仓库访问权限和 Git 凭据后重试。') from exc


def unpack_verified(archive, entry, target):
    """Extract only regular, explicitly locked files and verify before installation."""
    prefix = entry['path'] + '/'
    found = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as source:
        for member in source:
            safe_relative(member.name.rstrip('/'))
            if not member.name.startswith(prefix) or member.isdir():
                continue
            relative = member.name[len(prefix):]
            safe_relative(relative)
            if not member.isfile() or relative not in entry['files'] or relative in found:
                raise DependencyError('远端依赖包含未声明文件、链接或重复条目：' + member.name)
            if member.size > 20 * 1024 * 1024:
                raise DependencyError('依赖文件过大：' + relative)
            content = source.extractfile(member).read()
            if hashlib.sha256(content).hexdigest() != entry['files'][relative]:
                raise DependencyError('依赖文件校验失败：' + entry['name'] + '/' + relative)
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            output.chmod(0o755 if member.mode & 0o111 else 0o644)
            found.add(relative)
    if found != set(entry['files']):
        raise DependencyError('远端依赖文件不完整：' + entry['name'])
    state = inspect_dependency(entry, [target.parent])
    if state['status'] != 'available':
        raise DependencyError('远端 Skill 入口或必备文件无效：' + entry['name'])


def ensure_dependencies(stage='core', project=None, dest=None, check=False, lock_path=LOCK_PATH):
    lock = load_lock(lock_path)
    selected = selected_dependencies(lock, stage)
    roots = skill_roots(project, dest)
    states = [inspect_dependency(entry, roots) for entry in selected]
    destination = Path(dest).expanduser().resolve() if dest else default_destination().resolve()
    result = {'ok': False, 'stage': stage, 'destination': str(destination),
              'repository': lock['repository'], 'ref': lock['ref'], 'dependencies': states}
    if check or any(item['status'] == 'invalid' for item in states):
        result['ok'] = all(item['status'] == 'available' for item in states)
        if any(item['status'] == 'invalid' for item in states):
            result['error'] = '已有同名 Skill 不完整；已保留原目录，请修复或显式选择其他 --dest。'
        return result
    missing = [(entry, state) for entry, state in zip(selected, states) if state['status'] == 'missing']
    if not missing:
        result['ok'] = True
        return result
    try:
        archive = fetch_archive(lock['repository'], lock['ref'], [entry['path'] for entry, _ in missing])
        destination.mkdir(parents=True, exist_ok=True)
        # Stage on the destination filesystem; all dependencies verify before any install.
        with tempfile.TemporaryDirectory(prefix='.prototype-flow-install-', dir=destination) as directory:
            staging = Path(directory)
            for entry, _ in missing:
                unpack_verified(archive, entry, staging / entry['name'])
            # Serialize installers without creating persistent locks or touching existing skills.
            import fcntl
            descriptor = os.open(str(destination), os.O_RDONLY)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                for entry, state in missing:
                    current = inspect_dependency(entry, [destination])
                    if current['status'] == 'invalid':
                        raise DependencyError('安装期间出现同名目录，已保留：' + entry['name'])
                    if current['status'] == 'available':
                        state.update(current)
                        continue
                    target = destination / entry['name']
                    (staging / entry['name']).rename(target)
                    state.update(status='installed', path=str(target))
            finally:
                os.close(descriptor)
        result['ok'] = True
    except (DependencyError, OSError, tarfile.TarError) as exc:
        result['error'] = str(exc)
    return result
