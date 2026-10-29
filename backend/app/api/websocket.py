import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from litellm import BadRequestError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.security import decode_access_token
from app.models.message import Message
from app.models.project import Project, ResearcherProject
from app.models.session import Session
from app.models.trace import ResearchTrace
from app.models.user import User, Workspace
from app.services.llm_service import build_prompt, stream_llm_response
from app.services.rag_service import classify_query_mode, retrieve_chunks
from app.services.runtime_config import get_runtime_llm_api_key, get_runtime_value
from app.services.trace_service import build_trace_payload
from app.services.source_group_service import expand_source_ids_for_rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


def public_websocket_error_message(error: Exception) -> str:
    """Return a user-facing error message for websocket generation failures."""
    error_text = str(error)
    lower = error_text.lower()
    logger.warning(
        "LLM error classification: raw_text=%r",
        error_text[:300],
    )
    if "timed out" in lower:
        return "The model request timed out. Check the LLM endpoint and try again."
    if "502" in error_text or "badgateway" in lower:
        return (
            "The configured model endpoint returned 502 Bad Gateway. "
            "The upstream model service may be unavailable."
        )
    if "LLM Provider NOT provided" in error_text:
        return (
            "LLM model configuration is invalid. Use a provider-qualified model "
            "name such as 'openai/your-model' for custom OpenAI-compatible endpoints."
        )
    if "invalid model" in lower or "model name" in lower:
        return (
            "The configured model name is not available on this LLM endpoint. "
            "Open Admin > LLM Profiles, pick a model from Fetch Models, save, and activate."
        )
    if (
        "authentication" in lower
        or "unauthorized" in lower
        or "invalid api key" in lower
        or "api key" in lower and ("invalid" in lower or "401" in error_text)
    ):
        return (
            "LLM authentication failed. Check the API key on the active LLM profile."
        )
    if "/embed" in error_text or "worker" in lower:
        return (
            "Document embedding failed. Ensure the worker service is running "
            "(port 8001) and try again."
        )
    if "connection" in lower or "connect" in lower:
        return (
            "Could not reach the LLM endpoint. Check the API base URL and network/proxy."
        )
    return "The model request failed. Check the LLM settings and backend logs."


