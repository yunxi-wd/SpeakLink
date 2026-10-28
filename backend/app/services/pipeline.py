"""Bounded multi-role coordinator with durable audit and optimistic commit.

Inference runs outside write transactions. Accepted facts have one database
writer; human corrections are replayed after every model and rule stage.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import monotonic
from typing import Callable, TypeVar
from uuid import uuid4
from sqlalchemy.engine import Connection
from ..core.config import settings, ROOT
from ..models.database import transaction, rows, put, get, load_snapshot, save_snapshot
from ..schemas.domain import Snapshot, ExtractionCandidates, Card, now
from ..schemas.agents import AgentRun, AgentEvent, ReviewReport
from .common import stable_id
from .summarizer import summarize
from .extractor import extract
from .convergence import converge, reconcile
from .clustering import cluster
from .corrections import apply
from .reviewer import review, targets, quarantine
from .llm import role_config

T = TypeVar("T")
ACTIVE = {"queued", "running"}
POOL: ThreadPoolExecutor | None = None

class RevisionConflict(RuntimeError):
    """A newer source/correction won the commit race; preserve its data."""

class RunBusy(RuntimeError):
    """Only one queued/running inference operation per recording is allowed."""

@dataclass
class Work:
    """Detached job inputs captured in a short transaction."""
    run: AgentRun
    snap: Snapshot
    cached: dict | None
    corrections: list[dict]

def fingerprint(snap: Snapshot) -> str:
    """Bind new candidates to source, role configuration and all prompt versions."""
    configs = {role: {k: v for k, v in role_config(role).items() if k != "api_key"} for role in ["summary", "extractor", "reviewer"]}
    from .relation_rules import VERSION
    return stable_id(VERSION, [s.model_dump() for s in snap.segments], configs, settings.agents.max_revisions,
                     settings.agents.max_model_calls, settings.confidence_threshold, settings.embedding_provider,
                     settings.embedding_model, [p.read_text(encoding="utf-8") for p in sorted((ROOT / "configs/prompts").glob("*.yaml"))])

def prepare(sid: str) -> Work:
    """Capture inputs and persist queued state; no model calls occur here."""
    with transaction(True) as conn:
        snap = load_snapshot(conn, sid)
        if not snap.segments:
            raise ValueError("请先上传转写文本或转写音频")
        if any(r["status"] in ACTIVE for r in rows(conn, "agent_runs", sid)):
            raise RunBusy("该记录已有任务正在执行，请等待任务完成")
        saved = rows(conn, "runs", sid)
        pinned = snap.session.metadata.get("fingerprint")
        cached = next((r for r in saved if r["fingerprint"] == pinned), None)
        corrections = sorted(rows(conn, "corrections", sid), key=lambda c: c["created_at"])
        # Upgrade untouched old recordings automatically; human-edited IDs remain pinned.
        if cached and cached['fingerprint'] != fingerprint(snap) and not corrections:
            cached = None
        if cached is None and corrections:
            raise ValueError("存在人工校正但缺少原始候选缓存，不能覆盖；请从备份恢复")
        providers = [role_config(r)["provider"] for r in ["summary", "extractor", "reviewer"]]
        run = AgentRun(id=uuid4().hex, session_id=sid, base_revision=snap.revision,
                       fingerprint=cached["fingerprint"] if cached else fingerprint(snap),
                       mode="cached" if cached else "demo" if all(p == "demo" for p in providers) else "model", cached=cached is not None)
        put(conn, "agent_runs", run.model_dump())
    return Work(run, snap, cached, corrections)

def save_run(run: AgentRun) -> None:
    """Persist progress independently from the final business-data transaction."""
    with transaction(True) as conn:
        put(conn, "agent_runs", run.model_dump())

def safe_error(error: Exception) -> str:
    """Return diagnostics without provider response bodies or credentials."""
    import httpx
    from pydantic import ValidationError
    if isinstance(error, RevisionConflict):
        return "记录已在推理期间更新，本次结果未覆盖新数据；请刷新后重试。"
    if isinstance(error, httpx.HTTPError):
        return "模型服务请求失败：检查各角色地址、模型、超时和 JSON Schema 支持。"
    if isinstance(error, ValidationError):
        return "模型输出不符合结构化契约；请查看角色配置后重试。"
    if isinstance(error, ValueError):
        return "候选或审核的来源校验失败，本次结果未写入图谱。"
    return "处理失败，既有数据保持不变；请检查服务日志和依赖配置。"

class Coordinator:
    """Role invocations, bounded handoffs and persistent public decision traces."""

    def __init__(self, run: AgentRun) -> None:
        """Attach the coordinator to one durable request."""
        self.run = run
        self.sequence = 0

    def invoke(self, role: str, attempt: int, inputs: object, operation: Callable[[], T], dump: Callable[[T], dict]) -> T:
        """Execute a role with fresh context, storing input digest and structured output."""
        config = role_config(role)
        if config["provider"] != "demo":
            if self.run.model_calls >= settings.agents.max_model_calls:
                raise RuntimeError("model call budget exceeded")
            self.run.model_calls += 1
        self.sequence += 1
        self.run.status, self.run.current_step, self.run.rounds = "running", role, attempt
        event = AgentEvent(id=uuid4().hex, session_id=self.run.session_id, run_id=self.run.id, sequence=self.sequence,
                           role=role, attempt=attempt, provider=config["provider"], model=config["model"] if config["provider"] != "demo" else "deterministic-rules", input_digest=stable_id(inputs))
        with transaction(True) as conn:
            put(conn, "agent_events", event.model_dump())
            put(conn, "agent_runs", self.run.model_dump())
        started = monotonic()
        try:
            result = operation()
            event.output, event.status = dump(result), "completed"
        except Exception as exc:
            event.status, event.error = "failed", safe_error(exc)
            raise
        finally:
            event.duration_ms = round((monotonic() - started) * 1000)
            event.finished_at = now()
            self.run.steps_completed += int(event.status == "completed")
            with transaction(True) as conn:
                put(conn, "agent_events", event.model_dump())
                put(conn, "agent_runs", self.run.model_dump())
        return result

    def generate(self, snap: Snapshot) -> tuple[list[Card], ExtractionCandidates]:
        """Summarize, extract, review, then route bounded feedback to the responsible role."""
        feedback = None
        cards: list[Card] = []
        report = ReviewReport(issues=[])
        candidates = ExtractionCandidates(entities=[], relations=[])
        for attempt in range(settings.agents.max_revisions + 1):
            needs_summary = not cards or any(i.target_type == "card" for i in report.issues)
            roles = (["summary"] if needs_summary else []) + ["extractor", "reviewer"]
            required_calls = sum(role_config(r)["provider"] != "demo" for r in roles)
            if self.run.model_calls + required_calls > settings.agents.max_model_calls:
                break
            if needs_summary:
                cards = self.invoke("summary", attempt, {"segments": [s.model_dump() for s in snap.segments], "feedback": feedback},
                                    lambda: summarize(snap.segments, snap.session.id, snap.session.created_at, feedback), lambda value: {"cards": [c.model_dump() for c in value]})
            candidates = self.invoke("extractor", attempt, {"cards": [c.model_dump() for c in cards], "feedback": feedback},
                                     lambda: extract(cards, snap.segments, feedback), lambda value: value.model_dump())
            report = self.invoke("reviewer", attempt, {"segments": [s.model_dump() for s in snap.segments], "targets": targets(cards, candidates)},
                                 lambda: review(cards, snap.segments, candidates), lambda value: value.model_dump())
            if not any(i.verdict in {"revise", "reject"} for i in report.issues):
                break
            feedback = {"issues": [i.model_dump() for i in report.issues], "targets": targets(cards, candidates)}
        quarantine(cards, candidates, report)
        return cards, candidates

def cached_base(work: Work) -> Snapshot:
    """Restore frozen pre-correction facts, including legacy v1 recordings."""
    if work.cached is None:
        raise ValueError("缺少候选缓存")
    if "base_snapshot" in work.cached:
        base = Snapshot.model_validate(work.cached["base_snapshot"])
    elif work.corrections:
        base = Snapshot.model_validate(work.corrections[0]["before"])
    else:
        base = work.snap.model_copy(deep=True)
    base.session = work.snap.session.model_copy(deep=True)
    base.revision = work.snap.revision
    return base

def replay_corrections(snap: Snapshot, history: list[dict]) -> None:
    """Apply active human events, in order, after model and rule stages."""
    for event in history:
        if event["active"]:
            apply(snap, event["target_type"], event["target_id"], event["action"], event["after"]["operation"])
    reconcile(snap)

def execute(work: Work) -> Snapshot:
    """Infer outside write locks, then compare revisions and atomically commit facts."""
    run = work.run
    try:
        run.status, run.current_step = "running", "restore" if work.cached else "summary"
        save_run(run)
        if work.cached:
            snap, cached = cached_base(work), work.cached
        else:
            snap = work.snap.model_copy(deep=True)
            snap.cards, snap.entities, snap.relations, snap.clusters = [], [], [], []
            snap.cards, candidates = Coordinator(run).generate(snap)
            run.current_step = "convergence"
            save_run(run)
            converge(snap, candidates)
            cluster(snap)
            reconcile(snap)
            cached = {"id": stable_id(snap.session.id, run.fingerprint), "session_id": snap.session.id, "fingerprint": run.fingerprint,
                      "cards": [c.model_dump() for c in snap.cards], "candidates": candidates.model_dump(), "prompt_version": settings.prompt_version,
                      "base_snapshot": snap.model_dump(), "agent_run_id": run.id, "pipeline_version": "v2", "mode": run.mode}
        replay_corrections(snap, work.corrections)
        run.current_step = "commit"
        run.pending_count = sum(x.status == "pending" for x in [*snap.entities, *snap.relations])
        snap.session.status = "ready"
        snap.session.metadata.update({"fingerprint": run.fingerprint, "candidate_cache_hit": run.cached, "agent_run_id": run.id})
        if not work.cached:
            snap.session.metadata.update({"provider": "demo" if run.mode == "demo" else "multi-agent", "pipeline_version": "v2", "prompt_version": settings.prompt_version})
        with transaction(True) as conn:
            current = load_snapshot(conn, snap.session.id)
            if current.revision != run.base_revision:
                raise RevisionConflict("stale inference result")
            if "base_snapshot" not in cached:
                cached = dict(cached, base_snapshot=cached_base(work).model_dump())
            put(conn, "runs", cached)
            save_snapshot(conn, snap)
            run.status, run.current_step, run.result_revision, run.finished_at = "completed", "completed", snap.revision, now()
            put(conn, "agent_runs", run.model_dump())
        return snap
    except Exception as exc:
        run.status = "conflicted" if isinstance(exc, RevisionConflict) else "failed"
        run.error, run.finished_at = safe_error(exc), now()
        save_run(run)
        raise

def process_session(sid: str) -> Snapshot:
    """Synchronous compatibility API using the durable multi-agent execution path."""
    return execute(prepare(sid))

def process(conn: Connection, snap: Snapshot) -> Snapshot:
    """Replay cached facts for rollback only; never infer inside a caller's transaction."""
    cached = next((r for r in rows(conn, "runs", snap.session.id) if r["fingerprint"] == snap.session.metadata.get("fingerprint")), None)
    if cached is None:
        raise ValueError("缺少已提交候选，无法回滚")
    history = sorted(rows(conn, "corrections", snap.session.id), key=lambda c: c["created_at"])
    work = Work(AgentRun(id="replay", session_id=snap.session.id, base_revision=snap.revision, fingerprint=cached["fingerprint"], mode="cached"), snap, cached, history)
    result = cached_base(work)
    replay_corrections(result, history)
    return result

