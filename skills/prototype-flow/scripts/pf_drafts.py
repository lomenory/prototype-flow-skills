"""Mutable Demo workspaces with deduplicated recovery revisions and explicit freezes.

Only saved revisions carry evidence. Editing does not create an immutable Demo;
content-addressed recovery data retains the old bytes without copying a directory
for each run. All public mutations share the ProjectStore transaction lock.
"""
import copy
import math
from pathlib import Path
import shutil
import time

from pf_core import FlowError, canonical, digest, now, uid, valid_id
from pf_evidence import page_content


def _draft(store, artifact_id=None):
    registry = store._read('artifacts.json')
    artifact_id = artifact_id or registry.get('currentDraftId') or registry.get('currentArtifactId')
    artifact = next((a for a in registry['items'] if a['id'] == artifact_id), None)
    if not artifact or artifact.get('kind') != 'working-draft':
        raise FlowError('Select a working draft', 404)
    return registry, artifact


def _set_artifact(store, artifact):
    registry = store._read('artifacts.json')
    registry['items'] = [artifact if a['id'] == artifact['id'] else a for a in registry['items']]
    store._write('artifacts.json', registry)


def _remap(value, old, new):
    if isinstance(value, dict):
        return {key: _remap(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_remap(item, old, new) for item in value]
    if isinstance(value, str) and (value == old or value.startswith(old + '/')):
        return new + value[len(old):]
    return value


def _manifest_name(aid, revision):
    valid_id(aid)
    if type(revision) is not int or revision < 0:
        raise FlowError('Draft revision must be a nonnegative integer')
    return 'draft-revisions/' + aid + '/' + str(revision) + '.json'


def _blob(store, content):
    hash_ = digest(content)
    path = store._safe('.prototype-flow/draft-blobs/' + hash_)
    if path.exists():
        if store._file_digest(path) != hash_:
            raise FlowError('Draft recovery blob changed on disk', 409)
    else:
        store._write_bytes(path, content)
    return hash_


def _capture_file(store, path):
    """Reuse a validated CAS object; read source bytes only for new content."""
    hash_ = store._file_digest(path)
    blob = store._safe('.prototype-flow/draft-blobs/' + hash_)
    if blob.is_file():
        if store._file_digest(blob) != hash_:
            raise FlowError('Draft recovery blob changed on disk', 409)
    elif _blob(store, store._file_bytes(path)) != hash_:
        raise FlowError('Draft changed while saving recovery revision; retry', 409)
    return hash_


def _capture(store, artifact, name=None):
    """Capture bytes once, and evidence at the exact revision that was checked."""
    hashes = {}
    directory = store._safe(artifact['path'])
    for path in sorted(directory.rglob('*')):
        store._safe(path.relative_to(store.root))
        if path.is_file():
            hashes[path.relative_to(directory).as_posix()] = _capture_file(store, path)
    if hashes != artifact['fileHashes']:
        raise FlowError('Draft changed while saving recovery revision; retry', 409)
    relations = store._read('relations.json')
    bindings = [copy.deepcopy(b) for b in relations['bindings'] if b['artifactId'] == artifact['id']]
    ids = {b['id'] for b in bindings}
    flows = [copy.deepcopy(f) for f in relations['flows'] if any(
        step.get('bindingId') in ids or step.get('artifactId') == artifact['id']
        for step in f.get('steps', []) if isinstance(step, dict))]
    contents, external = {}, {}
    for binding in bindings:
        if binding.get('screenshot'):
            path = store._safe(binding['screenshot'])
            if path.is_file():
                external[binding['screenshot']] = _capture_file(store, path)
        if binding.get('verified') and binding.get('verificationScope'):
            try:
                if binding.get('verificationHash') == store._binding_fingerprint(binding):
                    contents[binding['id']] = page_content(store, binding, artifact)
            except (FlowError, OSError, UnicodeError):
                pass
    manifest = {'artifact': copy.deepcopy(artifact), 'bindings': bindings, 'flows': flows,
                'fileHashes': hashes, 'externalFiles': external, 'bindingContents': contents, 'createdAt': now()}
    target_name = name or _manifest_name(artifact['id'], artifact['draftRevision'])
    if store._read(target_name) is not None:
        raise FlowError('Draft recovery revision already exists', 409)
    store._write(target_name, manifest)
    return manifest


def _read_revision(store, aid, revision):
    manifest = store._read(_manifest_name(aid, revision))
    if not manifest:
        raise FlowError('Unknown draft revision', 404)
    if manifest.get('artifact', {}).get('id') != aid or manifest['artifact'].get('draftRevision') != revision:
        raise FlowError('Invalid draft revision metadata', 409)
    for relative, expected in manifest.get('fileHashes', {}).items():
        store._safe(relative, base=store._safe(manifest['artifact']['path']))
        path = store._safe('.prototype-flow/draft-blobs/' + expected)
        if not path.is_file() or store._file_digest(path) != expected:
            raise FlowError('Draft recovery data is missing or changed', 409)
    return manifest


def _assert_idle(store, artifact, clean=True):
    if artifact.get('activeRunId'):
        run = store._read('runs/' + valid_id(artifact['activeRunId']) + '.json')
        if run and run.get('status') == 'running':
            raise FlowError('Draft has an unfinished edit; save or finish that task first', 409,
                            {'runId': run['id'], 'artifactId': artifact['id']})
    if clean and store._inventory(store._safe(artifact['path'])) != artifact['fileHashes']:
        raise FlowError('Draft has unsaved changes; save the active task or restore a revision first', 409,
                        {'artifactId': artifact['id'], 'revision': artifact['draftRevision']})


def _clone_relations(store, source, target, keep_current_ids=False):
    """Move live bindings to a draft, or preserve relations inside a frozen record."""
    relations = store._read('relations.json')
    originals = [copy.deepcopy(b) for b in relations['bindings'] if b['artifactId'] == source['id']]
    if not originals:
        originals = copy.deepcopy(source.get('frozenRelations', {}).get('bindings', []))
    ids = {b['id'] for b in originals}
    flows = [copy.deepcopy(f) for f in relations['flows'] if any(
        step.get('bindingId') in ids or step.get('artifactId') == source['id']
        for step in f.get('steps', []) if isinstance(step, dict))]
    if not flows:
        flows = copy.deepcopy(source.get('frozenRelations', {}).get('flows', []))
    if keep_current_ids:
        source['frozenRelations'] = {'bindings': copy.deepcopy(originals), 'flows': copy.deepcopy(flows)}
        _set_artifact(store, source)
    clones = []
    for original in originals:
        clone = _remap(copy.deepcopy(original), source['path'], target['path'])
        clone.update(artifactId=target['id'])
        clone.pop('verificationInheritedFrom', None)
        if clone.get('verified'):
            try:
                if not original.get('verificationHash') or original['verificationHash'] != store._binding_fingerprint(original,
                        artifacts={source['id']: source}):
                    raise FlowError('Source evidence has changed')
                clone['verificationHash'] = store._binding_fingerprint(clone, artifacts={target['id']: target})
                if target.get('kind') == 'working-draft':
                    clone['verificationDraftRevision'] = target['draftRevision']
                else:
                    clone.pop('verificationDraftRevision', None)
                clone['verificationStatus'] = 'preserved'
            except (FlowError, OSError, UnicodeError):
                clone.update(verified=False, status='needs-review', verificationStatus='dependency-changed')
        clones.append(clone)
    for flow in flows:
        for step in flow.get('steps', []):
            if step.get('artifactId') == source['id']:
                step['artifactId'] = target['id']
    if keep_current_ids:
        relations['bindings'] = [b for b in relations['bindings'] if b['id'] not in ids] + clones
        flow_ids = {f['id'] for f in flows}
        relations['flows'] = [f for f in relations['flows'] if f['id'] not in flow_ids] + flows
        store._write('relations.json', relations)
    else:
        target['frozenRelations'] = {'bindings': clones, 'flows': flows}
        _set_artifact(store, target)


def _next_revision(store, artifact):
    directory = store._safe('.prototype-flow/draft-revisions/' + artifact['id'])
    revisions = [int(p.stem) for p in directory.glob('*.json') if p.stem.isdigit()]
    return max([artifact['draftRevision']] + revisions) + 1


def _create_draft(store):
    inputs = store._demo_inputs()
    source, framework = inputs.get('baseArtifact'), inputs['framework']
    aid = uid('DRAFT')
    relative = 'demos/' + aid
    directory = store._safe(relative)
    try:
        if source:
            store._copy_tree(store._safe(source['path']), directory)
            if (directory / '_framework').exists():
                if not source.get('frameworkId'):
                    raise FlowError('Unmanaged _framework conflicts with draft packaging')
                shutil.rmtree(directory / '_framework')
        else:
            directory.mkdir(parents=True)
        store._copy_tree(store._safe(framework['path']), directory / '_framework')
        store._copy_file(store._safe(framework['path']) / 'DESIGN.md', directory / 'DESIGN.md')
        artifact = _remap(copy.deepcopy(source or {}), source['path'], relative) if source else {}
        artifact.update(id=aid, path=relative, kind='working-draft', draftRevision=0,
                        draftSourceArtifactId=source['id'] if source else None,
                        frameworkId=framework['id'], frameworkPath='_framework',
                        entryHtml=(source or {}).get('entryHtml', 'index.html'),
                        createdAt=now(), updatedAt=now(), activeRunId=None, editStatus='ready',
                        fileHashes=store._inventory(directory))
        artifact.pop('frozenRelations', None)
        artifact.pop('frozenFrom', None)
        artifact.setdefault('status', 'candidate')
        artifact.setdefault('evidence', {})
        artifact.setdefault('requirementHashes', {})
        artifact.setdefault('documentHashes', {})
        matches_source = source and artifact['fileHashes'] == source['fileHashes']
        artifact['lastFrozenArtifactId'] = source['id'] if matches_source else None
        artifact['lastFrozenRevision'] = 0 if matches_source else None
        registry = store._read('artifacts.json')
        registry['items'].append(artifact)
        registry.update(currentArtifactId=aid, currentDraftId=aid)
        store._write('artifacts.json', registry)
        if source:
            # Do not preserve stale source evidence merely because its files copied.
            evaluated = {b['id']: b for b in store._evaluated_relations()['bindings']}
            relations = store._read('relations.json')
            relations['bindings'] = [evaluated[b['id']] for b in relations['bindings']]
            store._write('relations.json', relations)
            _clone_relations(store, source, artifact, keep_current_ids=True)
        _capture(store, artifact)
        return artifact
    except Exception:
        if directory.exists():
            shutil.rmtree(directory)
        raise


def _resolve_edit_scope(store, requirement_ids, binding_ids, change, all_requirements):
    if change is not None and not isinstance(change, dict):
        raise FlowError('Demo change must be an object')
    affected = (change or {}).get('affectedBindingIds', []) if isinstance(change, dict) else []
    if not isinstance(affected, list):
        raise FlowError('Demo affectedBindingIds must be an array of stable IDs')
    selected_bindings = binding_ids if binding_ids is not None else affected
    if not isinstance(selected_bindings, list):
        raise FlowError('Demo bindings must be an array of stable IDs')
    selected_bindings = list(dict.fromkeys(valid_id(bid) for bid in selected_bindings))
    known = {b['id']: b for b in store._read('relations.json')['bindings']}
    if set(selected_bindings) - set(known):
        raise FlowError('Unknown affected binding', 404, sorted(set(selected_bindings) - set(known)))
    if requirement_ids is not None and (binding_ids is not None or all_requirements):
        raise FlowError('Choose requirements, bindings or all requirements')
    if binding_ids is not None and all_requirements:
        raise FlowError('Choose bindings or all requirements')
    if requirement_ids is None and selected_bindings and not all_requirements:
        requirement_ids = sorted({rid for bid in selected_bindings for rid in known[bid].get('requirementIds', [])})
        if not requirement_ids:
            raise FlowError('Selected bindings have no requirements; use --requirements to set an explicit scope')
    if binding_ids is not None and change is not None:
        change = copy.deepcopy(change)
        change['affectedBindingIds'] = sorted(set(affected) | set(selected_bindings))
    return requirement_ids, change, selected_bindings


def _affected_modules(store, requirement_ids):
    selected = set(requirement_ids)
    index = store._read('requirement-index.json', {'items': []})
    module_ids = {r['moduleId'] for r in index['items'] if r['id'] in selected}
    return [{key: m[key] for key in ('id', 'title', 'documentId', 'stage') if key in m}
            for m in store._project()['modules'] if m['id'] in module_ids]


def _edit_receipt(store, run, draft):
    declared = set(run.get('affectedBindingIds', [])) | set((run.get('change') or {}).get('affectedBindingIds', []))
    selected = set(run['requirementIds'])
    bindings = [b for b in store._read('relations.json')['bindings'] if b['artifactId'] == draft['id']
                and (b['id'] in declared if declared else selected.intersection(b.get('requirementIds', [])))]
    keys = ('id', 'artifactId', 'requirementIds', 'screenId', 'stateId', 'route', 'fixtureId',
            'screenshot', 'verified', 'verificationStatus')
    run['affectedModules'] = _affected_modules(store, run['requirementIds'])
    run['bindings'] = [{key: b[key] for key in keys if key in b} for b in bindings]
    run['saveTemplate'] = {'outputs': {'summary': (run.get('change') or {}).get('summary', '')}}
    if bindings:
        run['saveTemplate']['bindingPatches'] = [{'id': b['id']} for b in bindings]


def edit_demo(store, requirement_ids=None, shared_document_ids=None, change=None,
              binding_ids=None, all_requirements=False):
    started, before = time.perf_counter(), dict(store.metrics)
    with store._transaction(), store._rollback_writes(), store._read_session():
        requirement_ids, change, selected_bindings = _resolve_edit_scope(
            store, requirement_ids, binding_ids, change, all_requirements)
        expanded_to_all = requirement_ids is None
        registry = store._read('artifacts.json')
        current_id = registry.get('currentDraftId')
        created = not current_id or registry.get('currentArtifactId') != current_id
        if created and current_id:
            _assert_idle(store, _draft(store, current_id)[1])
        draft = _create_draft(store) if created else _draft(store, current_id)[1]
        try:
            _assert_idle(store, draft, clean=False)
            dirty_hashes = store._inventory(store._safe(draft['path']))
            recovery = None
            recovery_revision = None
            if dirty_hashes != draft['fileHashes']:
                recovery_revision = _next_revision(store, draft)
                recovery = _manifest_name(draft['id'], recovery_revision)
                dirty = dict(draft, fileHashes=dirty_hashes, draftRevision=recovery_revision, status='candidate',
                             recoveryOnly=True)
                _capture(store, dirty, recovery)
            checkpoint_id = None
            if isinstance(change, dict) and change.get('tier') == 3 and draft.get('lastFrozenRevision') != draft['draftRevision']:
                if not recovery and (store._safe(draft['path']) / draft['entryHtml']).is_file():
                    checkpoint_id = freeze_demo(store, draft['id'], '重大调整前检查点', _checkpoint=True)['id']
                    draft = _draft(store, draft['id'])[1]
            # Metadata, PRDs and source references are pinned; Demo bytes use CAS.
            run = store.start_run('demo', requirement_ids, shared_document_ids,
                                  base_artifact_id=draft['id'], change=change, _pin_demo_files=False,
                                  _draft_baseline=draft)
            run.update(kind='draft-edit', draftId=draft['id'], artifactId=draft['id'],
                       draftRevision=draft['draftRevision'], beforeRevision=draft['draftRevision'],
                       path=draft['path'], outputs={'draftRevisions': []})
            run['scopeExpandedToAll'] = expanded_to_all
            run['affectedBindingIds'] = selected_bindings
            _edit_receipt(store, run, draft)
            if recovery:
                run['recoveryCheckpoint'] = recovery
                run['recoveryRevision'] = recovery_revision
            if checkpoint_id:
                run['checkpointArtifactId'] = checkpoint_id
            run['metrics']['inputPreparation'] = store._measurement(started, before)
            draft.update(activeRunId=run['id'], editStatus='editing')
            _set_artifact(store, draft)
            store._write('runs/' + run['id'] + '.json', run)
            return run
        except Exception:
            if created:
                shutil.rmtree(store._safe(draft['path']))
            raise


def _payload(payload):
    if not isinstance(payload, dict) or set(payload) - {
            'artifact', 'bindings', 'bindingPatches', 'flows', 'moduleStages', 'outputs', 'measurements'}:
        raise FlowError('Draft save supports artifact, bindings, bindingPatches, flows, moduleStages, outputs and measurements')
    if not isinstance(payload.get('artifact', {}), dict):
        raise FlowError('Draft artifact must be an object')
    measurements = payload.get('measurements', {})
    if (not isinstance(measurements, dict) or set(measurements) - {'editingMs', 'browserVerificationMs', 'verifiedPages'}
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in measurements.values())
            or ('verifiedPages' in measurements and type(measurements['verifiedPages']) is not int)):
        raise FlowError('Measurements must contain observed nonnegative durations and integer verifiedPages')
    outputs = payload.get('outputs', {})
    if not isinstance(outputs, dict) or set(outputs) - {'summary', 'paths'}:
        raise FlowError('Draft outputs support summary and paths')
    if not isinstance(outputs.get('paths', []), list) or any(not isinstance(p, str) for p in outputs.get('paths', [])):
        raise FlowError('Draft output paths must be strings')
    if not isinstance(payload.get('moduleStages', []), list):
        raise FlowError('Draft moduleStages must be an array')


