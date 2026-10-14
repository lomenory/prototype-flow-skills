"""Conservative, explicit reuse of page evidence across immutable Demo versions."""
import copy
from html.parser import HTMLParser
from pathlib import PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit

from pf_core import FlowError, canonical, now


REVIEW_MESSAGES = {
    'affected-page': '此页面在本轮声明的修改范围内，需要对应的新验证。',
    'requirement-input': '需求依据已变化，需要核对页面是否符合新规则。',
    'shared-document': '关联文档依据已变化，需要核对其中的共享规则。',
    'dependency-content': '页面或共享资源内容已变化，原验证不能直接沿用。',
    'unresolved-dependencies': '存在无法确定的动态或外部依赖，原验证不能跨修订沿用。',
    'prior-needs-review': '此前已待复核，本轮尚未提供新的有效验证。',
    'new-binding': '此页面尚未建立有效验证依据。',
    'explicitly-unverified': '本轮明确将此页面保留为待验证。',
    'page-state': '页面入口、状态或演示数据关联已变化。',
    'screenshot-content': '截图内容或位置已变化，需要核对新的页面证据。',
    'missing-verification-scope': '旧证据没有完整页面依赖范围，内容变化后不能直接沿用。',
    'evidence-unavailable': '无法完整读取或核对原验证依据。',
    'evidence-changed': '原验证指纹已失效，需要重新核对页面证据。',
    'draft-editing': '工作稿正在编辑或尚未保存，旧证据暂不计入当前验证。',
    'entry-unavailable': '登记的页面入口当前不可用。',
}


def review_reason(code, **details):
    """Additive explanation only; never changes evidence validity or scope."""
    return {'code': code, 'message': REVIEW_MESSAGES[code], **{key: value for key, value in details.items() if value}}


def changed_keys(before, after):
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def merge_review_reasons(reasons):
    merged = {}
    if not isinstance(reasons, list):
        return []
    for reason in reasons:
        if not isinstance(reason, dict) or reason.get('code') not in REVIEW_MESSAGES:
            continue
        current = merged.setdefault(reason['code'], review_reason(reason['code']))
        for field in ('paths', 'requirementIds', 'documentIds'):
            if isinstance(reason.get(field), list):
                current[field] = sorted(set(current.get(field, [])) | {value for value in reason[field] if isinstance(value, str)})
    return list(merged.values())


def content_review_reasons(before, after):
    reasons = []
    for field, code, detail in (('requirementHashes', 'requirement-input', 'requirementIds'),
                               ('documentHashes', 'shared-document', 'documentIds'),
                               ('dependencies', 'dependency-content', 'paths')):
        changed = changed_keys(before.get(field, {}), after.get(field, {}))
        if changed:
            reasons.append(review_reason(code, **{detail: changed}))
    if before.get('unresolvedDependencies') != after.get('unresolvedDependencies'):
        reasons.append(review_reason('unresolved-dependencies'))
    if before.get('screenshotHash') != after.get('screenshotHash'):
        reasons.append(review_reason('screenshot-content'))
    if any(before.get(key) != after.get(key) for key in
           ('screenId', 'stateId', 'route', 'fixtureId', 'requirementIds', 'verificationScope', 'frameworkId')):
        reasons.append(review_reason('page-state'))
    return reasons


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.uncertain = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base' or 'srcdoc' in attrs:
            self.uncertain = True
        for key in ('src', 'poster', 'data' if tag == 'object' else 'src'):
            if attrs.get(key):
                self.urls.append(attrs[key])
        if tag == 'link' and attrs.get('href'):
            self.urls.append(attrs['href'])
        if attrs.get('srcset'):
            self.uncertain = True
        self.urls.extend(css_urls(attrs.get('style', '')))


def css_urls(text):
    return re.findall(r'url\(\s*[\'"]?([^\s)\'"]+)', text, re.I) + re.findall(
        r'@import\s+[\'"]([^\'"]+)', text, re.I)


def page_content(store, binding, artifact, base=None):
    """A declared complete scope plus conservative shared-code/resource dependencies.

    Unknown dynamic or external dependencies retain a whole-artifact dependency.
    They can be verified normally, but cannot be inherited into a new artifact.
    """
    with store._read_session():
        return _page_content(store, binding, artifact, base)


