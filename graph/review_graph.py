"""
LangGraph orchestration graph for the AI Code Analyzer.

Workflow:
  orchestrator → context_builder → memory_node
      ↓
  [parallel] bug_detector | rules_checker | git_history | past_pr | comment_verifier
      ↓
  aggregator → confidence_scorer → output_node

Each node receives and returns the shared GraphState TypedDict.
"""

import asyncio
import logging
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings
from agents.bug_detector import BugDetectorAgent
from agents.rules_checker import RulesCheckerAgent
from agents.git_history_agent import GitHistoryAgent
from agents.past_pr_agent import PastPRAgent
from agents.comment_verifier import CommentVerifierAgent
from services.context_builder import ContextBuilder
from services.memory_service import MemoryService
from services.provider_factory import get_provider
from services.review_poster import ReviewPoster
from utils.deepseek_local_client import get_llm_client

logger = logging.getLogger(__name__)
settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Shared State
# ──────────────────────────────────────────────────────────────────────────────

class GraphState(TypedDict, total=False):
    # Input
    provider: str
    owner: str
    repo: str
    pr_number: int
    head_sha: str

    # Built context
    pr_context: Dict[str, Any]
    file_contexts: List[Dict[str, Any]]

    # Memory
    memory_context_raw: Dict[str, Any]
    memory_context_text: str
    active_rules_text: str
    repeated_issues: List[Dict[str, Any]]

    # Agent results
    bug_results: Dict[str, Any]
    rules_results: Dict[str, Any]
    history_results: Dict[str, Any]
    past_pr_results: Dict[str, Any]
    comment_results: Dict[str, Any]

    # Aggregated
    all_findings: List[Dict[str, Any]]
    high_findings: List[Dict[str, Any]]
    medium_findings: List[Dict[str, Any]]
    low_findings: List[Dict[str, Any]]

    # Scored
    scored_findings: List[Dict[str, Any]]
    avg_confidence: float

    # Output
    github_comment_id: Optional[int]
    report_summary: str
    error: Optional[str]


# ──────────────────────────────────────────────────────────────────────────────
# Node functions
# ──────────────────────────────────────────────────────────────────────────────

async def orchestrator_node(state: GraphState) -> GraphState:
    """Entry point. Validates required inputs and logs the start."""
    logger.info(
        "🚀 Starting analysis for PR #%d in %s/%s",
        state["pr_number"], state["owner"], state["repo"],
    )
    return {**state, "error": None}


async def context_builder_node(state: GraphState) -> GraphState:
    """Fetch PR files, enriched with diff, AST, and commit history."""
    try:
        gh = get_provider(state.get("provider", "github"))
        if not gh:
            return {**state, "error": f"Provider '{state.get('provider')}' not supported"}
        builder = ContextBuilder(gh)
        pr_ctx = await builder.build(state["owner"], state["repo"], state["pr_number"])
        await gh.close()

        logger.info(
            "Context built: %d files for PR #%d", len(pr_ctx.files), state["pr_number"]
        )
        return {
            **state,
            "pr_context": pr_ctx.to_dict(),
            "file_contexts": pr_ctx.files,
            "head_sha": pr_ctx.head_sha,
        }
    except Exception as exc:
        logger.exception("Context builder failed: %s", exc)
        return {**state, "error": str(exc), "file_contexts": []}


async def memory_node(state: GraphState) -> GraphState:
    """Retrieve PostgreSQL historical context and format it for agents."""
    try:
        memory_svc = MemoryService()
        file_paths = [f["file_path"] for f in state.get("file_contexts", [])]
        repo = f"{state['owner']}/{state['repo']}"

        raw = await memory_svc.get_memory_context(repo, state["pr_number"], file_paths)
        memory_text = memory_svc.build_memory_prompt(raw)
        # rules_text = MemoryService.format_rules(raw.get("rules", []))
        rules_text = ""  # Disable database rules to let model use its own reasoning
        repeated = raw.get("repeated_issues", [])

        logger.info("Memory context loaded: %d file paths", len(file_paths))
        return {
            **state,
            "memory_context_raw": raw,
            "memory_context_text": memory_text,
            "active_rules_text": rules_text,
            "repeated_issues": repeated,
        }
    except Exception as exc:
        logger.exception("Memory node failed: %s", exc)
        return {
            **state,
            "memory_context_raw": {},
            "memory_context_text": "",
            "active_rules_text": "",
            "repeated_issues": [],
        }


