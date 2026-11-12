"""Run: python -m streamlit run dashboard.py"""
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from analyzer.repository import Repository
from analyzer.risk import WEIGHTS

st.set_page_config(page_title='Repo Pathology | Repository Intelligence', page_icon='◈', layout='wide')
COLORS = {'High': '#fb7185', 'Medium': '#fbbf24', 'Low': '#2dd4bf'}
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:Inter,sans-serif}
.block-container{padding-top:2rem;padding-bottom:2rem;max-width:1600px}
h1{font-size:2.25rem!important;letter-spacing:-1.2px;font-weight:800!important}
h2,h3{letter-spacing:-.5px}
[data-testid="stSidebar"]{border-right:1px solid #253148}
[data-testid="stMetric"]{background:#131d30;border:1px solid #253148;border-radius:12px;padding:17px 14px}
[data-testid="stMetricLabel"]{color:#9bacc5;font-size:.78rem}
[data-testid="stMetricValue"]{font-size:1.7rem;color:#edf5ff}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:3px;color:#2dd4bf;margin-bottom:5px}
.subhead{color:#9bacc5;font-size:15px;margin-top:-12px;margin-bottom:20px}
.hero{padding:22px;border:1px solid #2c3b55;border-radius:12px;background:#131d30;margin-bottom:18px}
.tag{display:inline-block;padding:4px 10px;border:1px solid #344664;border-radius:30px;color:#aebede;font-size:11px;margin-right:6px}
button[kind="primary"]{border-radius:8px;font-weight:600}
[data-baseweb="tab-list"]{gap:20px;border-bottom:1px solid #253148}
[data-baseweb="tab"]{padding:10px 3px}
</style>''', unsafe_allow_html=True)


def chart(fig, height=320):
    fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(family='Inter, sans-serif', color='#b8c7dd'), margin=dict(l=10, r=15, t=35, b=20), height=height)
    st.plotly_chart(fig, width='stretch')


def get_result(key, sha=None, workspace=False):
    if key not in st.session_state.results:
        with st.spinner('Reading file contents, building graph and running static checks…'):
            st.session_state.results[key] = st.session_state.repo.analyze(sha, workspace)
    return st.session_state.results[key]


def graph_html(result):
    graph = result['graph']
    rows = result['files'][:60]
    keep = {row['path'] for row in rows}
    net = Network(height='540px', width='100%', bgcolor='#090f1d', font_color='#dbeafe', cdn_resources='in_line')
    for row in rows:
        title = (f"{escape(row['path'])}\nRisk: {row['risk_score']}/100 ({row['risk_level']})\n"
                 f"Commits: {row['commits']} | Churn: {row['churn']} | Bug fixes: {row['bug_fixes']}")
        net.add_node(row['path'], label=row['path'].rsplit('/', 1)[-1], title=title,
                     color=COLORS[row['risk_level']], size=10 + row['risk_score'] * .23)
    for a, b, data in graph.edges(data=True):
        if a in keep and b in keep:
            net.add_edge(a, b, value=data['weight'], title=f"{data['weight']} shared commits", color='#425370')
    net.set_options('''{"physics":{"solver":"forceAtlas2Based","forceAtlas2Based":{"gravitationalConstant":-65,"springLength":130},"stabilization":{"iterations":120}},"interaction":{"hover":true,"navigationButtons":true},"edges":{"smooth":false},"nodes":{"font":{"size":12}}}''')
    # PyVis serializes labels through Jinja's JSON escaping filter.
    return net.generate_html()


with st.sidebar:
    st.markdown('<div class="eyebrow">REPOSITORY INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown('### Analysis workspace')
    st.caption('Real Git history. Transparent risk signals.')
    url = st.text_input('Public GitHub repository URL', placeholder='https://github.com/owner/repository')
    local = st.text_input('Local Git repository path', value=str(Path(__file__).parent))
    st.caption('A GitHub URL takes precedence over the local path.')
    limit = st.slider('Commit history limit', 1, 200, 200)
    analyze = st.button('Analyze Repository', type='primary', width='stretch')
    st.divider()
    st.caption('MODEL / HEURISTIC V1')
    st.caption('Churn 25% · changes 20% · bug fixes 25% · coupling 15% · complexity 15%')
    st.caption('Scores are relative to this repository and snapshot. They are not calibrated defect probabilities or trained GNN outputs.')

st.markdown('<div class="eyebrow">CODE HEALTH / TEMPORAL INTELLIGENCE</div>', unsafe_allow_html=True)
st.title('REPO PATHOLOGY')
st.markdown('<div class="subhead">Repository Intelligence & Predictive Code Health</div>', unsafe_allow_html=True)

if analyze:
    progress = st.progress(0, text='Opening repository and mining commit history…')
    candidate = None
    try:
        candidate = Repository(url.strip() or local.strip(), limit)
        progress.progress(40, text=f'Mined {len(candidate.commits)} commits. Analyzing real source files…')
        result = candidate.analyze(workspace=candidate.local)
        previous = st.session_state.get('repo')
        st.session_state.repo = candidate
        st.session_state.results = {'Latest workspace' if candidate.local else 'Latest commit': result}
        st.session_state.repo_label = url.strip() or local.strip()
        st.session_state.pop('snapshot_choice', None)
        st.session_state.pop('trend', None)
        if previous:
            previous.close()
        progress.progress(100, text='Repository analysis complete')
    except Exception as exc:
        if candidate:
            candidate.close()
        st.error(f'Analysis could not complete: {exc}')
    finally:
        progress.empty()

if 'repo' not in st.session_state:
    st.markdown('''<div class="hero"><h2>Your repository has a history.<br>Find where risk accumulates.</h2>
    <p style="color:#9bacc5;max-width:740px">Mine actual commits, map files that change together, diagnose Python code,
    and compare README claims with implementation evidence. Select a repository in the sidebar to begin.</p>
    <span class="tag">GIT MINING</span><span class="tag">TEMPORAL GRAPHS</span><span class="tag">STATIC DIAGNOSIS</span>
    <span class="tag">NO API KEYS</span></div>''', unsafe_allow_html=True)
    st.info('For the fastest demonstration, keep the default local path and click Analyze Repository. Historical snapshots retain the original committed implementation.')
    st.stop()

repo = st.session_state.repo
latest = 'Latest workspace' if repo.local else 'Latest commit'
snapshots = repo.snapshots()
with st.sidebar:
    snapshot = st.selectbox('Snapshot date', [latest] + list(reversed(snapshots)), key='snapshot_choice')
    st.caption('Historical views read committed files and use only mined commits up to that snapshot. Latest workspace includes local edits; Git statistics remain committed history.')
sha = snapshots.get(snapshot)
data = get_result(snapshot, sha, workspace=snapshot == latest and repo.local)
files = pd.DataFrame(data['files'])
commits = pd.DataFrame(data['commits'])
issues = pd.DataFrame(data['issues'])
st.caption(f"{st.session_state.repo_label}  /  {snapshot}")
kpis = st.columns(6)
values = [('Repository Health', f"{data['health']}/100" if data['health'] is not None else 'N/A'),
          ('Commits Analyzed', len(data['commits'])), ('Source Files', len(files)),
          ('High-Risk Files', sum(f['risk_level'] == 'High' for f in data['files'])),
          ('Detected Issues', len(issues)), ('Contributors', data['contributors'])]
for col, (label, value) in zip(kpis, values):
    col.metric(label, value)
st.caption('Health = 100 − mean file risk. Log-normalized metrics are relative to the selected snapshot; missing complexity is reweighted. Bug-fix labels come from commit messages.')
for warning in data['warnings']:
    st.warning(warning)
overview, temporal, timeline, diagnosis, alignment = st.tabs(['Overview', 'Temporal Risk Graph', 'Commit Timeline', 'Code Diagnosis', 'README Alignment'])

with overview:
    st.markdown('### Signals across your codebase')
    if not files.empty:
        left, right = st.columns([1, 1.65])
        with left:
            counts = files['risk_level'].value_counts().rename_axis('Risk').reset_index(name='Files')
            fig = px.pie(counts, names='Risk', values='Files', hole=.76, color='Risk', color_discrete_map=COLORS, title='File risk distribution')
            fig.update_traces(textinfo='value', textposition='outside')
            chart(fig)
        with right:
            top = files.head(10).iloc[::-1]
            chart(px.bar(top, x='risk_score', y='path', orientation='h', color='risk_level', color_discrete_map=COLORS,
                         title='Files with the strongest risk signals', labels={'risk_score': 'Heuristic risk / 100', 'path': 'Source file', 'risk_level': 'Risk'}))
        st.dataframe(files[['path', 'risk_score', 'risk_level', 'commits', 'churn', 'bug_fixes', 'complexity']].head(12), hide_index=True, width='stretch')
    else:
        st.info('No supported source files found in this snapshot. Commit history remains available.')
    if not commits.empty:
        activity = commits.copy()
        activity['Date'] = pd.to_datetime(activity['timestamp'], utc=True).dt.floor('D')
        daily = activity.groupby('Date').agg(Commits=('sha', 'count'), Added=('added', 'sum'), Deleted=('deleted', 'sum')).reset_index()
        chart(px.bar(daily, x='Date', y=['Added', 'Deleted'], title='Repository activity · lines changed per day',
                     labels={'value': 'Lines changed', 'variable': 'Change type'}, color_discrete_sequence=['#2dd4bf', '#a78bfa']), 240)
    st.markdown('### Problems to investigate first')
    if issues.empty:
        st.success('No findings from the available static checks. This does not establish defect-free code.')
    else:
        priority = issues.assign(rank=issues.severity.map({'High': 0, 'Medium': 1, 'Low': 2, 'Info': 3})).sort_values('rank')
        st.dataframe(priority[['severity', 'issue_type', 'file', 'line', 'explanation']].head(6), hide_index=True, width='stretch')

with temporal:
    st.markdown('### Co-change topology')
    st.caption('Select a historical snapshot in the sidebar to rebuild this graph at that time. Showing up to 60 files ranked by risk. Red: high · amber: medium · teal: low.')
    a, b, c = st.columns(3)
    a.metric('Graph nodes', data['graph'].number_of_nodes())
    b.metric('Co-change edges', data['graph'].number_of_edges())
    c.metric('Displayed files', min(60, len(files)))
    if not files.empty:
        if hasattr(st, 'iframe'):
            st.iframe(graph_html(data), height=560, alt='Interactive file co-change network')
        else:
            components.html(graph_html(data), height=560, scrolling=False)
        selected = st.selectbox('Inspect a file', files.path, key='graph_file')
        row = next(row for row in data['files'] if row['path'] == selected)
        st.markdown(f"**{selected}** · {row['risk_level']} risk · **{row['risk_score']}/100**")
        st.write(' '.join(row['explanation']))
        st.caption(f"Degree: {row['degree']} · Weighted degree: {row['weighted_degree']} · Contributors: {row['contributors']} · Last committed change: {row['last_modified'] or 'No mined history'} · Size: {row['size_bytes']:,} bytes")
        with st.expander('Hypothetical improvement simulation'):
            st.caption('Metric-only scenario with normalization frozen at this snapshot. This is not a validated causal prediction or guaranteed improvement.')
            reduction = st.slider('Reduce complexity and coupling (%)', 0, 100, 30)
            available = sum(w for key, w in WEIGHTS.items() if row.get(key) is not None)
            delta = 100 * sum(WEIGHTS[k] * row['normalized'].get(k, 0) * reduction / 100 for k in ('complexity', 'weighted_degree')) / available
            st.metric('Simulated heuristic risk', round(max(0, row['risk_score'] - delta), 1), delta=round(-delta, 1), delta_color='inverse')
    else:
        st.info('The graph has no source nodes in this snapshot.')

with timeline:
    st.markdown('### Every change leaves a trace')
    if commits.empty:
        st.info('This repository has no commits yet.')
    else:
        events = commits.copy()
        events['Date'] = pd.to_datetime(events.timestamp, utc=True)
        events['Churn'] = events.added + events.deleted
        events['Marker size'] = events['Churn'].clip(lower=1)
        events['Type'] = events.bug_fix.map({True: 'Potential bug fix', False: 'Other commit'})
        events['Short SHA'] = events.sha.str[:8]
        chart(px.scatter(events, x='Date', y='Churn', color='Type', size='Marker size', size_max=24,
                         hover_data={'Short SHA': True, 'message': True, 'author': True, 'added': True, 'deleted': True, 'Marker size': False},
                         color_discrete_map={'Potential bug fix': '#fb7185', 'Other commit': '#2dd4bf'},
                         title='Actual commits · churn and potential bug fixes', labels={'Churn': 'Lines added + deleted'}))
        with st.expander('Calculate historical risk trend'):
            st.caption('Computed from committed files at up to 8 weekly snapshots. Relative normalization changes between snapshots; values are descriptive, not validated forecasts.')
            if st.button('Build historical trend'):
                points = [(label, commit_sha) for label, commit_sha in snapshots.items()
                          if any(c['sha'] == commit_sha for c in data['commits'])]
                if len(points) > 8:
                    points = [points[round(i * (len(points) - 1) / 7)] for i in range(8)]
                trend = []
                for label, commit_sha in points:
                    historical = get_result(label, commit_sha)
                    if historical['health'] is not None:
                        trend.append({'Date': repo.repo.commit(commit_sha).committed_datetime, 'Mean file risk': 100 - historical['health']})
                st.session_state.trend = {'snapshot': snapshot, 'points': trend}
            trend_result = st.session_state.get('trend', {})
            if trend_result.get('snapshot') == snapshot and trend_result.get('points'):
                if len(trend_result['points']) > 1:
                    chart(px.line(pd.DataFrame(trend_result['points']), x='Date', y='Mean file risk', markers=True, title='Historical mean heuristic risk'))
                else:
                    st.info('Only one weekly snapshot is available; a trend needs at least two.')
        for commit in reversed(data['commits']):
            label = f"{commit['timestamp'][:10]} · {commit['sha'][:8]} · {'FIX · ' if commit['bug_fix'] else ''}{commit['message'].splitlines()[0][:100] if commit['message'] else '(no message)'}"
            with st.expander(label):
                st.text(commit['message'])
                st.caption(f"Author: {commit['author']} · {commit['timestamp']} · +{commit['added']} / −{commit['deleted']} lines across all changed files")
                if commit['changed_files']:
                    st.dataframe([{'Changed file': p, **s} for p, s in commit['changed_files'].items()], hide_index=True, width='stretch')
                else:
                    st.caption('No file change statistics available for this commit.')

with diagnosis:
    st.markdown('### Code diagnosis')
    st.caption('Python AST + Radon checks. Unused imports and hardcoded predictions are heuristic findings. Non-Python checks cover maintenance markers only.')
    if issues.empty:
        st.info('No findings from the implemented checks.')
    else:
        a, b = st.columns([2, 1])
        search = a.text_input('Search files or findings', placeholder='File path, complexity, bare except…')
        severities = b.multiselect('Severity', ['High', 'Medium', 'Low', 'Info'], default=['High', 'Medium', 'Low', 'Info'])
        filtered = issues[issues.severity.isin(severities)]
        if search:
            filtered = filtered[filtered[['file', 'issue_type', 'explanation']].apply(lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)]
        st.dataframe(filtered, hide_index=True, width='stretch')
        st.download_button('Download findings CSV', filtered.to_csv(index=False), 'repo-pathology-findings.csv', 'text/csv')
        for row in filtered.head(25).to_dict('records'):
            with st.expander(f"{row['severity']} · {row['issue_type']} · {row['file']}:{row['line']}"):
                st.write(row['explanation'])
                st.markdown('**Suggested improvement:** ' + row['recommendation'])

with alignment:
    st.markdown('### Claims meet implementation')
    st.info('Preliminary evidence checks: imports, definitions and dependencies suggest implementation; they do not prove correctness. “Not found” means no matching evidence was detected, not that a feature is definitively absent.')
    if not data['alignment']:
        st.caption('No root README.md or recognized claims were found in this snapshot.')
    else:
        aligned = pd.DataFrame(data['alignment'])
        st.dataframe(aligned.rename(columns={'claimed_feature': 'Claimed feature', 'implementation_evidence': 'Implementation evidence',
                                            'status': 'Status', 'suggested_next_action': 'Suggested next action'}), hide_index=True, width='stretch')
        st.markdown('### Prioritized improvement roadmap')
        gaps = aligned[aligned.status != 'Evidence found']
        for i, row in enumerate(gaps.to_dict('records'), 1):
            st.markdown(f"**{i:02d} / {row['claimed_feature']}**")
            st.write(row['suggested_next_action'])
            st.caption(row['implementation_evidence'])
    st.caption('Demo tip: use an older committed snapshot to inspect the original constant prediction endpoint, then return to Latest workspace to inspect the AST-based replacement.')
