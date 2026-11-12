"""Bounded Git mining and point-in-time analysis; never import target code."""
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path, PurePosixPath
import os
import re
import tempfile

import git
import networkx as nx

from .improvements import analyze_source, complexity
from .risk import HeuristicRiskModel

EXCLUDED = {'.git', 'venv', '.venv', 'env', 'node_modules', '__pycache__', 'build', 'dist', 'vendor', '.next', '.tox', 'site-packages', 'coverage', '.mypy_cache'}
EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.vue', '.svelte', '.sh', '.sql', '.r', '.html', '.css', '.scss', '.sass', '.less', '.ps1', '.dart', '.ex', '.exs', '.lua', '.m'}
BUG = re.compile(r'\b(fix(?:es|ed|ing)?|bugs?|defects?|patch(?:es|ed)?|errors?|crash(?:es|ed)?|regressions?|hotfix)\b', re.I)
MAX_BYTES = 300_000
MAX_FILES = 1500


def source_file(path):
    p = PurePosixPath(path.replace('\\', '/'))
    return not any(part.lower() in EXCLUDED for part in p.parts) and p.suffix.lower() in EXTENSIONS and not p.name.endswith(('.min.js', '.d.ts'))


def validate_url(url):
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?', url) or any(part in ('.', '..') for part in url.split('/')[3:]):
        raise ValueError('Use a public HTTPS GitHub repository URL: https://github.com/owner/repository')
    return url.rstrip('/')


