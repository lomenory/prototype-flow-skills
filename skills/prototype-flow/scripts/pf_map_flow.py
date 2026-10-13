"""Default requirement-map receipts, separate from business persistence."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

from pf_core import FlowError
from pf_requirement_map import requirement_map_state
from pf_server import ensure_workbench


def _snapshot_command(store, module_id=None, requirement_id=None, version=None):
    command = [sys.executable, '-B', str(Path(__file__).with_name('flow.py')),
               'review-state', str(store.root), '--view', 'requirement-map']
    for flag, value in (('--module', module_id), ('--requirement', requirement_id), ('--version', version)):
        if value:
            command.extend([flag, value])
    return command


def _entry_descriptor(store, module_id=None, requirement_id=None, version=None, port=0):
    historical = version not in (None, '', 'working')
    descriptor = {'status': 'unavailable', 'url': None, 'projectId': None, 'reused': False,
                  'autoUpdate': False, 'snapshotCommand': _snapshot_command(store, module_id, requirement_id, version)}
    try:
        descriptor['projectId'] = store._project()['id']
        service = ensure_workbench(store, reuse=True, port=port)
        query = {key: value for key, value in (('module', module_id), ('requirement', requirement_id), ('version', version)) if value}
        url = service['requirementMapUrl'] + ('?' + urlencode(query) if query else '')
        descriptor.update(status='ready', url=url, projectId=service['projectId'],
                          reused=service['reused'], autoUpdate=not historical)
    except (FlowError, OSError, ValueError, subprocess.SubprocessError) as exc:
        descriptor.update(error=str(exc), errorStatus=getattr(exc, 'status', 503))
    return descriptor


def default_requirement_map(store):
    """Prepare a stable live entry after a committed write, without re-reading coverage.

    A presentation failure is returned separately and cannot change the business
    save outcome. The service and its discovery live outside project snapshots.
    """
    return _entry_descriptor(store)


def requirement_map_entry(store, module_id=None, requirement_id=None, version=None, port=0):
    """Validate scope first, then return a real snapshot and its viewing entry."""
    snapshot = requirement_map_state(store, module_id, requirement_id, version)
    return {**_entry_descriptor(store, module_id, requirement_id, version, port), 'snapshot': snapshot}
