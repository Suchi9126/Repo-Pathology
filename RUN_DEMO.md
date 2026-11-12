# Repo Pathology

A working repository intelligence MVP. The original README is retained so its claims can be checked against implementation. This application uses transparent heuristics, not a trained GNN, LLM, adaptive learner, or calibrated defect probability.

## Start on Windows

From the CodePrism directory, with the existing virtual environment activated:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run dashboard.py
```

Open http://localhost:8501. No API keys are needed. Keep the default local path and click **Analyze Repository**, or supply a public `https://github.com/owner/repository` URL. The URL takes precedence over the local path.

Optional API, in a second terminal:

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs. `POST /predict` accepts `code` and `language: python`; `risk_score` reflects actual static findings, while the legacy `defect_probability` is null because no calibrated probability exists. `POST /analyze` accepts `url` and `commit_limit` and mines a public GitHub repository.

## Suggested demonstration

1. Analyze the default local CodePrism repository. Explain that all counts come from files and Git, and the risk score is a repository-relative heuristic.
2. Show Overview, inspect risky files and actual static findings.
3. Open Temporal Risk Graph; drag and zoom, inspect a file and try the hypothetical complexity/coupling simulation.
4. Open Commit Timeline, inspect a commit's actual changed source files and churn. Build the historical trend if multiple weeks are available.
5. Select a historical snapshot from before this update. In README Alignment and Code Diagnosis, show the constant prediction finding and missing structural evidence for GNNs, LLMs and adaptive training. The original committed API contains Markdown instructions inside the `.py` file: the analyzer reports its syntax error and separately inspects its embedded Python block, with original line numbers. Return to Latest workspace to see the replacement API.
6. In the API docs, submit clean Python and then invalid syntax to `/predict`; compare findings and scores.

## Validation

```powershell
python -m unittest discover -s tests -v
```

## Methods and limits

- At most 200 commits from the selected branch; source file history is path-based and does not follow renames. Message keywords indicate potential fixes rather than confirmed bugs. File statistics cover only this mined window.
- Nodes represent supported source files present at the snapshot. Edges count commits changing a pair together. Commits touching more than 40 source files contribute metrics but no edges. Visualization shows up to 60 highest-risk files.
- Weekly snapshots use the latest mined commit in each UTC calendar week. Historical analysis reads committed blobs; Latest workspace includes local tracked and untracked non-ignored files but retains committed history metrics. Uncommitted files may have no history. Commit timestamps can be unreliable in rewritten histories.
- File limits: 1,500 eligible text files, 300 KB each. Generated folders, symlinks, binary content and common generated JS/type files are excluded. Remote cloning uses shallow history, no checkout, no interactive credentials or redirects. Git itself and network access are required. Clone size is not bounded by history depth. GitPython's 120-second clone timeout is enabled on supported platforms; Windows does not support that timeout, so a stalled Windows clone may require restarting the app.
- Complexity is the maximum Radon block complexity per Python file. Other languages have Git metrics and maintenance marker checks only. Missing complexity is omitted and remaining weights are rescaled.
- File scores use log1p(metric) / log1p(snapshot maximum), with weights 25% churn, 20% changes, 25% potential bug fixes, 15% weighted graph degree, 15% complexity. They are relative rankings: a tiny repository can still have high scores. Health is 100 minus mean file risk, not a measured reliability rate. Scores should not be compared directly across repositories or snapshots.
- README checks recognize a bounded set of technology claims and selected benchmark/support claims. Imports, definitions and dependencies are preliminary evidence, not semantic proof or feature validation. Heuristic unused-import findings can include false positives.
- Static analysis never imports or executes target repository code. PyVis libraries are embedded inline for offline graph display. Session state prevents recloning when switching views; restart or Analyze Repository refreshes data.
- Historical trend is descriptive. Simulation scales selected normalized metric contributions with the snapshot baseline held fixed; it does not predict a causal improvement. API snippet scores use separate static-finding weights and are not equivalent to repository file scores.
- No authentication, database, deployment infrastructure or model training is included. Temporary clones are cleaned on replacement; session teardown cleanup is best effort.