# async def _run_agents_parallel(state: GraphState) -> GraphState:
    """
    Launch all five agents concurrently using asyncio.gather().
    Each agent result is stored separately in state.
    """
    logger.info("Launching %d agents in parallel for %d files...", 5, len(state.get("file_contexts", [])))
    llm = get_llm_client()
    
    # Filter out lockfiles, manifests and other noisy/massive files to save LLM tokens/time
    SKIPPABLE_NAMES = {
        "package-lock.json", "package.json", 
        "yarn.lock", "pnpm-lock.yaml", "pnpm-workspace.yaml",
        "poetry.lock", "pyproject.toml", "pipfile.lock",
        "go.sum", "go.mod", "composer.lock"
    }
    original_files = state.get("file_contexts", [])
    file_contexts = [f for f in original_files if f["file_path"].split("/")[-1].lower() not in SKIPPABLE_NAMES]
    
    if len(file_contexts) < len(original_files):
        logger.info("Filtered out %d lock/manifest files.", len(original_files) - len(file_contexts))
    
    memory_text = state.get("memory_context_text", "")
    rules_text = state.get("active_rules_text", "")
    repeated = state.get("repeated_issues", [])

    bug_agent = BugDetectorAgent(llm)
    rules_agent = RulesCheckerAgent(llm)
    history_agent = GitHistoryAgent(llm)
    past_pr_agent_inst = PastPRAgent(llm)
    comment_agent = CommentVerifierAgent(llm)

    async def safe_run(coro, name: str) -> Dict[str, Any]:
        logger.info("Agent starting: %s", name)
        try:
            res = await asyncio.wait_for(coro, timeout=settings.PARALLEL_AGENT_TIMEOUT)
            logger.info("Agent complete: %s", name)
            return res
        except asyncio.TimeoutError:
            logger.error("Agent '%s' timed out after %ds", name, settings.PARALLEL_AGENT_TIMEOUT)
            return {"agent_name": name, "findings": [], "confidence": 0.0, "summary": "Timed out."}
        except Exception as exc:
            logger.exception("Agent '%s' raised: %s", name, exc)
            return {"agent_name": name, "findings": [], "confidence": 0.0, "summary": str(exc)}

    ROLES = [getattr(settings, "ANALYSIS_ROLE", "developer")]
    bug_tasks = [
        safe_run(bug_agent.analyze(file_contexts, memory_text, role=role), f"bug_detector_{role}")
        for role in ROLES
    ]
    rules_task = safe_run(rules_agent.analyze(file_contexts, memory_text, rules_text), "rules_checker")
    history_task = safe_run(history_agent.analyze(file_contexts, memory_text), "git_history_agent")
    past_task = safe_run(past_pr_agent_inst.analyze(file_contexts, memory_text, repeated), "past_pr_agent")
    comment_task = safe_run(comment_agent.analyze(file_contexts, memory_text), "comment_verifier")

    agent_results = await asyncio.gather(
        *bug_tasks, rules_task, history_task, past_task, comment_task
    )
    
    bug_res = {"findings": []}
    for i in range(len(ROLES)):
        bug_res["findings"].extend(agent_results[i].get("findings", []))
        
    rules_res = agent_results[len(ROLES)]
    hist_res = agent_results[len(ROLES) + 1]
    past_res = agent_results[len(ROLES) + 2]
    comment_res = agent_results[len(ROLES) + 3]

    logger.info(
        "Agents done — bugs:%d rules:%d history:%d past:%d docs:%d",
        len(bug_res["findings"]),
        len(rules_res["findings"]),
        len(hist_res["findings"]),
        len(past_res["findings"]),
        len(comment_res["findings"]),
    )

    return {
        **state,
        "bug_results": bug_res,
        "rules_results": rules_res,
        "history_results": hist_res,
        "past_pr_results": past_res,
        "comment_results": comment_res,
    }

