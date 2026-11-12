
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from fastapi import HTTPException
from pydantic import Field
from analyzer.improvements import analyze_source, complexity
from analyzer.repository import Repository

app = FastAPI(
    title="CodePrism API",
    description="Self-Adaptive Semantic Software Defect Prediction",
    version="1.0.0"
)


class CodeRequest(BaseModel):
    code: str = Field(max_length=300_000)
    language: str = "python"


class PredictionResponse(BaseModel):
    defect_probability: float | None = None
    risk_score: float
    model: str = 'AST heuristic; not a trained model or calibrated defect probability'
    risk_level: str
    explanation: list[str]
    issues: list[dict]
    timestamp: str


@app.get("/")
async def root():
    return {
        "message": "CodePrism API is running!",
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/predict", response_model=PredictionResponse)
def predict_defect(request: CodeRequest):
    """
    Analyze supplied Python without executing it. Scores summarize static signals.
    """
    if request.language.lower() not in ('python', 'py'):
        raise HTTPException(422, 'The prediction endpoint supports Python AST analysis only.')
    findings = analyze_source('submitted.py', request.code)
    cc = complexity(request.code)
    severity_weights = {'High': 20, 'Medium': 10, 'Low': 3, 'Info': 1}
    score = min(100, sum(severity_weights[i['severity']] for i in findings) + min(30, max(0, (cc or 1) - 1) * 2))
    return PredictionResponse(
        risk_score=score,
        risk_level='HIGH' if score >= 70 else 'MEDIUM' if score >= 40 else 'LOW',
        explanation=[f"{i['issue_type']} at line {i['line']}: {i['explanation']}" for i in findings]
                    or ['No issues detected by the implemented AST checks; this is not a guarantee of correctness.'],
        issues=findings,
        timestamp=datetime.now().isoformat()
    )


class RepositoryRequest(BaseModel):
    url: str
    commit_limit: int = Field(default=200, ge=1, le=200)


@app.post('/analyze')
def analyze_repository(request: RepositoryRequest):
    repo = None
    try:
        from analyzer.repository import validate_url
        validate_url(request.url)
        repo = Repository(request.url, request.commit_limit)
        result = repo.analyze()
        result.pop('graph')
        result['model'] = 'Repository-relative heuristic; not a defect probability'
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        if repo:
            repo.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