def _binding_updates(relations, draft, payload):
    updates = copy.deepcopy(payload.get('bindings', []))
    patches = payload.get('bindingPatches', [])
    if not isinstance(updates, list) or not isinstance(patches, list):
        raise FlowError('bindings and bindingPatches must be arrays')
    existing = {b['id']: b for b in relations['bindings']}
    used = {b.get('id') for b in updates if isinstance(b, dict)}
    allowed = {'id', 'requirementIds', 'screenId', 'stateId', 'route', 'fixtureId', 'screenshot',
               'verified', 'verificationScope', 'evidence', 'reverify', 'inheritVerificationFrom', 'contractRefs'}
    for patch in patches:
        if not isinstance(patch, dict) or set(patch) - allowed:
            raise FlowError('Binding patches accept editable fields only; identity, fingerprints and revisions are runtime-managed')
        bid = valid_id(patch.get('id'))
        if bid in used:
            raise FlowError('Duplicate binding update across bindings and bindingPatches')
        used.add(bid)
        original = existing.get(bid)
        if not original or original.get('artifactId') != draft['id']:
            raise FlowError('Binding patch must select an existing binding in this working draft', 404, bid)
        if patch.get('reverify') and (patch.get('verified') is not True or
                not isinstance(patch.get('evidence'), dict) or not patch['evidence']):
            raise FlowError('Binding reverify requires verified:true and new actual evidence in this patch')
        updated = copy.deepcopy(original)
        updated.update(copy.deepcopy(patch))
        updates.append(updated)
    return updates


