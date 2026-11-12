"""Preliminary README claim checks using executable structure and dependencies."""
import ast
import re

CHECKS = [
    ('FastAPI', r'fastapi', r'fastapi', r'route|endpoint|app'),
    ('React', r'\breact\b', r'react', r'component|jsx|tsx'),
    ('PyTorch', r'pytorch|\btorch\b', r'torch', r'forward|backward|train'),
    ('TensorFlow', r'tensorflow', r'tensorflow|keras', r'fit|predict|train'),
    ('Graph neural networks', r'graph neural|\bgnns?\b', r'torch_geometric|dgl', r'forward|message_passing|gcn|gat|gnn'),
    ('Large language models', r'large language|\bllms?\b', r'transformers|openai|anthropic|llama', r'generate|completion|chat'),
    ('Adaptive learning', r'self.adaptive|adaptive learning|retrain', r'torch|tensorflow|sklearn', r'retrain|partial_fit|update_model|adaptive_train'),
    ('Authentication', r'authenticat|\bauth\b', r'jwt|authlib|passlib', r'login|authenticate|verify_token'),
    ('Databases', r'databases?|postgres|sqlite|mongodb', r'sqlalchemy|sqlite3|pymongo|psycopg', r'query|execute|session|collection'),
    ('Testing', r'\btests?\b|testing|pytest', r'pytest|unittest', r'test_'),
]


def analyze_alignment(contents, issues):
    readmes = [text for p, text in contents.items() if p.lower() == 'readme.md']
    if not readmes:
        return []
    readme = readmes[0]
    imports, definitions, dependencies = [], [], []
    for path, source in contents.items():
        if path.endswith('.py'):
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError, RecursionError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend((a.name, f'{path}:{node.lineno}') for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append((node.module or '', f'{path}:{node.lineno}'))
                elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions.append((node.name, f'{path}:{node.lineno}'))
        elif path.endswith(('requirements.txt', 'pyproject.toml', 'package.json', 'environment.yml')):
            dependencies.append((source, path))
        elif path.endswith(('.jsx', '.tsx')):
            imports.append(('react', path))
            definitions.append(('component', path))
    rows = []
    for title, claim, dep, behavior in CHECKS:
        if not re.search(claim, readme, re.I):
            continue
        evidence = [f'Import {name} ({path})' for name, path in imports if re.search(dep, name, re.I)]
        deps = [f'Declared dependency ({path})' for text, path in dependencies if re.search(dep, text, re.I)]
        funcs = [f'Definition {name} ({path})' for name, path in definitions if re.search(behavior, name, re.I)]
        status = 'Evidence found' if evidence and funcs else 'Partial evidence' if evidence or deps or funcs else 'Not found'
        rows.append(dict(claimed_feature=title, implementation_evidence='; '.join((evidence + deps + funcs)[:6]) or 'No matching structural or dependency evidence found.',
            status=status, suggested_next_action='Review behavior and tests to validate the claim.' if status == 'Evidence found' else 'Locate working implementation and tests, or qualify this README claim.'))
    for issue in issues:
        if issue['issue_type'] == 'Potentially hardcoded prediction':
            rows.append(dict(claimed_feature='Input-dependent predictions', implementation_evidence=f"{issue['file']}:{issue['line']} — {issue['explanation']}",
                status='Partial evidence', suggested_next_action=issue['recommendation']))
    for line in readme.splitlines():
        if re.search(r'accuracy|outperforms|production.ready|multi.language', line, re.I):
            rows.append(dict(claimed_feature=re.sub(r'[*#>`]', '', line).strip()[:180], implementation_evidence='Keyword and structure checks cannot validate this performance or support claim.',
                status='Partial evidence', suggested_next_action='Provide reproducible benchmarks or language-specific tests.'))
    # Also retain feature descriptions beyond the recognized technology list.
    in_features = False
    for line in readme.splitlines():
        if line.startswith('## '):
            in_features = bool(re.search(r'features|capabilities', line, re.I))
            continue
        if not in_features or not re.match(r'^\s*[-*]\s+', line):
            continue
        if any(re.search(claim, line, re.I) for _, claim, _, _ in CHECKS) or re.search(r'accuracy|outperforms|production.ready|multi.language', line, re.I):
            continue
        title = re.sub(r'[*#>`]', '', re.sub(r'^\s*[-*]\s+', '', line)).strip()[:180]
        terms = set(re.findall(r'[a-z]{5,}', title.lower())) - {'which', 'their', 'about', 'using', 'provides', 'supports'}
        matches = [f'{name} ({path})' for name, path in definitions
                   if any(term in name.lower() for term in terms)]
        paths = [path for path in contents if any(term in path.lower() for term in terms)]
        evidence = matches[:4] + paths[:2]
        rows.append(dict(claimed_feature=title, implementation_evidence='; '.join(evidence) or 'No matching definition or file-path evidence found.',
            status='Partial evidence' if evidence else 'Not found', suggested_next_action='Inspect the matching code and add a feature-level demonstration or test.' if evidence else 'Locate supporting implementation or qualify this feature description.'))
    return rows