# For testing purpose
async def _run_agents_parallel(state: GraphState) -> GraphState:
    """
    Launch selected agents concurrently using asyncio.gather().
    Agents are controlled via ACTIVE_AGENTS list.
    """

    ACTIVE_AGENTS = ["bug_detector", "rules_checker", "git_history_agent", "past_pr_agent", "comment_verifier"]   # change this for testing

    logger.info(
        "Launching %d selected agents for %d files...",
        len(ACTIVE_AGENTS),
        len(state.get("file_contexts", [])),
    )

    llm = get_llm_client()

    # Filter noisy files
    SKIPPABLE_NAMES = {
        "package-lock.json", "package.json",
        "yarn.lock", "pnpm-lock.yaml", "pnpm-workspace.yaml",
        "poetry.lock", "pyproject.toml", "pipfile.lock",
        "go.sum", "go.mod", "composer.lock"
    }

    original_files = state.get("file_contexts", [])
    file_contexts = [
        f for f in original_files
        if f["file_path"].split("/")[-1].lower() not in SKIPPABLE_NAMES
    ]

    if len(file_contexts) < len(original_files):
        logger.info(
            "Filtered out %d lock/manifest files.",
            len(original_files) - len(file_contexts),
        )

    memory_text = state.get("memory_context_text", "")
    rules_text = state.get("active_rules_text", "")
    repeated = state.get("repeated_issues", [])

    bug_agent = BugDetectorAgent(llm)
    rules_agent = RulesCheckerAgent(llm)
    history_agent = GitHistoryAgent(llm)
    past_pr_agent_inst = PastPRAgent(llm)
    comment_agent = CommentVerifierAgent(llm)

    async def safe_run(coro, name: str) -> Dict[str, Any]:
        logger.info("Agent starting: %s", name)
        try:
            res = await asyncio.wait_for(
                coro, timeout=settings.PARALLEL_AGENT_TIMEOUT
            )
            logger.info("Agent complete: %s", name)
            return res
        except asyncio.TimeoutError:
            logger.error(
                "Agent '%s' timed out after %ds",
                name,
                settings.PARALLEL_AGENT_TIMEOUT,
            )
            return {
                "agent_name": name,
                "findings": [],
                "confidence": 0.0,
                "summary": "Timed out.",
            }
        except Exception as exc:
            logger.exception("Agent '%s' raised: %s", name, exc)
            return {
                "agent_name": name,
                "findings": [],
                "confidence": 0.0,
                "summary": str(exc),
            }

    tasks = []
    agent_names = []
    ROLES = [getattr(settings, "ANALYSIS_ROLE", "developer")]

    if "bug_detector" in ACTIVE_AGENTS:
        logger.info("🔧 Adding bug_detector tasks for roles")
        for role in ROLES:
            tasks.append(
                safe_run(
                    bug_agent.analyze(file_contexts, memory_text, role=role),
                    f"bug_detector_{role}",
                )
            )
            agent_names.append(f"bug_detector_{role}")

    if "rules_checker" in ACTIVE_AGENTS:
        logger.info("🔧 Adding rules_checker tasks for roles")
        for role in ROLES:
            tasks.append(
                safe_run(
                    rules_agent.analyze(file_contexts, memory_text, rules_text, role=role),
                    f"rules_checker_{role}",
                )
            )
            agent_names.append(f"rules_checker_{role}")

    if "git_history_agent" in ACTIVE_AGENTS:
        logger.info("🔧 Adding git_history_agent tasks for roles")
        for role in ROLES:
            tasks.append(
                safe_run(
                    history_agent.analyze(file_contexts, memory_text, role=role),
                    f"git_history_agent_{role}",
                )
            )
            agent_names.append(f"git_history_agent_{role}")

    if "past_pr_agent" in ACTIVE_AGENTS:
        logger.info("🔧 Adding past_pr_agent tasks for roles")
        for role in ROLES:
            tasks.append(
                safe_run(
                    past_pr_agent_inst.analyze(
                        file_contexts,
                        memory_text,
                        repeated,
                        role=role,
                    ),
                    f"past_pr_agent_{role}",
                )
            )
            agent_names.append(f"past_pr_agent_{role}")

    if "comment_verifier" in ACTIVE_AGENTS:
        logger.info("🔧 Adding comment_verifier tasks for roles")
        for role in ROLES:
            tasks.append(
                safe_run(
                    comment_agent.analyze(file_contexts, memory_text, role=role),
                    f"comment_verifier_{role}",
                )
            )
            agent_names.append(f"comment_verifier_{role}")

    if not tasks:
        logger.warning("No agents selected to run.")
        return state

    results = await asyncio.gather(*tasks)

    result_map = dict(zip(agent_names, results))

    # Dump contexts for debugging/visibility
    import os
    dump_dir = "agent_contexts"
    os.makedirs(dump_dir, exist_ok=True)
    
    for agent_task_name, res in result_map.items():
        debug_ctx = res.get("debug_context", [])
        if debug_ctx:
            filepath = os.path.join(dump_dir, f"{agent_task_name}_context.txt")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"=== {agent_task_name.upper()} CONTEXT ===\n\n")
                for i, ctx in enumerate(debug_ctx):
                    f.write(f"--- File {i+1}: {ctx.get('file_path', 'unknown')} ---\n")
                    f.write(ctx.get("prompt", "No prompt found"))
                    f.write("\n\n" + "="*80 + "\n\n")

    bug_res = {"findings": []}
    rules_res = {"findings": []}
    hist_res = {"findings": []}
    past_res = {"findings": []}
    comment_res = {"findings": []}
    
    for role in ROLES:
        bug_res["findings"].extend(result_map.get(f"bug_detector_{role}", {"findings": []}).get("findings", []))
        rules_res["findings"].extend(result_map.get(f"rules_checker_{role}", {"findings": []}).get("findings", []))
        hist_res["findings"].extend(result_map.get(f"git_history_agent_{role}", {"findings": []}).get("findings", []))
        past_res["findings"].extend(result_map.get(f"past_pr_agent_{role}", {"findings": []}).get("findings", []))
        comment_res["findings"].extend(result_map.get(f"comment_verifier_{role}", {"findings": []}).get("findings", []))

    bug_count = len(bug_res.get("findings", []))
    rules_count = len(rules_res.get("findings", []))
    hist_count = len(hist_res.get("findings", []))
    past_count = len(past_res.get("findings", []))
    comment_count = len(comment_res.get("findings", []))

    logger.info(
        "Agents done — bugs:%d rules:%d history:%d past:%d docs:%d",
        bug_count, rules_count, hist_count, past_count, comment_count,
    )

    logger.debug("Bug results: %s", bug_res)
    logger.debug("Rules results: %s", rules_res)
    logger.debug("History results: %s", hist_res)
    logger.debug("Past PR results: %s", past_res)
    logger.debug("Comment results: %s", comment_res)

    return {
        **state,
        "bug_results": bug_res,
        "rules_results": rules_res,
        "history_results": hist_res,
        "past_pr_results": past_res,
        "comment_results": comment_res,
    }