def _save_bindings(store, draft, previous, payload, run):
    relations = store._read('relations.json')
    touched = set()
    actual = set()
    explicitly_unverified = set()
    for group in ('bindings', 'flows'):
        records = {item['id']: item for item in relations[group]}
        updates = _binding_updates(relations, draft, payload) if group == 'bindings' else payload.get(group, [])
        if not isinstance(updates, list):
            raise FlowError(group + ' must be an array of updates')
        seen = set()
        for item in updates:
            if not isinstance(item, dict):
                raise FlowError('Relation update must be an object')
            rid = valid_id(item.get('id'))
            if rid in seen:
                raise FlowError('Duplicate relation update ID')
            seen.add(rid)
            if group == 'bindings':
                if item.get('artifactId') != draft['id']:
                    raise FlowError('Saved bindings must reference this working draft')
                if item.get('reverify') or rid not in records:
                    actual.add(rid)
                touched.add(rid)
                if item.get('verified') is False:
                    explicitly_unverified.add(rid)
            records[rid] = copy.deepcopy(item)
        relations[group] = list(records.values())
    all_draft = {b['id'] for b in relations['bindings'] if b['artifactId'] == draft['id']}
    store.update_relations(relations, changed_binding_ids=all_draft)
    relations = store._read('relations.json')
    old = {b['id']: b for b in previous['bindings']}
    affected = set(run.get('affectedBindingIds', [])) | set((run.get('change') or {}).get('affectedBindingIds', []))
    for binding in relations['bindings']:
        if binding['artifactId'] != draft['id'] or binding['id'] in actual:
            continue
        prior = old.get(binding['id'])
        inherited = False
        if prior and prior.get('verified') and binding['id'] not in affected | explicitly_unverified:
            try:
                old_content = previous.get('bindingContents', {}).get(binding['id'])
                if binding.get('verificationScope') and old_content is not None:
                    inherited = canonical(old_content) == canonical(page_content(store, binding, draft))
                elif (not binding.get('verificationScope') and draft['fileHashes'] == previous['fileHashes']
                      and draft.get('requirementHashes') == previous['artifact'].get('requirementHashes')
                      and draft.get('documentHashes') == previous['artifact'].get('documentHashes')):
                    old_fields = {k: prior.get(k) for k in ('screenId', 'stateId', 'route', 'fixtureId', 'screenshot', 'requirementIds')}
                    screenshot = store._safe(binding.get('screenshot', 'missing-screenshot'))
                    inherited = (old_fields == {k: binding.get(k) for k in old_fields}
                        and screenshot.is_file() and store._file_digest(screenshot) ==
                            previous.get('externalFiles', {}).get(prior.get('screenshot')))
            except (FlowError, OSError, UnicodeError):
                inherited = False
        if inherited:
            binding.update(verified=True, verificationStatus='inherited',
                           verificationDraftRevision=draft['draftRevision'],
                           verificationHash=store._binding_fingerprint(binding),
                           evidence=copy.deepcopy(prior['evidence']),
                           verificationInheritedFrom={'bindingId': prior['id'], 'artifactId': draft['id'],
                               'draftRevision': previous['artifact']['draftRevision'],
                               'verificationHash': prior['verificationHash'], 'inheritedAt': now()})
            binding.pop('status', None)
        else:
            binding.update(verified=False, status='needs-review', verificationStatus='draft-changed')
    store._write('relations.json', relations)
    return sorted(touched)


