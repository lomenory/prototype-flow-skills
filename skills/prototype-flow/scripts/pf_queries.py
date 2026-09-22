"""Read selected task or artifact records without building full project state."""
from pf_core import FlowError, business_text, digest, parse_requirements, split_frontmatter, valid_id


def _selected(value, *keys):
    return {key: value[key] for key in keys if key in value}


def _run_summary(run):
    result = _selected(run, 'id', 'stage', 'status', 'createdAt', 'finishedAt', 'error',
                       'inputRevision', 'inputPath', 'requirementIds', 'sharedDocumentIds',
                       'contextScope', 'resumedFrom', 'recoveredOutputs', 'snapshotOutputs')
    result.update(_selected(run, 'change', 'metrics', 'measurements', 'changedFiles'))
    result['inputRequirementIds'] = sorted(run.get('requirementHashes', {}))
    result['documents'] = [_selected(document, 'id', 'title', 'moduleId', 'path', 'revision')
                           for document in run.get('documents', [])]
    outputs = run.get('outputs', [])
    result['outputs'] = (_selected(outputs, 'summary', 'paths', 'artifactIds', 'bindingIds')
                         if isinstance(outputs, dict) else outputs)
    if run.get('framework'):
        result['framework'] = _selected(run['framework'], 'id', 'path', 'entryHtml')
    if run.get('baseArtifact'):
        result['baseArtifact'] = _selected(run['baseArtifact'], 'id', 'path', 'entryHtml')
    result['counts'] = {'documents': len(run.get('documents', [])),
                        'requirements': len(run.get('requirementHashes', {}))}
    return result


def _artifact_inputs(store, base, project, artifacts):
    """Read only PRDs that can determine the selected artifacts' freshness."""
    wanted_requirements = {rid for artifact in artifacts for rid in artifact.get('requirementHashes', {})}
    wanted_documents = {did for artifact in artifacts for did in artifact.get('documentHashes', {})}
    index = store._read('requirement-index.json', {'items': []}, base=base)
    wanted_documents.update(req['documentId'] for req in index.get('items', [])
                            if req['id'] in wanted_requirements)
    documents, requirements = {}, {}
    for module in project['modules']:
        if module['documentId'] not in wanted_documents:
            continue
        path = store._safe(module['documentPath'], base=base)
        if not path.is_file():
            continue
        content = path.read_text(encoding='utf-8')
        metadata, _, _ = split_frontmatter(content)
        if metadata.get('documentId') != module['documentId'] or metadata.get('moduleId') != module['id']:
            raise FlowError('Document identity changed outside an explicit operation', 409,
                            {'path': module['documentPath']})
        documents[module['documentId']] = digest(business_text(content))
        for req in parse_requirements(content, module['documentId'], module['id']):
            if req['id'] in wanted_requirements:
                if req['id'] in requirements:
                    raise FlowError('Duplicate project requirement ID: ' + req['id'])
                requirements[req['id']] = req['hash']
    return documents, requirements


def _artifact_record(store, base, artifact, documents, requirements, full):
    result = dict(artifact) if full else _selected(artifact, 'id', 'title', 'path', 'entryHtml',
        'status', 'runId', 'createdAt', 'inputRevision', 'inputPath', 'requirementIds',
        'frameworkId', 'baseArtifactId', 'sourceDemoPath')
    result['staleRequirementIds'] = sorted(rid for rid, expected in artifact.get('requirementHashes', {}).items()
                                           if requirements.get(rid) != expected)
    result['staleDocumentIds'] = sorted(did for did, expected in artifact.get('documentHashes', {}).items()
                                        if documents.get(did) != expected)
    result['syncStatus'] = 'stale' if result['staleRequirementIds'] or result['staleDocumentIds'] else 'current'
    path = store._safe(artifact['path'], base=base)
    result['integrityStatus'] = ('intact' if path.is_dir() and store._inventory(path) == artifact.get('fileHashes')
                                  else 'changed')
    if result['integrityStatus'] != 'intact':
        result['syncStatus'] = 'invalid'
    if not full:
        result['counts'] = {'requirements': len(artifact.get('requirementHashes', {})),
                            'documents': len(artifact.get('documentHashes', {})),
                            'files': len(artifact.get('fileHashes', {}))}
    return result


def query_state(store, section, record_id=None, version=None, full=False):
    """Preserve state section shapes, with optional identity filtering and full records."""
    if section not in ('runs', 'artifacts'):
        raise FlowError('State section must be runs or artifacts')
    if record_id is not None:
        valid_id(record_id)
    historical = version not in (None, '', 'working')
    with store._transaction(read_only=True):
        base = store._verify_snapshot(version)[0] if historical else store.root
        project = store._project(base)
        result = {'project': _selected(project, 'id', 'name', 'revision'), 'section': section,
                  'historical': historical, 'versionId': version if historical else None}
        if section == 'runs':
            if record_id is not None:
                run = store._read('runs/' + record_id + '.json', base=base)
                runs = [run] if run is not None else []
            else:
                directory = store._safe('.prototype-flow/runs', base=base)
                runs = [store._read('runs/' + path.name, base=base)
                        for path in sorted(directory.glob('*.json'))]
            if record_id is not None and not runs:
                raise FlowError('Run is not available in this version', 404, {'id': record_id})
            result['runs'] = runs if full else [_run_summary(run) for run in runs]
        else:
            collection = store._read('artifacts.json', {'items': [], 'currentArtifactId': None}, base=base)
            artifacts = [artifact for artifact in collection['items']
                         if record_id is None or artifact['id'] == record_id]
            if record_id is not None and not artifacts:
                raise FlowError('Artifact is not available in this version', 404, {'id': record_id})
            documents, requirements = _artifact_inputs(store, base, project, artifacts) if artifacts else ({}, {})
            result['artifacts'] = {'currentArtifactId': collection.get('currentArtifactId'),
                'items': [_artifact_record(store, base, artifact, documents, requirements, full)
                          for artifact in artifacts]}
        return result
