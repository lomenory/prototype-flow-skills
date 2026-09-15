#!/usr/bin/env python3
"""Install this local Skill package into an explicit root without host-specific tools."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile


SOURCE = Path(__file__).resolve().parents[1]
IGNORED = shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', '.git')


def inventory(root):
    files = {}
    for directory, dirs, names in os.walk(root):
        ignored = IGNORED(directory, dirs + names)
        dirs[:] = sorted(name for name in dirs if name not in ignored)
        for name in dirs + names:
            path = Path(directory) / name
            if name not in ignored and path.is_symlink():
                raise ValueError('Skill 包含符号链接，请使用完整的普通文件副本：' + str(path))
        for name in names:
            if name not in ignored:
                path = Path(directory) / name
                files[str(path.relative_to(root))] = path.read_bytes()
    if 'SKILL.md' not in files or 'scripts/flow.py' not in files:
        raise ValueError('主 Skill 入口或运行时缺失')
    return files


def install(destination, check=False, source=SOURCE):
    source = Path(source).resolve()
    destination = Path(destination).expanduser().resolve()
    target = destination / 'prototype-flow'
    result = {'ok': False, 'path': str(target), 'status': 'missing'}
    try:
        expected = inventory(source)

        def inspect_existing():
            if not target.exists() and not target.is_symlink():
                return False
            same = target.is_dir() and inventory(target) == expected
            result.update(ok=same, status='available' if same else 'conflict')
            if not same:
                result['error'] = '已有同名目录与当前源码不同，已保留；请选择其他 --dest 或另行处理更新。'
            return True

        if inspect_existing() or check:
            return result
        if source == target or source in target.parents:
            raise ValueError('安装目标不能位于主 Skill 源码内')
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.prototype-flow-install-', dir=destination) as temp:
            staged = Path(temp) / 'prototype-flow'
            shutil.copytree(source, staged, ignore=IGNORED)
            if inventory(staged) != expected:
                raise ValueError('复制期间源码发生变化，请重试')
            descriptor = os.open(str(destination), os.O_RDONLY)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                if inspect_existing():
                    return result
                staged.rename(target)
            finally:
                os.close(descriptor)
        result.update(ok=True, status='installed')
    except (OSError, ValueError) as exc:
        result.update(status='error', error=str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description='安装当前主 Skill 副本；不联网、不安装依赖、不覆盖已有目录')
    parser.add_argument('--dest', required=True, help='宿主的 skills 根目录，例如 ~/.claude/skills')
    parser.add_argument('--check', action='store_true', help='只检查目标是否与当前副本一致，不写入文件')
    args = parser.parse_args()
    result = install(args.dest, args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
