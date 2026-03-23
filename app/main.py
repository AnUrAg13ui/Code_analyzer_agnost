"""
FastAPI application — entry point.
Exposes the GitHub webhook endpoint and health/status routes.
"""

import hashlib
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from database.db import (
    init_db, close_pool, get_all_reports, get_report_detail,
    get_findings_for_pr, get_top_risk_modules, get_overall_stats,
    get_coding_rules
)
from graph.review_graph import run_review_workflow, close_checkpointer_pool
from services.provider_factory import get_provider
from utils.deepseek_local_client import get_llm_client

from config.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Application lifecycle
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup, clean up on shutdown."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_db()
    logger.info("Database schema ready.")

    llm = get_llm_client()
    llm_ok = await llm.health_check()
    if llm_ok:
        logger.info(
            "LLM endpoint reachable ✓  provider=%s  model=%s",
            llm.provider, llm.model_name,
        )
    else:
        logger.warning(
            "⚠️  Could not reach LLM endpoint at startup (provider=%s). "
            "Ensure the model runner is started first.",
            llm.provider,
        )

    yield  # Application is running

    if settings.USE_DATABASE:
        await close_pool()
        await close_checkpointer_pool()
    await get_llm_client().close()
    logger.info("Shutdown complete.")


# ──────────────────────────────────────────────────────────────────────────────
# App instance
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-ready AI Code Analyzer using FastAPI, LangGraph, "
        "PostgreSQL, and a locally hosted DeepSeek Coder model."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Global Error Handling
# ──────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for any unhandled exceptions in the API."""
    logger.exception("Unhandled error for %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal server error occurred.",
            "detail": str(exc) if settings.DEBUG else "Check server logs for details."
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Standardize HTTP exception responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail}
    )


# ──────────────────────────────────────────────────────────────────────────────
# Background task
# ──────────────────────────────────────────────────────────────────────────────

