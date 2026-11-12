"""Read-only static checks. Findings are signals, not proof of defects."""
import ast
import io
import re
import tokenize

from radon.complexity import cc_visit


def complexity(source):
    try:
        return max((block.complexity for block in cc_visit(source)), default=1)
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return None


def analyze_source(path, source):
    issues = []
    recovery_note = ''

    def add(line, severity, kind, explanation, recommendation):
        issues.append(dict(file=path, line=line, severity=severity, issue_type=kind,
                           explanation=explanation + recovery_note, recommendation=recommendation))

    if not path.endswith('.py'):
        for number, line in enumerate(source.splitlines(), 1):
            if re.search(r'\b(TODO|FIXME)\b', line):
                add(number, 'Info', 'Maintenance marker', line.strip()[:180],
                    'Review this marker and track any outstanding work.')
        return issues
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and re.search(r'\b(TODO|FIXME)\b', token.string):
                add(token.start[0], 'Info', 'Maintenance marker', token.string[:180],
                    'Resolve or track the outstanding maintenance task.')
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        add(getattr(exc, 'lineno', 1) or 1, 'High', 'Syntax error', str(exc),
            'Correct the syntax before importing or running this module.')
        # Some starter repositories accidentally save Markdown instructions as .py.
        # Inspect a fenced Python block separately, retaining original line numbers.
        # The syntax error remains a finding; the file is never treated as valid.
        fence = re.search(r'^```(?:python|py)\s*\n', source, re.M)
        if not fence:
            return issues
        recovered = '\n' * source[:fence.end()].count('\n') + source[fence.end():].split('```', 1)[0]
        try:
            tree = ast.parse(recovered)
        except (SyntaxError, ValueError, RecursionError):
            return issues
        source = recovered
        recovery_note = ' Found in an embedded Python block; the full file still has a syntax error.'
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                if name not in used and name != '*' and getattr(node, 'module', '') != '__future__' and not path.endswith('__init__.py'):
                    add(node.lineno, 'Low', 'Potentially unused import (heuristic)',
                        f'{name} has no direct name references; re-exports and dynamic usage may be valid.',
                        'Check indirect usage before removing the import.')
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            add(node.lineno, 'Medium', 'Bare except', 'Catches all exceptions, including process interrupts.',
                'Catch specific exception types and handle or log the failure.')
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            params = len(node.args.posonlyargs + node.args.args + node.args.kwonlyargs)
            if length > 60:
                add(node.lineno, 'Medium', 'Long function', f'{node.name} spans {length} lines.',
                    'Extract cohesive operations into smaller named functions.')
            if params > 6:
                add(node.lineno, 'Medium', 'Excessive parameters', f'{node.name} has {params} explicit parameters.',
                    'Group related values into a typed configuration or request object.')
            if re.search(r'predict|infer|probability', node.name, re.I):
                args = {arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
                refs = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                constants = []
                for ret in (n for n in ast.walk(node) if isinstance(n, ast.Return)):
                    value = ret.value
                    if isinstance(value, ast.Call):
                        constants.extend(k.value for k in value.keywords if re.search(r'risk|probab|score', k.arg or ''))
                    if isinstance(value, ast.Dict):
                        constants.extend(v for k, v in zip(value.keys, value.values) if isinstance(k, ast.Constant) and re.search(r'risk|probab|score', str(k.value)))
                    if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
                        constants.append(value)
                if any(isinstance(c, ast.Constant) for c in constants) and not (args & refs):
                    add(node.lineno, 'High', 'Potentially hardcoded prediction',
                        f'{node.name} returns a constant score or risk field without referencing its input parameters.',
                        'Derive outputs from the supplied input and label any heuristic score explicitly.')
    controls = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)

    def nesting(node, depth=0):
        current = depth + int(isinstance(node, controls))
        if current == 5 and isinstance(node, controls):
            add(node.lineno, 'Medium', 'Deep nesting', 'Control flow reaches five nested levels.',
                'Use guard clauses or extract inner control flow into a helper.')
        for child in ast.iter_child_nodes(node):
            nesting(child, 0 if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else current)

    nesting(tree)
    for block in cc_visit(source):
        if block.complexity > 10:
            add(block.lineno, 'High' if block.complexity > 20 else 'Medium', 'Cyclomatic complexity',
                f'{block.name} has cyclomatic complexity {block.complexity}.',
                'Split decision branches into focused functions and test independent paths.')
    return issues