def _page_content(store, binding, artifact, base=None):
    scope = binding.get('verificationScope')
    if (not isinstance(scope, dict) or scope.get('complete') is not True
            or set(scope) - {'files', 'complete'} or not isinstance(scope.get('files'), list)
            or not scope['files'] or any(not isinstance(p, str) for p in scope['files'])):
        raise FlowError('verificationScope requires complete:true and non-empty Demo-relative files')
    manifest = artifact.get('fileHashes', {})
    directory = store._safe(artifact['path'], base=base)
    entry = unquote(urlsplit(binding['route']).path) or artifact.get('entryHtml', 'index.html')
    files = set(scope['files']) | {entry, 'DESIGN.md'}
    files.update(p for p in manifest if p.startswith('_framework/')
                 or PurePosixPath(p).suffix.lower() in ('.js', '.mjs', '.cjs', '.css', '.json'))
    if 'DESIGN.md' not in manifest:
        files.discard('DESIGN.md')
    pending, visited, uncertain = list(files), set(), False
    dynamic = re.compile(r'\b(fetch|XMLHttpRequest|WebSocket|EventSource|Worker|eval|Function)\b|'
                         r'\bimport\s*\(|\.(src|href)\s*=|\bsetAttribute\s*\(')
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        path = store._safe(relative, base=directory, must_exist=True)
        if relative not in manifest or not path.is_file():
            raise FlowError('Verification dependency is not in the immutable Demo', details=relative)
        visited.add(relative)
        suffix = path.suffix.lower()
        if suffix not in ('.html', '.htm', '.css', '.js', '.mjs', '.cjs'):
            continue
        raw = store._file_bytes(path)
        if store._file_digest(path) != manifest[relative]:
            raise FlowError('Verification dependency changed on disk', 409, {'path': relative})
        text = raw.decode('utf-8')
        urls = css_urls(text)
        if suffix in ('.html', '.htm'):
            parser = Resources()
            parser.feed(text)
            urls.extend(parser.urls)
            uncertain = uncertain or parser.uncertain
        if suffix != '.css':
            uncertain = uncertain or bool(dynamic.search(text))
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme == 'data' or url.startswith('#'):
                continue
            if parsed.scheme or parsed.netloc or url.startswith('/'):
                uncertain = True
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(relative), unquote(parsed.path)))
            store._safe(target, base=directory)
            pending.append(target)
    content = {key: binding.get(key) for key in
               ('screenId', 'stateId', 'route', 'fixtureId', 'requirementIds', 'verificationScope')}
    content['dependencies'] = {p: manifest[p] for p in sorted(visited)}
    content['frameworkId'] = artifact.get('frameworkId')
    content['requirementHashes'] = {rid: artifact.get('requirementHashes', {}).get(rid)
                                    for rid in binding.get('requirementIds', [])}
    if any(h is None for h in content['requirementHashes'].values()):
        raise FlowError('Verification scope references requirements absent from the Demo inputs')
    # Shared prose can affect a page even when its own requirement block is unchanged.
    content['documentHashes'] = artifact.get('documentHashes', {})
    screenshot = store._safe(binding['screenshot'], base=base, must_exist=True)
    content['screenshotHash'] = store._file_digest(screenshot)
    if uncertain:
        content['unresolvedDependencies'] = (artifact['id'] + '@' + str(artifact['draftRevision'])
                                             if artifact.get('kind') == 'working-draft' else artifact['id'])
    return content


def inherit_binding(store, binding, source, artifacts, intact):
    if not source or not source.get('verified') or not source.get('verificationScope'):
        raise FlowError('Evidence inheritance requires a verified source with a complete page scope')
    if not binding.get('verificationScope'):
        binding['verificationScope'] = copy.deepcopy(source['verificationScope'])
    for aid in (source['artifactId'], binding['artifactId']):
        if aid not in intact:
            intact[aid] = store._intact_artifact(aid)
    if source.get('verificationHash') != store._binding_fingerprint(source, artifacts=artifacts):
        raise FlowError('Source evidence is no longer valid; reverify the affected page', 409)
    old = page_content(store, source, artifacts[source['artifactId']])
    new = page_content(store, binding, artifacts[binding['artifactId']])
    if canonical(old) != canonical(new):
        raise FlowError('Page, shared dependencies, inputs or screenshot changed; reverify this binding', 409)
    binding.update(verified=True, verificationStatus='inherited',
                   verificationHash=store._binding_fingerprint(binding, artifacts=artifacts),
                   evidence=copy.deepcopy(source['evidence']),
                   verificationInheritedFrom={'bindingId': source['id'], 'artifactId': source['artifactId'],
                       'verificationHash': source['verificationHash'], 'inheritedAt': now()})
    binding.pop('status', None)
    for field in ('reviewReasons', 'reviewChange', 'reviewRevision'):
        binding.pop(field, None)
