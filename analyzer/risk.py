"""Replace RiskModel with a trained model later without changing mining."""
import math
from typing import Protocol

WEIGHTS = {'churn': .25, 'commits': .20, 'bug_fixes': .25, 'weighted_degree': .15, 'complexity': .15}


class RiskModel(Protocol):
    def score(self, files: list[dict]) -> list[dict]: ...


class HeuristicRiskModel:
    name = 'Transparent heuristic v1 (not a defect probability)'

    def score(self, files):
        maxima = {key: max((f.get(key) or 0 for f in files), default=0) for key in WEIGHTS}
        result = []
        for original in files:
            row = dict(original)
            available = {key: weight for key, weight in WEIGHTS.items() if row.get(key) is not None}
            normalized = {key: math.log1p(row.get(key, 0)) / math.log1p(maxima[key]) if maxima[key] else 0 for key in available}
            score = 100 * sum(available[k] * normalized[k] for k in available) / sum(available.values())
            row['risk_score'] = round(score, 1)
            row['risk_level'] = 'High' if row['risk_score'] >= 70 else 'Medium' if row['risk_score'] >= 40 else 'Low'
            reasons = []
            labels = {'churn': f"{row['churn']} lines of churn", 'commits': f"{row['commits']} commits touching this file",
                      'bug_fixes': f"{row['bug_fixes']} potential bug-fix commits", 'weighted_degree': f"{row.get('weighted_degree', 0)} weighted co-change links",
                      'complexity': f"maximum cyclomatic complexity {row.get('complexity')}"}
            for key, value in normalized.items():
                if value >= .6 and (row.get(key) or 0) > (1 if key in ('commits', 'complexity') else 0):
                    reasons.append(labels[key] + ' (elevated relative to this repository).')
            row['explanation'] = reasons or ['No elevated signals in the available metrics; limited history can hide risk.']
            row['normalized'] = normalized
            result.append(row)
        return sorted(result, key=lambda f: (-f['risk_score'], f['path']))
