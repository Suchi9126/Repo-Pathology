import tempfile
import unittest
from pathlib import Path

from git import Repo, Actor
from analyzer.repository import Repository, validate_url
from analyzer.improvements import analyze_source
from analyzer.risk import HeuristicRiskModel
from src.api.server import CodeRequest, predict_defect


class AnalysisSmokeTests(unittest.TestCase):
    def test_real_history_and_temporal_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            git_repo = Repo.init(root)
            actor = Actor('Demo', 'demo@example.test')
            (root / 'a.py').write_text('def predict(request):\n    return {"risk_score": 0.87}\n')
            (root / 'b.py').write_text('value = 1\n')
            (root / 'README.md').write_text('# Demo\nUses Graph Neural Networks, LLMs and adaptive learning.\n')
            git_repo.index.add(['a.py', 'b.py', 'README.md'])
            first = git_repo.index.commit('initial implementation', author=actor, committer=actor,
                author_date='2026-01-01 10:00:00 +0000', commit_date='2026-01-01 10:00:00 +0000')
            (root / 'a.py').write_text('def predict(request):\n    return request["score"]\n')
            (root / 'b.py').write_text('broken (\n')
            git_repo.index.add(['a.py', 'b.py'])
            git_repo.index.commit('fix regression in prediction', author=actor, committer=actor,
                author_date='2026-01-09 10:00:00 +0000', commit_date='2026-01-09 10:00:00 +0000')
            repo = Repository(folder)
            try:
                old = repo.analyze(first.hexsha)
                current = repo.analyze()
                self.assertEqual(len(old['commits']), 1)
                self.assertEqual(old['graph']['a.py']['b.py']['weight'], 1)
                self.assertEqual(current['graph']['a.py']['b.py']['weight'], 2)
                self.assertTrue(any(i['issue_type'] == 'Potentially hardcoded prediction' for i in old['issues']))
                self.assertFalse(any(i['issue_type'] == 'Potentially hardcoded prediction' for i in current['issues']))
                self.assertTrue(any(i['issue_type'] == 'Syntax error' for i in current['issues']))
                self.assertFalse(any(i['issue_type'] == 'Syntax error' for i in old['issues']))
                self.assertTrue(all(f['bug_fixes'] == 0 for f in old['files']))
                self.assertTrue(all(0 <= f['risk_score'] <= 100 for f in current['files']))
                self.assertTrue(any(r['claimed_feature'] == 'Graph neural networks' and r['status'] == 'Not found' for r in old['alignment']))
            finally:
                repo.close()
                git_repo.close()

    def test_empty_repository_and_isolated_node(self):
        with tempfile.TemporaryDirectory() as folder:
            git_repo = Repo.init(folder)
            repo = Repository(folder)
            try:
                self.assertEqual(repo.analyze()['files'], [])
                self.assertIsNone(repo.analyze()['health'])
                Path(folder, 'only.py').write_text('x = 1\n')
                result = repo.analyze(workspace=True)
                self.assertEqual(result['graph'].number_of_nodes(), 1)
                self.assertEqual(result['graph'].number_of_edges(), 0)
            finally:
                repo.close()
                git_repo.close()

    def test_static_checks_and_input_dependent_api(self):
        findings = analyze_source('a.py', 'import os\ndef f(a,b,c,d,e,f,g):\n    try:\n        pass\n    except:\n        pass\n    # TODO resolve\n')
        kinds = {i['issue_type'] for i in findings}
        self.assertTrue({'Bare except', 'Excessive parameters', 'Maintenance marker', 'Potentially unused import (heuristic)'} <= kinds)
        clean = predict_defect(CodeRequest(code='def double(x):\n    return x * 2\n'))
        invalid = predict_defect(CodeRequest(code='def broken(:'))
        self.assertGreater(invalid.risk_score, clean.risk_score)
        self.assertIsNone(clean.defect_probability)
        self.assertEqual(HeuristicRiskModel().score([]), [])

    def test_url_validation(self):
        self.assertEqual(validate_url('https://github.com/owner/repo.git'), 'https://github.com/owner/repo.git')
        for invalid in ['http://github.com/a/b', 'https://evil.test/a/b', 'https://github.com/a/b?x=1', 'https://github.com/a/..', 'git@github.com:a/b', 'https://user:pass@github.com/a/b']:
            with self.assertRaises(ValueError):
                validate_url(invalid)

    def test_embedded_python_in_invalid_source(self):
        source = '1. **instructions**\n```python\ndef predict(request):\n    return {"risk_score": 0.87}\n'
        findings = analyze_source('broken.py', source)
        self.assertTrue(any(i['issue_type'] == 'Syntax error' for i in findings))
        hardcoded = next(i for i in findings if i['issue_type'] == 'Potentially hardcoded prediction')
        self.assertEqual(hardcoded['line'], 3)
        self.assertIn('embedded Python block', hardcoded['explanation'])

    def test_current_project(self):
        repo = Repository(str(Path(__file__).resolve().parents[1]))
        try:
            result = repo.analyze(workspace=True)
            self.assertTrue(any(f['path'] == 'src/api/server.py' for f in result['files']))
            self.assertTrue(result['commits'])
            self.assertTrue(result['alignment'])
        finally:
            repo.close()


if __name__ == '__main__':
    unittest.main()