# Expose as a named node function
async def parallel_agents_node(state: GraphState) -> GraphState:
    return await _run_agents_parallel(state)


async def aggregator_node(state: GraphState) -> GraphState:
    """Merge all agent findings into a single deduplicated list."""
    all_findings: List[Dict[str, Any]] = []

    for key in ("bug_results", "rules_results", "history_results", "past_pr_results", "comment_results"):
        result = state.get(key, {})
        findings = result.get("findings", [])
        agent_name = result.get("agent_name", key)
        logger.info(
            "📊 Aggregator collecting findings from %s: %d findings",
            agent_name, len(findings)
        )
        all_findings.extend(findings)

    # Deduplicate by (file_path, description[:60]) to avoid near-duplicates
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for f in all_findings:
        key = (f.get("file_path"), f.get("description", "")[:60])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    high = [f for f in deduped if f.get("severity") == "high"]
    medium = [f for f in deduped if f.get("severity") == "medium"]
    low = [f for f in deduped if f.get("severity") == "low"]

    logger.info(
        "Aggregated %d findings (H=%d M=%d L=%d)", len(deduped), len(high), len(medium), len(low)
    )

    return {
        **state,
        "all_findings": deduped,
        "high_findings": high,
        "medium_findings": medium,
        "low_findings": low,
    }