def save_demo(store, run_id, payload):
    _payload(payload)
    started, before = time.perf_counter(), dict(store.metrics)
    phase_times = {}

    def measured(name, operation):
        phase_started = time.perf_counter()
        try:
            return operation()
        finally:
            phase_times[name] = round(phase_times.get(name, 0) + (time.perf_counter() - phase_started) * 1000, 3)

    with store._transaction(), store._rollback_writes(), store._read_session():
        run = store._read('runs/' + valid_id(run_id) + '.json')
        if not run or run.get('kind') != 'draft-edit' or run.get('status') != 'running':
            raise FlowError('Draft save requires a running draft edit task', 409)
        affected_modules = _affected_modules(store, run['requirementIds'])
        allowed_modules = {module['id'] for module in affected_modules}
        for update in payload.get('moduleStages', []):
            if not isinstance(update, dict) or update.get('id') not in allowed_modules:
                raise FlowError('Demo moduleStages must target modules in this edit scope', 409)
        registry, draft = _draft(store, run['draftId'])
        if (draft.get('activeRunId') != run_id or draft['draftRevision'] != run['beforeRevision']
                or registry.get('currentArtifactId') != draft['id']):
            raise FlowError('Draft baseline changed during this task', 409)
        if measured('inventoryMs', lambda: store._inventory(store._safe(run['inputPath']))) != run['inputFileHashes']:
            raise FlowError('Fixed generation input changed on disk', 409)
        previous = measured('recoveryReadMs', lambda: _read_revision(store, draft['id'], draft['draftRevision']))
        data = copy.deepcopy(payload.get('artifact', {}))
        if (data.get('id', draft['id']) != draft['id'] or data.get('path', draft['path']) != draft['path']
                or data.get('runId', run_id) != run_id):
            raise FlowError('Draft identity, path and task are fixed')
        if set(data) - {'id', 'path', 'runId', 'title', 'entryHtml', 'status', 'evidence'}:
            raise FlowError('Draft artifact supports id, path, runId, title, entryHtml, status and evidence')
        draft.update(data)
        draft.update(runId=run_id, inputRevision=run['inputRevision'], inputPath=run['inputPath'],
                     inputFileHashes=run['inputFileHashes'], inputDocuments=copy.deepcopy(run['documents']),
                     requirementIds=run['requirementIds'], updatedAt=now(),
                     draftRevision=_next_revision(store, draft), activeRunId=None, editStatus='ready')
        retired = {rid for item in store._read('relations.json')['supersessions'] for rid in item.get('from', [])}
        draft['requirementHashes'] = {**{rid: h for rid, h in draft['requirementHashes'].items() if rid not in retired},
                                      **run['requirementHashes']}
        draft['documentHashes'] = {**draft['documentHashes'], **run['documentHashes']}
        directory = store._safe(draft['path'])
        draft['fileHashes'] = measured('inventoryMs', lambda: store._inventory(directory))
        draft['status'] = data.get('status', 'candidate')
        if draft['status'] not in ('candidate', 'verified', 'current'):
            raise FlowError('Draft status must be candidate or verified')
        framework = run['framework']
        if ({p[len('_framework/'):]: h for p, h in draft['fileHashes'].items() if p.startswith('_framework/')}
                != framework['fileHashes'] or draft['fileHashes'].get('DESIGN.md') != framework['fileHashes']['DESIGN.md']):
            raise FlowError('Draft must retain its fixed framework and DESIGN.md', 409)
        store._validate_route(draft['entryHtml'])
        if draft['entryHtml'] not in draft['fileHashes']:
            raise FlowError('Draft entryHtml must name an existing file')
        if draft['status'] in ('verified', 'current'):
            store._framework_review_file(draft, directory)
            if not data.get('evidence'):
                raise FlowError('Verified draft requires evidence for this save')
        _set_artifact(store, draft)
        bindings = measured('evidenceMs', lambda: _save_bindings(store, draft, previous, payload, run))
        validation = measured('validationMs', lambda: store.validate(artifact_ids=[draft['id']]))
        if not validation['ok']:
            raise FlowError('Scoped draft validation failed; edited files and recovery revision preserved', 409, validation)
        # Framework activation still compares the fixed baseline, including concurrent runs.
        draft.update(frameworkBaselineId=run['frameworkBaselineId'], artifactBaselineId=run['artifactBaselineId'])
        if store._frameworks()['currentFrameworkId'] != run['frameworkBaselineId']:
            raise FlowError('Current framework changed during this task', 409)
        if draft['status'] in ('verified', 'current'):
            store._activate_demo_framework(draft)
        _set_artifact(store, draft)
        if payload.get('moduleStages'):
            measured('moduleStagesMs', lambda: store.set_module_stages(payload['moduleStages']))
        affected_modules = _affected_modules(store, run['requirementIds'])
        current_bindings = [b for b in store._read('relations.json')['bindings'] if b['artifactId'] == draft['id']]
        evidence_summary = {
            'verifiedBindingIds': sorted(b['id'] for b in current_bindings if b.get('verified')),
            'needsReviewBindingIds': sorted(b['id'] for b in current_bindings if not b.get('verified')),
            'reverifiedBindingIds': sorted(b['id'] for b in current_bindings
                if b.get('verified') and b.get('verificationStatus') == 'verified')}
        outputs = copy.deepcopy(payload.get('outputs', {}))
        paths = outputs.pop('paths', [])
        # A mutable Demo path is a revision reference, never a historical output copy.
        paths = [p for p in paths if not (p == draft['path'] or p.startswith(draft['path'] + '/'))]
        outputs.update(paths=paths, artifactIds=[draft['id']], bindingIds=bindings,
                       draftRevisions=[{'artifactId': draft['id'], 'revision': draft['draftRevision']}])
        finished = store.finish_run(run_id, 'completed', outputs)
        changed = sorted(p for p in set(previous['fileHashes']) | set(draft['fileHashes'])
                         if previous['fileHashes'].get(p) != draft['fileHashes'].get(p))
        finished.update(draftRevision=draft['draftRevision'], changedFiles=changed, validation=validation,
                        affectedModules=affected_modules, evidenceSummary=evidence_summary)
        if payload.get('measurements'):
            finished['measurements'] = copy.deepcopy(payload['measurements'])
        measured('captureMs', lambda: _capture(store, draft))
        store._bump()
        finished.setdefault('metrics', {})['draftSave'] = dict(store._measurement(started, before), phaseTimes=phase_times)
        store._write('runs/' + run_id + '.json', finished)
        return {'runId': run_id, 'status': 'completed', 'artifactId': draft['id'], 'draftId': draft['id'],
                'draftRevision': draft['draftRevision'], 'path': draft['path'], 'activated': True,
                'bindingIds': bindings, 'changedFiles': changed, 'validation': validation, 'metrics': finished['metrics'],
                'affectedModules': affected_modules, 'evidenceSummary': evidence_summary}


