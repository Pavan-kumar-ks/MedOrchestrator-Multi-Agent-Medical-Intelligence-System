import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agents.hospital_detail_agent import hospital_detail_agent
from app.agents.location_intake import location_intake_agent
from app.main import (
    _looks_like_hospital_query,
    _match_hospital,
    _store_diagnosis_context,
    _try_parse_age,
    format_hospital_details,
    format_medical_response,
    run_agentic_system,
)
from app.memory.session_memory import SessionMemory


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"


class MessageRequest(BaseModel):
    message: str


class SessionState:
    def __init__(self) -> None:
        self.chat_history: List[Dict[str, str]] = []
        self.memory = SessionMemory()


sessions: Dict[str, SessionState] = {}

app = FastAPI(
    title="MedOrchestrator UI",
    description="Browser interface for the Medical Multi-Agent clinical decision support pipeline.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _new_session() -> tuple[str, SessionState]:
    session_id = uuid.uuid4().hex
    state = SessionState()
    sessions[session_id] = state
    return session_id, state


def _response(
    state: SessionState,
    message: str,
    kind: str = "assistant",
    raw: Dict[str, Any] | None = None,
    structured: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    raw = raw or {}
    return {
        "kind": kind,
        "message": message,
        "session_memory": state.memory.data,
        "raw": raw,
        "structured": structured or {},
        "details": details or {},
        "agent_trace": raw.get("_agent_trace", []),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/api/session")
def create_session() -> Dict[str, Any]:
    session_id, state = _new_session()
    state.memory.set("awaiting_name", True)
    return {"session_id": session_id, "session_memory": state.memory.data}


@app.get("/api/session/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    state = sessions.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "session_memory": state.memory.data,
        "chat_history": state.chat_history,
    }


@app.post("/api/session/{session_id}/message")
def post_message(session_id: str, body: MessageRequest) -> Dict[str, Any]:
    state = sessions.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    user_input = body.message.strip()
    if not user_input:
        return _response(state, "Please describe your disease or main symptoms.")

    memory = state.memory

    if memory.get("awaiting_name"):
        memory.set("name", user_input)
        memory.set("awaiting_name", False)
        memory.set("awaiting_age", True)
        return _response(state, f"Thanks, {user_input}. Please share your age.")

    if not memory.get("name"):
        memory.set("awaiting_name", True)
        return _response(state, "Please share your name.")

    if memory.get("awaiting_age"):
        age = _try_parse_age(user_input)
        if age is None:
            return _response(state, "Please provide your age as a number, for example 29.")
        memory.set("age", age)
        memory.set("awaiting_age", False)
        memory.set("awaiting_location", True)
        return _response(state, "Please share your current location, city, neighbourhood, or a nearby landmark.")

    if not memory.get("age"):
        memory.set("awaiting_age", True)
        return _response(state, "Please share your age.")

    if memory.get("confirm_location"):
        answer = user_input.lower()
        if answer in ["yes", "y", "correct"] or answer.startswith("y"):
            candidate = memory.get("location_candidate")
            if isinstance(candidate, dict):
                memory.set("location", candidate)
            memory.set("confirm_location", False)
            memory.set("awaiting_location", False)
            return _response(
                state,
                'Location confirmed. Please describe your disease or main symptoms, for example "I have sudden shortness of breath and chest pain".',
            )
        if answer in ["no", "n", "incorrect"] or answer.startswith("n"):
            memory.set("confirm_location", False)
            memory.set("awaiting_location", True)
            return _response(state, "Please provide a nearby landmark or more specific location.")
        return _response(state, "Please answer with yes or no to confirm your location.")

    if memory.get("awaiting_location"):
        loc_result = location_intake_agent(
            {
                "user_input": user_input,
                "session_memory": memory.data,
                "chat_history": state.chat_history,
            }
        )
        if loc_result.get("session_memory"):
            memory.update(loc_result["session_memory"])
        if loc_result.get("confirm_location"):
            candidate = loc_result.get("location_candidate") or {}
            formatted = candidate.get("formatted") or candidate.get("text") or "this location"
            return _response(state, f"Is this your location? {formatted} (yes/no)")
        if loc_result.get("need_location"):
            return _response(state, loc_result.get("location_prompt", "Please provide your location."))
        memory.set("awaiting_location", False)

    if not memory.get("location"):
        memory.set("awaiting_location", True)
        return _response(state, "Please share your current location, city, neighbourhood, or a nearby landmark.")

    if memory.get("awaiting_hospital_selection"):
        shown_hospitals = memory.get("shown_hospitals") or []
        matched = _match_hospital(user_input, shown_hospitals)

        if matched:
            hospital_name = matched.get("name", "")
            top_disease = memory.get("last_top_disease", "")
            location_data = memory.get("location") or {}
            location_hint = location_data.get("formatted") or location_data.get("text") or ""
            details = hospital_detail_agent(hospital_name, top_disease, location_hint)
            pretty = format_hospital_details(hospital_name, top_disease, details)
            memory.set("awaiting_hospital_selection", True)
            return _response(
                state,
                pretty,
                kind="hospital_details",
                details=details,
            )

        if _looks_like_hospital_query(user_input):
            names = "\n".join(
                f"{index}. {hospital.get('name', '')}"
                for index, hospital in enumerate(shown_hospitals, 1)
            )
            return _response(
                state,
                f'I could not find "{user_input}" in the hospital list. Please type the exact name or use a number:\n{names}',
            )

        memory.set("awaiting_hospital_selection", False)

    result = run_agentic_system(user_input, state.chat_history, memory)
    _store_diagnosis_context(memory, result)

    if result.get("session_memory"):
        memory.update(result["session_memory"])

    state.chat_history.append({"role": "user", "content": user_input})
    state.chat_history.append({"role": "assistant", "content": json.dumps(result)})

    formatted = format_medical_response(result)
    hospitals = result.get("hospitals") or []
    followup = result.get("followup_answer")
    if hospitals and not followup:
        memory.set("shown_hospitals", hospitals)
        memory.set("awaiting_hospital_selection", True)

    message = formatted.get("pretty_text") or followup or "Assessment complete."
    kind = "followup" if followup else "assessment"
    return _response(
        state,
        message,
        kind=kind,
        raw=result,
        structured=formatted,
    )
