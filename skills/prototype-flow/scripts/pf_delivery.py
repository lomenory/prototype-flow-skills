"""Thin CLI delivery wrapper; package eligibility stays in pf_export."""
import os
from pathlib import Path
import tempfile

from pf_core import FlowError, valid_id
from pf_export import module_package


def export_module(store, module_id, output, version=None, resource_manifest=None):
    valid_id(module_id)
    target = Path(output)
    if not target.is_absolute():
        raise FlowError('导出路径必须是绝对路径')
    if target.exists() or target.is_symlink():
        raise FlowError('导出文件已存在，不覆盖原文件', 409)
    if not target.parent.is_dir():
        raise FlowError('导出目录不存在', 404)
    receipt = {}
    data, filename = module_package(store, module_id, version, resource_manifest=resource_manifest, receipt=receipt)
    fd, temporary = tempfile.mkstemp(prefix='.pf-export-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)  # Publish atomically without replacing an existing file.
        except FileExistsError:
            raise FlowError('导出文件已存在，不覆盖原文件', 409)
    finally:
        os.unlink(temporary)
    return {'path': str(target), 'filename': target.name, 'suggestedFilename': filename,
            'versionId': version or 'working', 'moduleId': module_id, 'bytes': len(data), **receipt}