def finish_edit(store, run, status):
    _, draft = _draft(store, run['draftId'])
    if draft.get('activeRunId') != run['id']:
        return
    if status == 'completed':
        raise FlowError('Use demo-save to complete a draft edit')
    dirty = store._inventory(store._safe(draft['path'])) != draft['fileHashes']
    draft.update(activeRunId=None, editStatus='needs-review' if dirty else 'ready')
    _set_artifact(store, draft)


def freeze_demo(store, artifact_id=None, title=None, _checkpoint=False):
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise FlowError('Frozen Demo title must be nonempty')
    with store._transaction(), store._rollback_writes():
        registry, draft = _draft(store, artifact_id)
        _assert_idle(store, draft)
        if draft.get('lastFrozenRevision') == draft['draftRevision']:
            existing = next((a for a in registry['items'] if a['id'] == draft.get('lastFrozenArtifactId')), None)
            if existing:
                return dict(store._intact_artifact(existing['id']), reused=True)
        validation = store.validate(artifact_ids=[draft['id']])
        blocking = [e for e in validation['errors'] if not (_checkpoint and e['code'] == 'artifact-stale')]
        if blocking:
            raise FlowError('Save and validate the draft before freezing', 409, validation)
        aid = uid('DEMO')
        relative = 'demos/' + aid
        target = store._safe(relative)
        try:
            store._copy_tree(store._safe(draft['path']), target)
            artifact = _remap(copy.deepcopy(draft), draft['path'], relative)
            for key in ('draftRevision', 'activeRunId', 'editStatus', 'lastFrozenArtifactId', 'lastFrozenRevision'):
                artifact.pop(key, None)
            artifact.update(id=aid, path=relative, kind='frozen', createdAt=now(),
                            frozenFrom={'artifactId': draft['id'], 'revision': draft['draftRevision']})
            if title is not None:
                artifact['title'] = title.strip()
            if _checkpoint:
                artifact['checkpoint'] = True
                if not validation['ok']:
                    artifact['status'] = 'candidate'
            # Copy external screenshots into the immutable package as well.
            relations = store._read('relations.json')
            screenshot_paths = {}
            for binding in relations['bindings']:
                if binding['artifactId'] != draft['id'] or not binding.get('screenshot'):
                    continue
                source = store._safe(binding['screenshot'])
                if source.is_file() and not binding['screenshot'].startswith(draft['path'] + '/'):
                    relative_shot = '_evidence/' + store._file_digest(source) + source.suffix.lower()
                    store._copy_file(source, target / relative_shot)
                    screenshot_paths[binding['screenshot']] = relative + '/' + relative_shot
            artifact['fileHashes'] = store._inventory(target)
            registry['items'].append(artifact)
            draft.update(lastFrozenArtifactId=aid, lastFrozenRevision=draft['draftRevision'])
            registry['lastFrozenArtifactId'] = aid
            store._write('artifacts.json', registry)
            _clone_relations(store, draft, artifact)
            if screenshot_paths:
                for binding in artifact['frozenRelations']['bindings']:
                    if binding.get('screenshot') in screenshot_paths:
                        binding['screenshot'] = screenshot_paths[binding['screenshot']]
                        if binding.get('verified'):
                            binding['verificationHash'] = store._binding_fingerprint(binding)
                _set_artifact(store, artifact)
            store._bump()
            return dict(artifact, validation=validation, reused=False)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            raise