async def run_analysis_background(owner: str, repo: str, pr_number: int, provider: str = "github") -> None:
    """Runs the full LangGraph workflow in the background."""
    start = time.perf_counter()
    try:
        state = await run_review_workflow(owner, repo, pr_number, provider)
        elapsed = time.perf_counter() - start
        if state.get("error"):
            logger.error(
                "Analysis for %s/%s PR #%d failed: %s",
                owner, repo, pr_number, state["error"],
            )
        else:
            logger.info(
                "Analysis for %s/%s PR #%d complete in %.1fs — %s",
                owner, repo, pr_number, elapsed, state.get("report_summary"),
            )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.exception(
            "Unhandled error in analysis for %s/%s PR #%d after %.1fs: %s",
            owner, repo, pr_number, elapsed, exc,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Webhook endpoint
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/webhook/{provider}", status_code=202)
async def generic_webhook(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Receives generic webhook events for any registered Git Provider,
    verifies the signature, and kicks off the analysis for PR events.
    """
    raw_body = await request.body()
    
    # ── Retrieve Provider Plugin ──────────────────────────────────
    provider_inst = get_provider(provider)
    if not provider_inst:
        logger.error(">>> Received webhook for unsupported provider: %s", provider)
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    # ── Signature verification ────────────────────────────────────
    try:
        if not await provider_inst.verify_webhook_signature(request, raw_body):
            logger.warning("Invalid webhook signature for %s — rejecting request.", provider)
            raise HTTPException(status_code=401, detail="Invalid signature")
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {exc}")

    # ── Parse payload ─────────────────────────────────────────────
    try:
        payload: Dict[str, Any] = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    pr_event = provider_inst.parse_webhook_payload(request, payload)
    
    if not pr_event:
        logger.info(">>> Webhook ignored for %s: not a targeted PR lifecycle event.", provider)
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "Event not handled"},
        )

    logger.info("Queuing analysis for %s/%s PR #%d via %s", pr_event.owner, pr_event.repo, pr_event.pr_number, provider)

    # Fire analysis in background — return immediately to provider
    background_tasks.add_task(
        run_analysis_background, pr_event.owner, pr_event.repo, pr_event.pr_number, provider
    )

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "message": f"Analysis started for {pr_event.owner}/{pr_event.repo} PR #{pr_event.pr_number}",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Manual trigger endpoint (for testing)
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/analyze")
async def manual_analyze(
    owner: str,
    repo: str,
    pr_number: int,
    background_tasks: BackgroundTasks,
):
    """
    Manually trigger analysis for a PR (useful for testing without a webhook).
    """
    logger.info("Manual analysis triggered for %s/%s PR #%d", owner, repo, pr_number)
    background_tasks.add_task(run_analysis_background, owner, repo, pr_number, "github")
    return {
        "status": "accepted",
        "message": f"Analysis started for {owner}/{repo} PR #{pr_number}",
    }


@app.post("/debug/analyze")
async def debug_analyze(owner: str, repo: str, pr_number: int):
    """Run full workflow synchronously and return context + agent data for UI debugging."""
    logger.info("Debug full analysis triggered for %s/%s PR #%d", owner, repo, pr_number)
    state = await run_review_workflow(owner, repo, pr_number, "github")

    agent_results = {
        "bug": state.get("bug_results", {}),
        "rules": state.get("rules_results", {}),
        "history": state.get("history_results", {}),
        "past_pr": state.get("past_pr_results", {}),
        "comment": state.get("comment_results", {}),
    }

    def extract_file_contexts(agent_data: Dict[str, Any]):
        debug_entries = agent_data.get("debug_context", []) or []
        return [entry.get("file_context") for entry in debug_entries if entry.get("file_context")]

    agent_initial_file_contexts = {
        key: extract_file_contexts(value) for key, value in agent_results.items()
    }

    return {
        "status": "ok",
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "pr_context": state.get("pr_context", {}),
        "file_contexts": state.get("file_contexts", []),
        "memory_context_raw": state.get("memory_context_raw", {}),
        "memory_context_text": state.get("memory_context_text", ""),
        "agent_results": agent_results,
        "agent_initial_file_contexts": agent_initial_file_contexts,
        "all_findings": state.get("all_findings", []),
        "report_summary": state.get("report_summary", ""),
        "avg_confidence": state.get("avg_confidence", 0.0),
        "error": state.get("error"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard API Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/reports")
async def list_reports(limit: int = 50):
    """List recent PR reports."""
    reports = await get_all_reports(limit=limit)
    return {"reports": reports}


@app.get("/reports/detail")
async def report_detail(owner: str, repo: str, pr_number: int):
    """Fetch detail for one PR report."""
    full_repo = f"{owner}/{repo}"
    report = await get_report_detail(full_repo, pr_number)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/findings")
async def list_findings(owner: str, repo: str, pr_number: int):
    """List all individual findings for a PR."""
    full_repo = f"{owner}/{repo}"
    findings = await get_findings_for_pr(full_repo, pr_number)
    return {"findings": findings}


@app.get("/stats")
async def dashboard_stats():
    """Overall system statistics and high-risk modules."""
    stats = await get_overall_stats()
    top_risks = await get_top_risk_modules(limit=5)
    return {
        "summary": stats,
        "top_risks": top_risks
    }


@app.get("/rules")
async def list_rules(enabled_only: bool = True):
    """List agent coding rules. Note: Rules are now disabled - AI uses its own reasoning."""
    # rules = await get_coding_rules(enabled_only=enabled_only)
    # return {"rules": rules}
    return {"rules": [], "message": "Coding rules are disabled. The AI now uses its own reasoning and best practices knowledge."}


# ──────────────────────────────────────────────────────────────────────────────
# Health & Status endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Quick readiness probe."""
    llm = get_llm_client()
    llm_ok = await llm.health_check()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "llm_provider": llm.provider,
        "llm_model": llm.model_name,
        "llm_base_url": llm.base_url,
        "llm_reachable": llm_ok,
    }


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.DEBUG,
    )