async def confidence_scorer_node(state: GraphState) -> GraphState:
    """
    Score each finding. Apply threshold filter.
    Confidence boosted when:
      - Multiple agents flag the same file
      - Finding matches a repeated historical issue
      - Severity is high
    """
    threshold = settings.CONFIDENCE_THRESHOLD
    weights = settings.SEVERITY_WEIGHTS

    all_findings = state.get("all_findings", [])
    repeated_descriptions = {
        r.get("description", "")[:60] for r in state.get("repeated_issues", [])
    }

    # Count how many agents flagged each file
    file_agent_counts: Dict[str, set] = {}
    for f in all_findings:
        fp = f.get("file_path", "")
        file_agent_counts.setdefault(fp, set()).add(f.get("agent_name"))

    scored: List[Dict[str, Any]] = []
    for f in all_findings:
        base_conf = float(f.get("confidence", 0.5))
        severity_bonus = weights.get(f.get("severity", "low"), 0.4) * 0.1
        multi_agent_bonus = (
            0.1 if len(file_agent_counts.get(f.get("file_path", ""), set())) > 1 else 0.0
        )
        repeat_bonus = (
            0.1 if f.get("description", "")[:60] in repeated_descriptions else 0.0
        )

        final_conf = min(base_conf + severity_bonus + multi_agent_bonus + repeat_bonus, 1.0)
        f_scored = {**f, "confidence": final_conf}

        if final_conf >= threshold:
            scored.append(f_scored)
        else:
            logger.debug("Filtered finding (conf=%.2f): %s", final_conf, f.get("description", "")[:60])

    if not all_findings:
        logger.info("Confidence scoring: No findings detected to score.")
        return {**state, "scored_findings": [], "avg_confidence": 0.0}

    avg_conf = (
        sum(f["confidence"] for f in scored) / len(scored) if scored else 0.0
    )

    pass_rate = (len(scored) / len(all_findings)) * 100 if all_findings else 0
    logger.info(
        "Confidence scoring: %d/%d findings passed threshold %.0f%% (Pass Rate: %.1f%%). Avg Confidence: %.1f%%",
        len(scored), len(all_findings), threshold * 100, pass_rate, avg_conf * 100
    )

    return {**state, "scored_findings": scored, "avg_confidence": avg_conf}


