"""Read-only structural validation of selected Demos and their dependencies.

This reports integrity and recorded evidence; it never executes a browser check
or changes a binding's persisted verification status.
"""
import copy
from urllib.parse import unquote, urlsplit

from pf_core import FlowError, business_text, digest, parse_requirements, split_frontmatter, valid_id


def _selector(values, label):
    if values is None:
        return set()
    if not isinstance(values, (list, tuple, set)) or not values:
        raise FlowError(label + ' must be a nonempty list of stable IDs')
    return {valid_id(value) for value in values}


def _inputs(store, project, artifacts, bindings, index):
    """Read selected input documents, following requirement dependencies only."""
    wanted_requirements = {rid for artifact in artifacts for rid in artifact.get('requirementHashes', {})}
    wanted_requirements.update(rid for binding in bindings for rid in binding.get('requirementIds', []))
    wanted_documents = {did for artifact in artifacts for did in artifact.get('documentHashes', {})}
    indexed = {req['id']: req for req in index.get('items', [])}
    modules = {module['documentId']: module for module in project['modules']}
    documents, requirements, visited = {}, {}, set()
    while True:
        wanted_documents.update(indexed[rid]['documentId'] for rid in wanted_requirements if rid in indexed)
        pending = wanted_documents - visited
        if not pending:
            break
        for document_id in sorted(pending):
            visited.add(document_id)
            module = modules.get(document_id)
            if not module:
                continue
            path = store._safe(module['documentPath'])
            if not path.is_file():
                continue
            content = store._file_bytes(path).decode('utf-8')
            metadata, _, _ = split_frontmatter(content)
            if metadata.get('documentId') != document_id or metadata.get('moduleId') != module['id']:
                raise FlowError('Document identity changed outside an explicit operation', 409,
                                {'path': module['documentPath']})
            documents[document_id] = {'id': document_id, 'path': module['documentPath'],
                                      'content': content, 'businessHash': digest(business_text(content))}
            for requirement in parse_requirements(content, document_id, module['id']):
                if requirement['id'] in requirements:
                    raise FlowError('Duplicate project requirement ID: ' + requirement['id'])
                requirements[requirement['id']] = requirement
        # Dependencies can reach another selected document already read this pass.
        while True:
            expanded = wanted_requirements | {rid for req in requirements.values()
                if req['id'] in wanted_requirements for rid in req.get('dependsOn', [])}
            if expanded == wanted_requirements:
                break
            wanted_requirements = expanded
    # The index locates unrelated IDs; current selected Markdown is authoritative.
    known_ids = {req['id'] for req in indexed.values() if req['documentId'] not in visited} | set(requirements)
    return documents, requirements, known_ids, wanted_requirements, wanted_documents


def _entry_path(store, artifact, route):
    store._validate_route(route)
    relative = unquote(urlsplit(route).path) or artifact.get('entryHtml', 'index.html')
    return store._safe(relative, base=store._safe(artifact['path']))