def restore_demo_revision(store, artifact_id, revision):
    with store._transaction(), store._rollback_writes():
        _, draft = _draft(store, artifact_id)
        _assert_idle(store, draft, clean=False)
        manifest = _read_revision(store, draft['id'], revision)
        directory = store._safe(draft['path'])
        current_hashes = store._inventory(directory)
        recovery = None
        recovery_revision = None
        if current_hashes != draft['fileHashes']:
            recovery_revision = _next_revision(store, draft)
            recovery = _manifest_name(draft['id'], recovery_revision)
            dirty = dict(draft, fileHashes=current_hashes, draftRevision=recovery_revision,
                         status='candidate', recoveryOnly=True)
            _capture(store, dirty, recovery)
        # Stage every byte before touching the visible directory. Directory swap
        # rolls back on metadata failures and preserves the failed edit in CAS.
        staging = store._safe('.prototype-flow/run-work/' + uid('RESTORE'))
        previous_path = store._safe('.prototype-flow/run-work/' + uid('BEFORE'))
        staging.mkdir(parents=True)
        swapped = False
        try:
            for relative, hash_ in manifest['fileHashes'].items():
                store._copy_file(store._safe('.prototype-flow/draft-blobs/' + hash_), staging / relative)
            directory.rename(previous_path)
            staging.rename(directory)
            swapped = True
            restored = copy.deepcopy(manifest['artifact'])
            restored.pop('recoveryOnly', None)
            screenshot_map = {}
            for path_, hash_ in manifest.get('externalFiles', {}).items():
                source = store._safe(path_)
                if path_.startswith(draft['path'] + '/') or (source.is_file() and store._file_digest(source) == hash_):
                    continue
                blob = store._safe('.prototype-flow/draft-blobs/' + hash_)
                if not blob.is_file() or store._file_digest(blob) != hash_:
                    raise FlowError('Draft screenshot recovery data is missing or changed', 409)
                relative = '_evidence/' + hash_ + Path(path_).suffix.lower()
                store._copy_file(blob, directory / relative)
                screenshot_map[path_] = draft['path'] + '/' + relative
            restored['fileHashes'] = store._inventory(directory)
            restored.update(draftRevision=_next_revision(store, draft), activeRunId=None, editStatus='ready',
                            updatedAt=now(), restoredFromRevision=revision,
                            lastFrozenArtifactId=draft.get('lastFrozenArtifactId'),
                            lastFrozenRevision=draft.get('lastFrozenRevision'))
            _set_artifact(store, restored)
            relations = store._read('relations.json')
            old_ids = {b['id'] for b in relations['bindings'] if b['artifactId'] == draft['id']}
            relations['bindings'] = [b for b in relations['bindings'] if b['artifactId'] != draft['id']]
            for binding in copy.deepcopy(manifest['bindings']):
                if binding.get('screenshot') in screenshot_map:
                    binding['screenshot'] = screenshot_map[binding['screenshot']]
                if binding.get('verified') and (manifest['artifact'].get('recoveryOnly') or (screenshot_map and not binding.get('verificationScope'))):
                    binding.update(verified=False, status='needs-review', verificationStatus='restored-needs-review')
                if binding.get('verified'):
                    # Only original saved evidence for the restored bytes is used.
                    binding.update(verificationDraftRevision=restored['draftRevision'],
                                   verificationStatus='restored',
                                   verificationHash=store._binding_fingerprint(binding))
                relations['bindings'].append(binding)
            historical_flow_ids = {f['id'] for f in manifest['flows']}
            relations['flows'] = [f for f in relations['flows'] if f['id'] not in historical_flow_ids and not any(
                s.get('bindingId') in old_ids or s.get('artifactId') == draft['id']
                for s in f.get('steps', []) if isinstance(s, dict))] + copy.deepcopy(manifest['flows'])
            store._write('relations.json', relations)
            _capture(store, restored)
            store._bump()
        except Exception:
            if swapped:
                shutil.rmtree(directory)
                previous_path.rename(directory)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        if previous_path.exists():
            shutil.rmtree(previous_path)
        return {'artifactId': draft['id'], 'path': draft['path'], 'draftRevision': restored['draftRevision'],
                'restoredFromRevision': revision, 'recoveryCheckpoint': recovery, 'recoveryRevision': recovery_revision,
                'validation': store.validate(artifact_ids=[draft['id']])}
