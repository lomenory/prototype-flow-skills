"""Assemble existing scoped evidence; never execute or invent verification.

The result is a candidate for demo-save, not a saved revision. Source reports
remain authoritative and their recorded scope and outcomes are preserved.
"""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import unquote, urlsplit

from pf_core import FlowError, digest, valid_id
from pf_drafts import _draft
from pf_validation import _inputs


def _object(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise FlowError(label + ' has unsupported fields or is not an object')
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise FlowError(label + ' must be a nonempty string')
    return value


def _strings(value, label, empty=True):
    if (not isinstance(value, list) or (not value and not empty)
            or any(not isinstance(item, str) or not item for item in value)
            or len(set(value)) != len(value)):
        raise FlowError(label + ' must be an array of unique strings')
    return value


def _file(store, relative, base=None):
    _text(relative, 'Evidence path')
    path = store._safe(relative, base=base, must_exist=True)
    if not path.is_file():
        raise FlowError('Evidence must name a file', 400, relative)
    return path


def _hash(store, path, expected):
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise FlowError('Evidence requires recorded SHA-256 hashes')
    if store._file_digest(path) != expected:
        raise FlowError('Recorded evidence is stale: file hash changed', 409,
                        {'path': path.relative_to(store.root).as_posix()})


def _read_report(store, source, run, draft, allowed):
    path = _file(store, source)
    raw = store._file_bytes(path)
    try:
        report = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise FlowError('Evidence report must be UTF-8 JSON', details=source) from exc
    _object(report, ('schemaVersion', 'runId', 'draftId', 'draftRevision', 'kind', 'method',
                     'scope', 'fileHashes', 'results', 'screenshots'), 'Evidence report')
    if report.get('schemaVersion') != 1:
        raise FlowError('Evidence report requires schemaVersion:1')
    if (report.get('runId') != run['id'] or report.get('draftId') != draft['id']
            or type(report.get('draftRevision')) is not int
            or report['draftRevision'] != run['beforeRevision']):
        raise FlowError('Evidence report does not match this edit baseline', 409, source)
    if report.get('kind') not in ('browser', 'static', 'framework', 'inherited'):
        raise FlowError('Evidence kind must be browser, static, framework or inherited')
    _text(report.get('method'), 'Evidence method')
    scope = _object(report.get('scope'), ('bindingIds', 'files', 'viewports'), 'Evidence scope')
    bids = _strings(scope.get('bindingIds'), 'scope.bindingIds')
    if set(bids) - set(allowed):
        raise FlowError('Evidence binding is outside this edit scope', 409, sorted(set(bids) - set(allowed)))
    files = _strings(scope.get('files'), 'scope.files', empty=False)
    hashes = report.get('fileHashes')
    if not isinstance(hashes, dict) or set(hashes) != set(files):
        raise FlowError('fileHashes must exactly cover scope.files')
    directory = store._safe(draft['path'])
    for relative in files:
        _hash(store, _file(store, relative, directory), hashes[relative])
    viewports = scope.get('viewports', [])
    if not isinstance(viewports, list):
        raise FlowError('scope.viewports must be an array')
    for viewport in viewports:
        _object(viewport, ('width', 'height'), 'Viewport')
        if any(type(viewport.get(key)) is not int or viewport[key] <= 0 for key in ('width', 'height')):
            raise FlowError('Viewport width and height must be positive integers')
    if report['kind'] == 'browser' and (not bids or not viewports):
        raise FlowError('Browser evidence requires bindingIds and observed viewports')
    if report['kind'] == 'browser':
        for bid in bids:
            entry = unquote(urlsplit(allowed[bid]['route']).path) or draft.get('entryHtml', 'index.html')
            if entry not in files:
                raise FlowError('Browser fileHashes must include each observed binding entry', details=bid)
    results = report.get('results')
    if not isinstance(results, list) or not results:
        raise FlowError('Evidence results must be a nonempty array')
    checked = set()
    for result in results:
        _object(result, ('id', 'status', 'summary', 'bindingIds', 'source'), 'Evidence result')
        identifier = _text(result.get('id'), 'Result id')
        if identifier in checked:
            raise FlowError('Duplicate evidence result id')
        checked.add(identifier)
        if result.get('status') not in ('passed', 'failed', 'not-run', 'inherited'):
            raise FlowError('Result status must be passed, failed, not-run or inherited')
        _text(result.get('summary'), 'Result summary')
        targets = _strings(result.get('bindingIds', bids), 'Result bindingIds')
        if set(targets) - set(bids):
            raise FlowError('Result bindingIds must stay within report scope')
        if result['status'] == 'inherited':
            _file(store, result.get('source'))
        elif 'source' in result:
            _file(store, result['source'])
        if report['kind'] == 'inherited' and result['status'] != 'inherited':
            raise FlowError('Inherited reports cannot claim new passed results')
    shots = report.get('screenshots', {})
    if not isinstance(shots, dict) or set(shots) - set(bids):
        raise FlowError('Report screenshots must map scoped binding IDs')
    for bid, shot in shots.items():
        _object(shot, ('path', 'sha256'), 'Screenshot')
        shot_path = _file(store, shot.get('path'))
        if directory not in shot_path.parents:
            raise FlowError('Screenshots must be existing files inside this working draft', 403)
        _hash(store, shot_path, shot.get('sha256'))
    return {'source': source, 'sha256': digest(raw), **copy.deepcopy(report)}


def _baseline(store, run_id):
    run = store._read('runs/' + valid_id(run_id) + '.json')
    if not run or run.get('kind') != 'draft-edit' or run.get('status') != 'running':
        raise FlowError('Evidence assembly requires a running draft edit task', 409)
    registry, draft = _draft(store, run['draftId'])
    if (draft.get('activeRunId') != run_id or draft['draftRevision'] != run['beforeRevision']
            or registry.get('currentArtifactId') != draft['id']):
        raise FlowError('Draft baseline changed during this task', 409)
    if store._inventory(store._safe(run['inputPath'])) != run['inputFileHashes']:
        raise FlowError('Fixed generation input changed on disk', 409)
    documents, requirements, _, _, _ = _inputs(
        store, store._project(), [run], [], store._read('requirement-index.json', {'items': []}))
    if (any(documents.get(key, {}).get('businessHash') != expected for key, expected in run['documentHashes'].items())
            or any(requirements.get(key, {}).get('hash') != expected for key, expected in run['requirementHashes'].items())):
        raise FlowError('PRD input changed after this edit started', 409)
    original = {binding['id']: binding for binding in run.get('bindings', [])}
    current = {binding['id']: binding for binding in store._read('relations.json')['bindings']}
    fields = ('artifactId', 'requirementIds', 'screenId', 'stateId', 'route', 'fixtureId')
    for bid, binding in original.items():
        other = current.get(bid, {})
        if other.get('artifactId') != draft['id'] or any(binding.get(k) != other.get(k) for k in fields):
            raise FlowError('Binding baseline changed during this edit', 409, bid)
    return run, draft, original


def _inherited_framework(store, run, draft, requested):
    _object(requested, ('mode',), 'frameworkReview')
    if requested.get('mode') != 'inherited':
        raise FlowError('frameworkReview supports explicit mode:inherited only')
    baseline = run.get('baseArtifact', {})
    if (baseline.get('status') not in ('verified', 'current')
            or baseline.get('frameworkId') != run['framework']['id']):
        raise FlowError('Framework inheritance requires the verified fixed baseline', 409)
    directory = store._safe(draft['path'])
    original = copy.deepcopy(baseline.get('evidence', {}).get('frameworkReview'))
    source = store._framework_review_file({'evidence': {'frameworkReview': original}}, directory)
    relative = source.relative_to(directory).as_posix()
    _hash(store, source, baseline.get('fileHashes', {}).get(relative))
    if (store._inventory(directory / '_framework') != run['framework']['fileHashes']
            or store._file_digest(directory / 'DESIGN.md') != run['framework']['fileHashes']['DESIGN.md']):
        raise FlowError('Framework changed; inherited review is no longer applicable', 409)
    return dict(original, mode='inherited', fromArtifactId=baseline['id'],
                fromDraftRevision=run['beforeRevision'])


def _assemble(store, run_id, payload):
    _object(payload, ('reports', 'screenshots', 'summary', 'artifactStatus', 'frameworkReport',
                      'frameworkReview'), 'Assembly input')
    sources = _strings(payload.get('reports'), 'reports', empty=False)
    run, draft, bindings = _baseline(store, run_id)
    reports = [_read_report(store, source, run, draft, bindings) for source in sources]
    mappings = payload.get('screenshots', {})
    if not isinstance(mappings, dict) or set(mappings) - set(bindings):
        raise FlowError('screenshots must map binding IDs within this edit scope')
    by_binding = {}
    for report in reports:
        if report['kind'] != 'browser':
            continue
        for bid in report['scope']['bindingIds']:
            relevant = [item for item in report['results'] if bid in item.get('bindingIds', report['scope']['bindingIds'])]
            if not relevant:
                raise FlowError('Browser report has a binding without a recorded result', details=bid)
            by_binding.setdefault(bid, []).append((report, relevant))
    patches = []
    for bid, observed in by_binding.items():
        observed_files = {file for report, _ in observed for file in report['scope']['files']}
        failed = any(result['status'] == 'failed' and (
            bid in result.get('bindingIds', report['scope']['bindingIds'])
            or (not result.get('bindingIds', report['scope']['bindingIds'])
                and observed_files.intersection(report['scope']['files'])))
            for report in reports for result in report['results'])
        passed = [(report, [result for result in results if result['status'] == 'passed'])
                  for report, results in observed if any(result['status'] == 'passed' for result in results)]
        if failed or not passed:
            continue
        report, results = passed[-1]
        shot = report.get('screenshots', {}).get(bid)
        if not shot:
            raise FlowError('Passed browser binding requires its recorded screenshot', details=bid)
        if bid in mappings and mappings[bid] != shot['path']:
            raise FlowError('Screenshot mapping differs from the browser report', 409, bid)
        source_path = _file(store, report['source'])
        if store._safe(draft['path']) not in source_path.parents:
            raise FlowError('Verified binding report must already exist inside this working draft', 403)
        patches.append({'id': bid, 'screenshot': shot['path'], 'verified': True, 'reverify': True,
                        'evidence': {'method': report['method'], 'source': report['source'],
                                     'sourceHash': report['sha256'], 'scope': copy.deepcopy(report['scope']),
                                     'summary': '; '.join(item['summary'] for item in results)}})
    if set(mappings) - {patch['id'] for patch in patches}:
        raise FlowError('Screenshot mappings require passed browser evidence; not-run or inherited results cannot reverify')
    template = copy.deepcopy(run.get('saveTemplate', {}))
    summary = payload.get('summary', template.get('outputs', {}).get('summary', ''))
    _text(summary, 'Assembly summary')
    save = {'artifact': copy.deepcopy(template.get('artifact', {})), 'outputs': {'summary': summary}}
    status = payload.get('artifactStatus', 'candidate')
    if status not in ('candidate', 'verified', 'current'):
        raise FlowError('artifactStatus must be candidate, verified or current')
    save['artifact']['status'] = status
    if patches:
        save['bindingPatches'] = patches
    framework_source = payload.get('frameworkReport')
    if framework_source is not None and 'frameworkReview' in payload:
        raise FlowError('Choose frameworkReport or inherited frameworkReview, not both')
    if 'frameworkReview' in payload:
        review = _inherited_framework(store, run, draft, payload['frameworkReview'])
        save['artifact']['evidence'] = {'frameworkReview': review}
    elif framework_source is not None or status in ('verified', 'current'):
        framework = next((item for item in reports if item['source'] == framework_source), None)
        if not framework or framework['kind'] != 'framework' or any(item['status'] != 'passed' for item in framework['results']):
            raise FlowError('Verified/current artifact requires a passed frameworkReport from reports')
        review = {'mode': 'observed', 'source': framework_source,
                  'summary': '; '.join(item['summary'] for item in framework['results'])}
        store._framework_review_file({'evidence': {'frameworkReview': review}}, store._safe(draft['path']))
        save['artifact']['evidence'] = {'frameworkReview': review}
    if status in ('verified', 'current') and any(item['status'] == 'failed' for report in reports for item in report['results']):
        raise FlowError('Failed evidence cannot produce a verified/current artifact')
    report = {'schemaVersion': 1, 'runId': run_id, 'draftId': draft['id'], 'draftRevision': run['beforeRevision'],
              'status': 'assembled', 'summary': summary, 'reports': reports,
              'proposedReverificationBindingIds': sorted(patch['id'] for patch in patches),
              'bindingsWithoutNewBrowserEvidence': sorted(set(bindings) - {patch['id'] for patch in patches}),
              'verificationPerformed': False}
    return {'runId': run_id, 'draftId': draft['id'], 'savePayload': save, 'validationReport': report}


def assemble_evidence(store, run_id, payload, output=None):
    """Return an unsaved payload/report, optionally publish both to new local_tasks/.

    Output is a project-relative new directory. No project registry or Demo bytes
    are modified, and the scratch validation report is not claimed as Demo proof.
    """
    published = None
    temporary = None
    try:
        with store._transaction(read_only=output is None), store._read_session():
            result = _assemble(store, run_id, payload)
            if output is not None:
                target = store._safe(_text(output, 'Output directory'))
                if Path(output).parts[0] != 'local_tasks' or len(Path(output).parts) < 2:
                    raise FlowError('Assembly output must be a new directory under local_tasks/', 403)
                protected = (store._read('artifacts.json', {'items': []})['items']
                             + store._frameworks()['items'])
                for item in protected:
                    directory = store._safe(item['path'])
                    if target == directory or directory in target.parents:
                        raise FlowError('Assembly output cannot be inside a registered Demo or framework', 403)
                if target.exists():
                    raise FlowError('Assembly output already exists; choose a new directory', 409)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = Path(tempfile.mkdtemp(prefix='.pf-assemble-', dir=str(target.parent)))
                for filename, key in (('save.json', 'savePayload'), ('validation-report.json', 'validationReport')):
                    data = (json.dumps(result[key], ensure_ascii=False, indent=2) + '\n').encode('utf-8')
                    with (temporary / filename).open('wb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                store._safe(output)
                if target.exists():
                    raise FlowError('Assembly output already exists; choose a new directory', 409)
                os.rename(temporary, target)
                published, temporary = target, None
                result.update(output=output, savePath=output.rstrip('/') + '/save.json',
                              reportPath=output.rstrip('/') + '/validation-report.json')
        return result
    except Exception:
        if published is not None:
            shutil.rmtree(published)
        raise
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
