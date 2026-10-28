"""FastAPI entrypoint: transactional APIs, local uploads and consistent graph snapshots."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4
import importlib.util
import logging
import httpx
from alembic.config import Config
from alembic import command
from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings, ROOT
from .models.database import transaction, get, put, rows, load_snapshot, save_snapshot
from .schemas.domain import Session, Snapshot, TranscriptSegment, Card, TopicCluster, Correction, QueryLog, Export, now
from .schemas.api import CreateSession, TranscriptInput, SearchRequest, SearchResult, CorrectionInput, EntityPatch, RelationPatch, Health, Graph
from .schemas.agents import AgentRun, AgentEvent, RunDetail
from .services.common import stable_id
from .services import asr, pipeline, corrections, graph_store, search as retrieval, export as exporting

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run forward migrations on startup before serving requests."""
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    pipeline.startup()
    try:
        yield
    finally:
        pipeline.shutdown()

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["GET", "POST", "PUT", "PATCH"], allow_headers=["Content-Type"])

@app.exception_handler(pipeline.RunBusy)
async def busy_error(_: Request, exc: pipeline.RunBusy) -> JSONResponse:
    """Reject duplicate jobs while allowing other recordings to progress."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.exception_handler(pipeline.RevisionConflict)
async def conflict_error(_: Request, exc: pipeline.RevisionConflict) -> JSONResponse:
    """Preserve edits made while agents were reasoning outside the transaction."""
    return JSONResponse(status_code=409, content={"detail": pipeline.safe_error(exc)})

@app.exception_handler(LookupError)
async def not_found(_: Request, exc: LookupError) -> JSONResponse:
    """Map missing local resources to 404."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(ValueError)
async def invalid(_: Request, exc: ValueError) -> JSONResponse:
    """Map semantic/schema validation failures to explicit client errors."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})

@app.exception_handler(RuntimeError)
async def unavailable(_: Request, exc: RuntimeError) -> JSONResponse:
    """Surface missing model dependencies without returning fabricated output."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})

@app.exception_handler(httpx.HTTPError)
async def model_error(_: Request, exc: httpx.HTTPError) -> JSONResponse:
    """Expose model unavailability without credentials or external response bodies."""
    logging.warning("Model request failed: %s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "模型服务不可用；检查 LLM 地址、模型及 JSON Schema 支持"})

@app.get("/api/health", response_model=Health)
def health() -> Health:
    """Report application and configured inference modes."""
    installed = importlib.util.find_spec("faster_whisper") is not None
    return Health(status="ok", llm_provider=settings.llm_provider, embedding_provider=settings.embedding_provider,
                  asr_installed=installed, asr_model=Path(settings.asr_model).name,
                  asr_message="语音引擎已安装，首次使用需加载模型。" if installed else "语音转写组件尚未安装，录音和上传暂时无法转成文字。请先完成语音环境安装。")

@app.post("/api/sessions", response_model=Session, status_code=201)
def create(body: CreateSession) -> Session:
    """Create a recording and persist it before returning its ID."""
    session = Session(id=uuid4().hex, title=body.title, language=body.language)
    with transaction(True) as conn:
        put(conn, "sessions", session.model_dump())
    return session

@app.get("/api/sessions", response_model=list[Session])
def timeline() -> list[Session]:
    """Return newest recordings first."""
    with transaction() as conn:
        return sorted([Session(**x) for x in rows(conn, "sessions")], key=lambda s: s.created_at, reverse=True)

@app.get("/api/sessions/{sid}", response_model=Snapshot)
def detail(sid: str) -> Snapshot:
    """Return a single-revision snapshot for both linked frontend views."""
    with transaction() as conn:
        return load_snapshot(conn, sid)

@app.put("/api/sessions/{sid}/transcript", response_model=Snapshot)
def set_transcript(sid: str, body: TranscriptInput) -> Snapshot:
    """Import a transcript; processed recordings are immutable source material."""
    with transaction(True) as conn:
        snap = load_snapshot(conn, sid)
        if snap.cards or rows(conn, "runs", sid):
            raise HTTPException(409, "已处理记录请新建副本修改原文，避免校正引用失效")
        snap.segments = [TranscriptSegment(id=stable_id(sid, "segment", i), session_id=sid, text=asr.clean_text(s.text), raw_text=s.text, start_ms=s.start_ms, end_ms=s.end_ms, speaker=s.speaker) for i, s in enumerate(body.segments)]
        snap.session.duration_ms = max(s.end_ms for s in snap.segments)
        snap.session.status = "transcribed"
        save_snapshot(conn, snap)
        return snap

@app.post("/api/sessions/{sid}/audio", response_model=Session)
def audio(sid: str, file: UploadFile) -> Session:
    """Stream bounded audio to a generated safe path and attach it transactionally."""
    suffix = Path(file.filename or "audio.webm").suffix.lower()
    if suffix not in {".webm", ".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac"}:
        raise HTTPException(415, "不支持的音频格式")
    directory = settings.data_dir / "audio"
    directory.mkdir(exist_ok=True)
    path = directory / f"{uuid4().hex}{suffix}"
    try:
        total = 0
        with path.open("wb") as stream:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "音频超过大小限制")
                stream.write(chunk)
        if total == 0:
            raise HTTPException(422, "音频为空")
        with transaction(True) as conn:
            snap = load_snapshot(conn, sid)
            if snap.cards:
                raise HTTPException(409, "已处理记录请新建记录上传")
            old_path = snap.session.audio_path
            snap.session.audio_path, snap.session.status = str(path), "uploaded"
            save_snapshot(conn, snap)
        if old_path:
            Path(old_path).unlink(missing_ok=True)
        return snap.session
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()