async def output_node(state: GraphState) -> GraphState:
    """Post the review comment to GitHub and persist everything to PostgreSQL."""
    if state.get("error"):
        logger.error("Skipping output due to earlier error: %s", state["error"])
        return state

    findings = state.get("scored_findings", [])
    owner = state["owner"]
    repo = state["repo"]
    pr_number = state["pr_number"]
    head_sha = state.get("head_sha", "HEAD")

    try:
        gh = get_provider(state.get("provider", "github"))
        if not gh:
            return {**state, "error": f"Provider '{state.get('provider')}' not supported"}
        poster = ReviewPoster(gh)
        comment_id = await poster.post_review(
            owner, repo, pr_number, head_sha, findings, state.get("avg_confidence", 0.0)
        )
        await gh.close()

        summary = (
            f"Analysis complete: {len(findings)} findings posted as comment #{comment_id}"
        )
        logger.info(summary)
        return {
            **state,
            "github_comment_id": comment_id,
            "report_summary": summary,
        }
    except Exception as exc:
        logger.exception("Output node failed: %s", exc)
        return {**state, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# Graph construction
# ──────────────────────────────────────────────────────────────────────────────

def build_review_graph(checkpointer: Any) -> StateGraph:
    """
    Construct the LangGraph workflow with the provided checkpointer.
    """
    graph = StateGraph(GraphState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("context_builder", context_builder_node)
    graph.add_node("memory", memory_node)
    graph.add_node("parallel_agents", parallel_agents_node)
    graph.add_node("aggregator", aggregator_node)
    graph.add_node("confidence_scorer", confidence_scorer_node)
    graph.add_node("output", output_node)

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "context_builder")
    graph.add_edge("context_builder", "memory")
    graph.add_edge("memory", "parallel_agents")
    graph.add_edge("parallel_agents", "aggregator")
    graph.add_edge("aggregator", "confidence_scorer")
    graph.add_edge("confidence_scorer", "output")
    graph.add_edge("output", END)

    return graph.compile(checkpointer=checkpointer)


# Singletons for memory & persistent state
_compiled_graph = None
_checkpointer = None
_postgres_pool = None


async def get_checkpointer():
    """
    Returns a persistent Postgres checkpointer if USE_DATABASE is true,
    otherwise returns a volatile InMemorySaver.
    """
    global _checkpointer, _postgres_pool
    if _checkpointer is not None:
        return _checkpointer

    if settings.USE_DATABASE:
        try:
            # Create a dedicated pool for the checkpointer
            _postgres_pool = AsyncConnectionPool(
                conninfo=settings.DATABASE_URL,
                max_size=settings.DB_POOL_SIZE,
                kwargs={"autocommit": True},
                open=False
            )
            await _postgres_pool.open()
            
            _checkpointer = AsyncPostgresSaver(_postgres_pool)
            # Ensure tables (checkpoints) exist
            await _checkpointer.setup()
            logger.info("LangGraph checkpointer: Using PostgreSQL (persistent).")
            return _checkpointer
        except Exception as exc:
            logger.error("Failed to init Postgres checkpointer: %s. Falling back to memory.", exc)

    _checkpointer = InMemorySaver()
    logger.info("LangGraph checkpointer: Using InMemory (volatile).")
    return _checkpointer


async def get_review_graph():
    global _compiled_graph
    if _compiled_graph is None:
        cp = await get_checkpointer()
        _compiled_graph = build_review_graph(cp)
        logger.info("LangGraph review workflow compiled.")
    return _compiled_graph


async def run_review_workflow(owner: str, repo: str, pr_number: int, provider: str = "github") -> GraphState:
    """
    Public entry point.
    Runs the full review workflow and returns the final state.
    """
    graph = await get_review_graph()
    initial_state: GraphState = {
        "provider": provider,
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "head_sha": "",
        "pr_context": {},
        "file_contexts": [],
        "memory_context_raw": {},
        "memory_context_text": "",
        "active_rules_text": "",
        "repeated_issues": [],
        "bug_results": {},
        "rules_results": {},
        "history_results": {},
        "past_pr_results": {},
        "comment_results": {},
        "all_findings": [],
        "high_findings": [],
        "medium_findings": [],
        "low_findings": [],
        "scored_findings": [],
        "avg_confidence": 0.0,
        "github_comment_id": None,
        "report_summary": "",
        "error": None,
    }

    config = {"configurable": {"thread_id": f"{owner}/{repo}/pr/{pr_number}"}}
    # PostgresSaver handles its own transactions
    final_state = await graph.ainvoke(initial_state, config=config)
    return final_state


async def close_checkpointer_pool():
    global _postgres_pool, _checkpointer, _compiled_graph
    if _postgres_pool is not None:
        await _postgres_pool.close()
        logger.info("LangGraph checkpointer pool closed.")
        _postgres_pool = None
    _checkpointer = None
    _compiled_graph = None