class Repository:
    def __init__(self, location, limit=200):
        self.temp = None
        self.warnings = []
        if location.startswith('https://'):
            url = validate_url(location)
            self.temp = tempfile.TemporaryDirectory(prefix='repo-pathology-')
            try:
                # One extra parent keeps the oldest analyzed commit's diff genuine.
                self.repo = git.Repo.clone_from(url, self.temp.name, depth=min(max(int(limit), 1), 200) + 1, no_checkout=True,
                    **({'kill_after_timeout': 120} if os.name != 'nt' else {}),
                    env={'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1',
                        'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_COUNT': '2',
                        'GIT_CONFIG_KEY_0': 'credential.helper', 'GIT_CONFIG_VALUE_0': '',
                        'GIT_CONFIG_KEY_1': 'http.followRedirects', 'GIT_CONFIG_VALUE_1': 'false'})
            except Exception:
                self.temp.cleanup()
                raise ValueError('Unable to clone. Check that the public repository exists and network access is available.') from None
            self.local = False
        else:
            if '://' in location:
                raise ValueError('Only public HTTPS github.com URLs or local Git directories are supported.')
            try:
                self.repo = git.Repo(Path(location).expanduser().resolve(), search_parent_directories=False)
            except (git.InvalidGitRepositoryError, git.NoSuchPathError):
                raise ValueError('The local path must be an existing Git repository.') from None
            self.local = not self.repo.bare
        self.limit = min(max(int(limit), 1), 200)
        self.commits = []
        shallow_file = Path(self.repo.git_dir) / 'shallow'
        shallow_boundaries = set(shallow_file.read_text().splitlines()) if shallow_file.exists() else set()
        if self.repo.head.is_valid():
            for commit in self.repo.iter_commits(max_count=self.limit):
                try:
                    if commit.hexsha in shallow_boundaries:
                        self.warnings.append(f'Diff unavailable for shallow boundary {commit.hexsha[:8]}; its change metrics are excluded.')
                        stats = {}
                    else:
                        stats = commit.stats.files
                except (git.GitCommandError, ValueError):
                    self.warnings.append(f'Change statistics unavailable for {commit.hexsha[:8]}.')
                    stats = {}
                changed = {p: {'added': int(s.get('insertions', 0)), 'deleted': int(s.get('deletions', 0))}
                           for p, s in stats.items() if source_file(p)}
                self.commits.append(dict(sha=commit.hexsha, message=commit.message.strip(), author=commit.author.name,
                    author_id=commit.author.email or commit.author.name, timestamp=commit.committed_datetime.astimezone(timezone.utc).isoformat(),
                    files=changed, changed_files={p: {'added': int(s.get('insertions', 0)), 'deleted': int(s.get('deletions', 0))} for p, s in stats.items()},
                    added=sum(s.get('insertions', 0) for s in stats.values()),
                    deleted=sum(s.get('deletions', 0) for s in stats.values()), bug_fix=bool(BUG.search(commit.message))))
        self.commits.sort(key=lambda c: (c['timestamp'], c['sha']))

    def close(self):
        self.repo.close()
        if self.temp:
            self.temp.cleanup()

    def snapshots(self):
        weeks = {}
        for commit in self.commits:
            date = datetime.fromisoformat(commit['timestamp'])
            weeks[date.strftime('%G-W%V')] = commit
        return {f"{week} · {c['timestamp'][:10]} · {c['sha'][:7]}": c['sha'] for week, c in weeks.items()}

    def contents(self, sha=None, workspace=False):
        contents = {}
        skipped = 0
        if workspace and self.local:
            root = Path(self.repo.working_tree_dir)
            # Git's file list avoids traversing generated directories and honors ignores.
            names = self.repo.git.ls_files('-z', '--cached', '--others', '--exclude-standard').split('\0')
            for name in sorted(set(names)):
                if not name or any(p.lower() in EXCLUDED for p in PurePosixPath(name).parts):
                    continue
                path = root / name
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                    continue
                if path.stat().st_size > MAX_BYTES or len(contents) >= MAX_FILES:
                    skipped += 1
                    continue
                if source_file(name) or PurePosixPath(name).suffix.lower() in {'.md', '.txt', '.toml', '.json', '.yml', '.yaml', '.ini', '.cfg'}:
                    raw = path.read_bytes()
                    if b'\0' not in raw:
                        contents[name] = raw.decode('utf-8', errors='replace')
        elif self.repo.head.is_valid():
            for blob in self.repo.commit(sha or 'HEAD').tree.traverse():
                if blob.type != 'blob' or blob.mode == 0o120000 or any(p.lower() in EXCLUDED for p in PurePosixPath(blob.path).parts):
                    continue
                if blob.size > MAX_BYTES or len(contents) >= MAX_FILES:
                    skipped += 1
                    continue
                if source_file(blob.path) or PurePosixPath(blob.path).suffix.lower() in {'.md', '.txt', '.toml', '.json', '.yml', '.yaml', '.ini', '.cfg'}:
                    raw = blob.data_stream.read()
                    if b'\0' not in raw:
                        contents[blob.path] = raw.decode('utf-8', errors='replace')
        return contents, skipped

    def analyze(self, sha=None, workspace=False):
        contents, skipped = self.contents(sha, workspace)
        commits = self.commits
        if sha:
            cutoff = next(i for i, c in enumerate(commits) if c['sha'] == sha)
            commits = commits[:cutoff + 1]
        metrics = {}
        graph = nx.Graph()
        for path, source in contents.items():
            if source_file(path):
                metrics[path] = dict(path=path, commits=0, churn=0, contributors=set(), bug_fixes=0,
                    last_modified=None, size_bytes=len(source.encode('utf-8')), complexity=complexity(source) if path.endswith('.py') else None)
                graph.add_node(path)
        omitted_edges = 0
        for commit in commits:
            paths = [p for p in commit['files'] if p in metrics]
            for p in paths:
                m = metrics[p]
                m['commits'] += 1
                m['churn'] += sum(commit['files'][p].values())
                m['contributors'].add(commit['author_id'])
                m['bug_fixes'] += int(commit['bug_fix'])
                m['last_modified'] = commit['timestamp']
            if len(commit['files']) > 40:
                omitted_edges += 1
                continue
            for a, b in combinations(paths, 2):
                graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get('weight', 0) + 1)
        for path, row in metrics.items():
            row['contributors'] = len(row['contributors'])
            row['degree'] = graph.degree(path)
            row['weighted_degree'] = graph.degree(path, weight='weight')
        files = HeuristicRiskModel().score(list(metrics.values()))
        issues = []
        for path, source in contents.items():
            if source_file(path):
                try:
                    issues.extend(analyze_source(path, source))
                except (RecursionError, ValueError, TypeError) as exc:
                    issues.append(dict(file=path, line=1, severity='Info', issue_type='Analysis limitation',
                        explanation=f'Static checks could not finish: {type(exc).__name__}', recommendation='Inspect this file manually.'))
        from .alignment import analyze_alignment
        warnings = list(self.warnings)
        if skipped:
            warnings.append(f'{skipped} entries skipped by the {MAX_FILES}-file / {MAX_BYTES:,}-byte per-file limits.')
        if omitted_edges:
            warnings.append(f'Co-change edges omitted for {omitted_edges} commits touching more than 40 source files.')
        if not any(p.endswith('.py') for p in metrics):
            warnings.append('No Python source: static checks are limited to maintenance markers; Git metrics still apply.')
        return dict(files=files, commits=commits, graph=graph, issues=issues, alignment=analyze_alignment(contents, issues),
                    warnings=warnings, workspace=workspace and self.local, snapshot=sha or 'HEAD',
                    contributors=len({c['author_id'] for c in commits}), health=round(100 - sum(f['risk_score'] for f in files) / len(files), 1) if files else None)