@app.post("/api/sessions/{sid}/transcribe", response_model=Snapshot)
def transcribe(sid: str) -> Snapshot:
    """Transcribe real audio; model/download errors remain explicit."""
    with transaction() as conn:
        snap = load_snapshot(conn, sid)
        if snap.cards:
            raise HTTPException(409, "已处理记录不能重新转写")
        if not snap.session.audio_path:
            raise HTTPException(422, "请先上传音频")
    snap.segments = asr.transcribe(snap.session.audio_path, sid, snap.session.language)
    if not snap.segments:
        raise HTTPException(422, "未检测到语音")
    snap.session.duration_ms = max(s.end_ms for s in snap.segments)
    snap.session.status = "transcribed"
    with transaction(True) as conn:
        if load_snapshot(conn, sid).revision != snap.revision:
            raise pipeline.RevisionConflict("source changed during ASR")
        save_snapshot(conn, snap)
        return snap

@app.post("/api/sessions/{sid}/process", response_model=Snapshot)
def process(sid: str) -> Snapshot:
    """Run candidate/convergence/correction stages and commit one new revision."""
    return pipeline.process_session(sid)

@app.post("/api/sessions/{sid}/jobs", response_model=AgentRun, status_code=202)
def process_async(sid: str) -> AgentRun:
    """Start bounded background collaboration and return its durable execution ID."""
    return pipeline.submit(sid)

@app.get("/api/sessions/{sid}/runs", response_model=list[AgentRun])
def runs(sid: str) -> list[AgentRun]:
    """Return newest execution first, including cached replays and failed attempts."""
    with transaction() as conn:
        get(conn, "sessions", sid)
        return sorted([AgentRun(**r) for r in rows(conn, "agent_runs", sid)], key=lambda r: r.created_at, reverse=True)

@app.get("/api/runs/{rid}", response_model=RunDetail)
def run_detail(rid: str) -> RunDetail:
    """Read role progress, public decisions and structured outputs in one transaction."""
    with transaction() as conn:
        run = AgentRun(**get(conn, "agent_runs", rid))
        events = [AgentEvent(**e) for e in rows(conn, "agent_events", run.session_id) if e["run_id"] == rid]
        return RunDetail(run=run, events=sorted(events, key=lambda e: e.sequence))

@app.post("/api/sessions/{sid}/clone", response_model=Session, status_code=201)
def clone(sid: str) -> Session:
    """Copy transcript into a fresh recording for new models without invalidating old corrections."""
    with transaction(True) as conn:
        original = load_snapshot(conn, sid)
        session = Session(id=uuid4().hex, title=original.session.title[:180] + " · 重新分析", language=original.session.language,
                          duration_ms=original.session.duration_ms, status="transcribed", metadata={"copied_from": sid})
        put(conn, "sessions", session.model_dump())
        copied = Snapshot(session=session, segments=[s.model_copy(update={"id": stable_id(session.id, "segment", i), "session_id": session.id, "text": asr.clean_text(s.text)}) for i, s in enumerate(original.segments)])
        save_snapshot(conn, copied)
        return copied.session

@app.get("/api/sessions/{sid}/transcript", response_model=list[TranscriptSegment])
def transcript(sid: str) -> list[TranscriptSegment]:
    """Read timestamped source evidence."""
    return detail(sid).segments

@app.get("/api/sessions/{sid}/cards", response_model=list[Card])
def cards(sid: str) -> list[Card]:
    """Read current cards, including explicit pending status."""
    return detail(sid).cards

@app.get("/api/sessions/{sid}/graph", response_model=Graph)
def graph(sid: str, mode: Literal['knowledge', 'evidence'] = 'knowledge') -> Graph:
    """Read accepted graph and count uncertain candidates."""
    snap = detail(sid)
    return graph_store.evidence_view(snap) if mode == 'evidence' else graph_store.graph_view(snap)