def validate_scope(store, artifact_ids=None, binding_ids=None):
    """Validate only explicit artifacts, bindings and their required resources.

    Explicit artifacts include their bindings. Explicit bindings include their
    artifacts without bringing in sibling bindings. Both selectors form a union.
    Missing/invalid selectors are caller errors, not a vacuous successful check.
    """
    requested_artifacts = _selector(artifact_ids, 'artifact_ids')
    requested_bindings = _selector(binding_ids, 'binding_ids')
    if not requested_artifacts and not requested_bindings:
        raise FlowError('Scoped validation requires artifact IDs or binding IDs')
    with store._transaction(read_only=True), store._read_session():
        project = store._project()
        artifacts_by_id = {artifact['id']: artifact for artifact in store._read('artifacts.json')['items']}
        relations = store._read('relations.json')
        bindings_by_id = {binding['id']: binding for binding in relations.get('bindings', [])}
        missing_artifacts = requested_artifacts - set(artifacts_by_id)
        missing_bindings = requested_bindings - set(bindings_by_id)
        if missing_artifacts or missing_bindings:
            raise FlowError('Unknown scoped validation target', 404,
                            {'artifactIds': sorted(missing_artifacts), 'bindingIds': sorted(missing_bindings)})
        selected_bindings = requested_bindings | {bid for bid, binding in bindings_by_id.items()
                                                 if binding.get('artifactId') in requested_artifacts}
        selected_artifacts = requested_artifacts | {bindings_by_id[bid].get('artifactId')
                                                    for bid in selected_bindings}
        artifacts = [artifact for aid, artifact in artifacts_by_id.items() if aid in selected_artifacts]
        bindings = [binding for bid, binding in bindings_by_id.items() if bid in selected_bindings]
        frozen = [(artifact, copy.deepcopy(artifact['frozenRelations'])) for artifact in artifacts
                  if artifact.get('frozenRelations') and artifact.get('kind') != 'working-draft']
        frozen_bindings = [binding for _, saved in frozen for binding in saved.get('bindings', [])]
        bindings += frozen_bindings
        scope = {'artifactIds': sorted(aid for aid in selected_artifacts if aid is not None),
                 'bindingIds': sorted(selected_bindings | {b['id'] for b in frozen_bindings}),
                 'documentIds': [], 'frameworkIds': [], 'flowIds': []}
        errors, warnings = [], []
        try:
            index = store._read('requirement-index.json', {'items': []})
            documents, requirements, known_ids, wanted_requirements, wanted_documents = _inputs(
                store, project, artifacts, bindings, index)
            scope['documentIds'] = sorted(wanted_documents)
            scope['requirementIds'] = sorted(wanted_requirements)
            sources = store._read('sources.json', {'items': []})
            source_ids = {source['id'] for source in sources['items']}
            retired = {rid for item in relations.get('supersessions', []) for rid in item.get('from', [])}
            selected_sources = set()
            for req in requirements.values():
                if req['id'] not in wanted_requirements:
                    continue
                selected_sources.update(req.get('sourceIds', []))
                missing_sources = set(req.get('sourceIds', [])) - source_ids
                if missing_sources:
                    warnings.append({'code': 'source-missing', 'id': req['id'], 'references': sorted(missing_sources)})
                missing = set(req.get('dependsOn', [])) - known_ids
                if missing:
                    warnings.append({'code': 'dependency-needs-review' if missing <= retired else 'dependency-missing',
                                     'id': req['id'], 'references': sorted(missing)})

            frameworks = {framework['id']: framework for framework in store._frameworks()['items']}
            selected_frameworks = {artifact['frameworkId'] for artifact in artifacts if artifact.get('frameworkId')}
            scope['frameworkIds'] = sorted(selected_frameworks)
            for fid in sorted(selected_frameworks & set(frameworks)):
                framework = frameworks[fid]
                path = store._safe(framework['path'])
                if not path.is_dir() or store._inventory(path) != framework['fileHashes']:
                    errors.append({'code': 'framework-mutated', 'id': fid})
            artifact_inventories = {}
            for artifact in artifacts:
                aid = artifact['id']
                path = store._safe(artifact['path'])
                if not path.is_dir():
                    artifact_inventories[aid] = {}
                    errors.append({'code': 'artifact-missing', 'id': aid})
                else:
                    hashes = store._inventory(path)
                    artifact_inventories[aid] = hashes
                    if hashes != artifact.get('fileHashes'):
                        if artifact.get('kind') == 'working-draft':
                            warnings.append({'code': 'draft-unsaved', 'id': aid})
                        else:
                            errors.append({'code': 'artifact-mutated', 'id': aid})
                    framework = frameworks.get(artifact.get('frameworkId'))
                    if artifact.get('frameworkId'):
                        if not framework:
                            errors.append({'code': 'artifact-framework-missing', 'id': aid})
                        elif {name[len('_framework/'):]: value for name, value in hashes.items()
                              if name.startswith('_framework/')} != framework['fileHashes']:
                            errors.append({'code': 'artifact-framework-mismatch', 'id': aid})
                        if artifact.get('status') in ('verified', 'current'):
                            try:
                                store._framework_review_file(artifact, path)
                            except FlowError as exc:
                                if exc.status == 403:
                                    raise
                                warnings.append({'code': 'framework-review-unarchived', 'id': aid,
                                                 'message': '框架验证报告未保存在 Demo 包内，历史证据需复核'})
                    else:
                        warnings.append({'code': 'framework-unbound', 'id': aid})
                if not _entry_path(store, artifact, artifact.get('entryHtml', 'index.html')).is_file():
                    errors.append({'code': 'artifact-entry-missing', 'id': aid})
                stale_requirements = sorted(rid for rid, expected in artifact.get('requirementHashes', {}).items()
                                            if requirements.get(rid, {}).get('hash') != expected)
                stale_documents = sorted(did for did, expected in artifact.get('documentHashes', {}).items()
                                         if documents.get(did, {}).get('businessHash') != expected)
                if stale_requirements or stale_documents:
                    errors.append({'code': 'artifact-stale', 'id': aid, 'staleRequirementIds': stale_requirements,
                                   'staleDocumentIds': stale_documents})
                if not artifact.get('evidence'):
                    warnings.append({'code': 'artifact-unverified', 'id': aid})

            evaluated = store._evaluated_relations(binding_ids=selected_bindings,
                                                   artifact_inventories=artifact_inventories)
            bindings = [binding for binding in evaluated.get('bindings', []) if binding['id'] in selected_bindings]
            for artifact, saved in frozen:
                for binding in saved.get('bindings', []):
                    if binding.get('artifactId') != artifact['id']:
                        errors.append({'code': 'frozen-binding-artifact-mismatch', 'id': binding['id']})
                    if binding.get('verified'):
                        try:
                            valid = bool(binding.get('verificationHash')) and binding['verificationHash'] == store._binding_fingerprint(
                                binding, artifacts=artifacts_by_id)
                        except (FlowError, OSError, UnicodeError):
                            valid = False
                        if not valid:
                            binding.update(verified=False, status='needs-review')
                    bindings.append(binding)
            related_flows = []
            frozen_ids = {artifact['id'] for artifact, _ in frozen}
            live_artifacts = selected_artifacts - frozen_ids
            live_requirements = wanted_requirements if live_artifacts or selected_bindings else set()
            for flow in relations.get('flows', []):
                related = bool(live_requirements.intersection(flow.get('requirementIds', [])))
                steps = flow.get('steps', [])
                for step in steps if isinstance(steps, list) else []:
                    if not isinstance(step, dict):
                        continue
                    related = related or step.get('bindingId') in selected_bindings
                    related = related or step.get('artifactId') in live_artifacts
                    related = related or bool(live_requirements.intersection(
                        store._step_requirements(step, relations.get('bindings', []))))
                if related:
                    related_flows.append(flow)
            scope['flowIds'] = [flow['id'] for flow in related_flows]
            errors.extend(store._flow_step_errors({'flows': related_flows,
                                                   'bindings': relations.get('bindings', [])}, known_ids))
            for _, saved in frozen:
                saved_ids = {binding['id'] for binding in saved.get('bindings', [])}
                context = [binding for binding in relations.get('bindings', []) if binding['id'] not in saved_ids]
                errors.extend(store._flow_step_errors({'flows': saved.get('flows', []),
                    'bindings': context + saved.get('bindings', [])}, known_ids))
                related_flows.extend(saved.get('flows', []))
            scope['flowIds'] = sorted({flow['id'] for flow in related_flows})
            for item in bindings + related_flows:
                if set(item.get('requirementIds', [])) - known_ids:
                    errors.append({'code': 'relation-requirement-missing', 'id': item['id']})
                if item.get('status') == 'needs-review':
                    warnings.append({'code': 'relation-needs-review', 'id': item['id']})
            for binding in bindings:
                artifact = artifacts_by_id.get(binding.get('artifactId'))
                if artifact is None:
                    errors.append({'code': 'binding-artifact-missing', 'id': binding['id']})
                elif not _entry_path(store, artifact, binding.get('route', '')).is_file():
                    errors.append({'code': 'binding-entry-missing', 'id': binding['id']})
                if binding.get('screenshot') and not store._safe(binding['screenshot']).is_file():
                    warnings.append({'code': 'screenshot-missing', 'id': binding['id']})
                if not binding.get('verified'):
                    warnings.append({'code': 'entry-unverified', 'id': binding['id']})

            selected_source_records = {'items': [source for source in sources['items'] if source['id'] in selected_sources]}
            for relative in store._referenced_files(list(documents.values()), selected_source_records,
                                                    {'bindings': bindings}):
                if not store._safe(relative).is_file():
                    warnings.append({'code': 'referenced-file-missing', 'path': relative})
        except (FlowError, OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'code': 'invalid-project', 'message': str(exc)})
        return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'scope': scope}