async def _get_session_for_websocket_user(
    session_id: str,
    user_id: str,
    db: AsyncSession,
) -> Session | None:
    result = await db.execute(
        select(Session)
        .join(Workspace, Workspace.id == Session.workspace_id)
        .where(
            Session.id == session_id,
            Workspace.researcher_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return session
    # Project owners and privileged roles may open member sessions.
    session = await db.get(Session, session_id)
    if session is None or session.project_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None:
        return None
    if user.role in (ROLE_ADMIN, ROLE_PI):
        return session
    result = await db.execute(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == session.project_id,
            ResearcherProject.researcher_id == user_id,
            ResearcherProject.role == "owner",
        )
    )
    return session if result.scalar_one_or_none() is not None else None


@router.websocket("/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str, token: str = ""):
    # Authenticate
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    async with async_session_factory() as db:
        session = await _get_session_for_websocket_user(session_id, user_id, db)
        if not session:
            await websocket.close(code=4404, reason="Session not found")
            return

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "")
            source_ids = data.get("source_ids", [])
            locale = data.get("locale")
            replace_message_id = data.get("replace_message_id")
            logger.debug("WS message: content=%r source_ids=%s", content[:40], source_ids)

            async with async_session_factory() as db:
                session = await _get_session_for_websocket_user(session_id, user_id, db)
                if not session:
                    await websocket.send_json(
                        {"type": "error", "message": "Session not found"}
                    )
                    continue

                replacement_message = None
                if replace_message_id:
                    result = await db.execute(
                        select(Message).where(
                            Message.id == replace_message_id,
                            Message.session_id == session_id,
                            Message.role == "assistant",
                        )
                    )
                    replacement_message = result.scalar_one_or_none()
                    if replacement_message is None:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "The answer to regenerate was not found.",
                            }
                        )
                        continue

                # Save user message for normal sends. Regeneration reuses the
                # previous prompt and replaces the target assistant answer.
                if replacement_message is None:
                    user_msg = Message(
                        session_id=session_id, role="user", content=content
                    )
                    db.add(user_msg)
                    await db.commit()

                # Auto-generate title from first user message
                if not session.title:
                    title = content.strip().replace("\n", " ")
                    if len(title) > 50:
                        title = title[:47] + "..."
                    session.title = title
                    await db.commit()
                    await websocket.send_json(
                        {"type": "title_updated", "title": session.title}
                    )

                # Resolve LLM config (needed for both classification and generation)
                llm_model = await get_runtime_value("llm_model", db)
                llm_api_base = await get_runtime_value("llm_api_base", db)
                llm_api_key = await get_runtime_llm_api_key(db)

                # Expand group sources to leaf sources
                expanded_source_ids = await expand_source_ids_for_rag(
                    source_ids, db, user_id
                )

                # Classify query intent, then retrieve accordingly
                if expanded_source_ids:
                    mode = await classify_query_mode(
                        content, llm_model, llm_api_base, llm_api_key
                    )
                    chunks = await retrieve_chunks(
                        content,
                        expanded_source_ids,
                        db,
                        mode=mode,
                        user_id=user_id,
                        project_id=session.project_id,
                        agent_run_id=f"chat:{session_id}",
                    )
                else:
                    chunks = []

                # Get chat history
                result = await db.execute(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at, Message.id)
                    .limit(20)
                )
                history = [
                    {"role": m.role, "content": m.content}
                    for m in result.scalars().all()
                    if (m.content or "").strip() and m.id != replace_message_id
                ]

                # Build prompt and stream response
                project_instructions = None
                if session.project_id:
                    project = await db.get(Project, session.project_id)
                    project_instructions = project.instructions if project else None
                prompt_history = history[:-1] if replacement_message is None else history
                if expanded_source_ids:
                    prompt_history = []
                messages = build_prompt(
                    content,
                    chunks,
                    prompt_history,
                    locale=locale,
                    project_instructions=project_instructions,
                )
                logger.info(
                    "WS generation start session=%s sources=%d chunks=%d history=%d",
                    session_id,
                    len(expanded_source_ids),
                    len(chunks),
                    len(history[:-1]),
                )

                full_response = ""
                try:
                    async for token_text in stream_llm_response(
                        messages,
                        model=llm_model,
                        api_base=llm_api_base,
                        api_key=llm_api_key,
                    ):
                        full_response += token_text
                        await websocket.send_json(
                            {"type": "token", "content": token_text}
                        )
                except Exception:
                    logger.exception(
                        "WS generation failed session=%s model=%r api_base=%r has_key=%s",
                        session_id,
                        llm_model,
                        llm_api_base,
                        bool(llm_api_key),
                    )
                    raise

                if not full_response.strip():
                    logger.warning(
                        "WS generation returned empty response session=%s",
                        session_id,
                    )
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                "The model returned an empty response. "
                                "Try a different LLM profile or ask a shorter question."
                            ),
                        }
                    )
                    continue

                trace_payload = build_trace_payload(
                    query=content,
                    source_ids=expanded_source_ids,
                    retrieved_chunks=chunks,
                    locale=locale,
                )

                if replacement_message is not None:
                    assistant_msg = replacement_message
                    assistant_msg.content = full_response
                    result = await db.execute(
                        select(ResearchTrace)
                        .where(ResearchTrace.message_id == assistant_msg.id)
                        .order_by(ResearchTrace.created_at.desc())
                    )
                    trace = result.scalars().first()
                    if trace is None:
                        trace = ResearchTrace(
                            session_id=session_id,
                            message_id=assistant_msg.id,
                            user_id=user_id,
                        )
                        db.add(trace)
                    trace.inputs_json = trace_payload["inputs"]
                    trace.retrieval_json = trace_payload["retrieval"]
                    trace.citations_json = trace_payload["citations"]
                    trace.summary_steps_json = trace_payload["summary_steps"]
                else:
                    assistant_msg = Message(
                        session_id=session_id,
                        role="assistant",
                        content=full_response,
                    )
                    trace = ResearchTrace(
                        session_id=session_id,
                        message_id=None,
                        user_id=user_id,
                        inputs_json=trace_payload["inputs"],
                        retrieval_json=trace_payload["retrieval"],
                        citations_json=trace_payload["citations"],
                        summary_steps_json=trace_payload["summary_steps"],
                    )
                    db.add(assistant_msg)
                    await db.flush()
                    trace.message_id = assistant_msg.id
                    db.add(trace)
                await db.commit()
                await db.refresh(assistant_msg)
                await db.refresh(trace)

                await websocket.send_json(
                    {
                        "type": "done",
                        "content": full_response,
                        "message_id": assistant_msg.id,
                        "trace_id": trace.id,
                        "inputs": trace_payload["inputs"],
                        "retrieval": trace_payload["retrieval"],
                        "citations": trace_payload["citations"],
                        "summary_steps": trace_payload["summary_steps"],
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except BadRequestError as e:
        logger.error("WebSocket LLM error: %s", e)
        await websocket.send_json(
            {
                "type": "error",
                "message": public_websocket_error_message(e),
            }
        )
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        await websocket.send_json(
            {
                "type": "error",
                "message": public_websocket_error_message(e),
            }
        )
        await websocket.close(code=1011, reason="Internal error")