@app.get("/api/sessions/{sid}/clusters", response_model=list[TopicCluster])
def clusters(sid: str) -> list[TopicCluster]:
    """Read topic memberships and boundary explanations."""
    return detail(sid).clusters

@app.post("/api/sessions/{sid}/search", response_model=SearchResult)
def search(sid: str, body: SearchRequest) -> SearchResult:
    """Retrieve current cards and real graph paths, recording the query."""
    with transaction() as conn:
        snap = load_snapshot(conn, sid)
    result = retrieval.search(snap, body.query, body.limit)
    with transaction(True) as conn:
        if load_snapshot(conn, sid).revision != snap.revision:
            raise pipeline.RevisionConflict("graph changed during retrieval")
        log = QueryLog(id=uuid4().hex, session_id=sid, query=body.query, retrieved_card_ids=[c.id for c in result.cards], graph_path=result.paths)
        put(conn, "queries", log.model_dump())
        return result

@app.post("/api/corrections", response_model=Snapshot)
def correct(body: CorrectionInput) -> Snapshot:
    """Commit one human correction with optimistic concurrency and complete audit."""
    with transaction(True) as conn:
        snap = load_snapshot(conn, body.session_id)
        if snap.revision != body.expected_revision:
            raise HTTPException(409, "记录已更新，请刷新后重试")
        before = snap.model_dump()
        corrections.apply(snap, body.target_type, body.target_id, body.action, body.payload)
        correction = Correction(id=uuid4().hex, session_id=body.session_id, target_type=body.target_type, target_id=body.target_id, action=body.action, before=before, after={"operation": body.payload, "snapshot": snap.model_dump()}, operator=body.operator)
        put(conn, "corrections", correction.model_dump())
        save_snapshot(conn, snap)
        return snap

@app.get("/api/sessions/{sid}/corrections", response_model=list[Correction])
def history(sid: str) -> list[Correction]:
    """List immutable correction history with active/rolled-back flags."""
    with transaction() as conn:
        get(conn, "sessions", sid)
        return sorted([Correction(**c) for c in rows(conn, "corrections", sid)], key=lambda c: c.created_at)

@app.post("/api/corrections/{cid}/rollback", response_model=Snapshot)
def rollback(cid: str, expected_revision: int) -> Snapshot:
    """Rollback latest active event only; replay earlier events to avoid stale snapshots."""
    with transaction(True) as conn:
        correction = get(conn, "corrections", cid)
        snap = load_snapshot(conn, correction["session_id"])
        if snap.revision != expected_revision:
            raise HTTPException(409, "记录已更新")
        active = sorted([c for c in rows(conn, "corrections", snap.session.id) if c["active"]], key=lambda c: c["created_at"])
        if not active or active[-1]["id"] != cid:
            raise HTTPException(409, "请按逆序回滚，避免破坏后续校正依赖")
        correction["active"] = False
        put(conn, "corrections", correction)
        snap = pipeline.process(conn, snap)
        save_snapshot(conn, snap)
        return snap

@app.patch("/api/entities/{eid}", response_model=Snapshot)
def patch_entity(eid: str, body: EntityPatch) -> Snapshot:
    """Route entity edits through the same audit/replay workflow."""
    with transaction() as conn:
        entity = get(conn, "entities", eid)
    return correct(CorrectionInput(session_id=entity["session_id"], target_type="entity", target_id=eid, action="update", payload=body.model_dump(exclude_none=True, exclude={"expected_revision"}), expected_revision=body.expected_revision))

@app.patch("/api/relations/{rid}", response_model=Snapshot)
def patch_relation(rid: str, body: RelationPatch) -> Snapshot:
    """Route relation edits through the same audit/replay workflow."""
    with transaction() as conn:
        relation = get(conn, "relations", rid)
    return correct(CorrectionInput(session_id=relation["session_id"], target_type="relation", target_id=rid, action="update", payload=body.model_dump(exclude_none=True, exclude={"expected_revision"}), expected_revision=body.expected_revision))

@app.get("/api/sessions/{sid}/export")
def export(sid: str, format: Literal["json", "graphml", "markdown"] = "json") -> Response:
    """Export a single consistent snapshot and audit the artifact path."""
    with transaction(True) as conn:
        snap = load_snapshot(conn, sid)
        content, media_type, suffix = exporting.export(snap, format)
        directory = settings.data_dir / "exports"
        directory.mkdir(exist_ok=True)
        path = directory / f"{sid}-{snap.revision}.{suffix}"
        path.write_text(content, encoding="utf-8")
        put(conn, "exports", Export(id=uuid4().hex, session_id=sid, format=format, path=str(path)).model_dump())
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="speaklink-{sid}.{suffix}"'})