def submit(sid: str) -> AgentRun:
    """Queue inference and return immediately for frontend progress polling."""
    if POOL is None:
        raise RuntimeError("后台执行器尚未启动")
    work = prepare(sid)
    try:
        POOL.submit(execute, work)
    except Exception as exc:
        work.run.status, work.run.error, work.run.finished_at = "failed", safe_error(exc), now()
        save_run(work.run)
        raise
    return AgentRun(**get_run(work.run.id))

def get_run(run_id: str) -> dict:
    """Read a durable execution record for asynchronous clients."""
    with transaction() as conn:
        return get(conn, "agent_runs", run_id)

def startup() -> None:
    """Mark crash-interrupted jobs explicitly instead of silently retrying inference."""
    global POOL
    with transaction(True) as conn:
        for value in rows(conn, "agent_runs"):
            if value["status"] in ACTIVE:
                run = AgentRun(**value)
                run.status, run.finished_at, run.error = "interrupted", now(), "服务重启导致任务中断；原图保持不变，可重新提交。"
                put(conn, "agent_runs", run.model_dump())
                for event in rows(conn, "agent_events", run.session_id):
                    if event["run_id"] == run.id and event["status"] == "running":
                        event.update(status="failed", finished_at=run.finished_at, error=run.error)
                        put(conn, "agent_events", event)
    POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="speaklink-agent")

def shutdown() -> None:
    """Wait for bounded jobs during graceful shutdown; crashes recover on startup."""
    global POOL
    if POOL:
        POOL.shutdown(wait=True)
        POOL = None
