"""FastAPI entry point.  Run: uvicorn main:app --reload"""
from fastapi import FastAPI

from routes import router

app = FastAPI(title="LegalEase API")
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
