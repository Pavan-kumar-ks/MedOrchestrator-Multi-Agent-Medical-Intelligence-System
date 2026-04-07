"""Utilities to format medical assistant responses into a clean, human-friendly structure.

Expose `format_medical_response(response: dict) -> dict` which returns both a machine-friendly
structure and a `pretty_text` human-readable summary suitable for display.
"""
from typing import Any, Dict, List


def _join_lines(title: str, lines: List[str]) -> str:
    if not lines:
        return ""
    out = [f"{title}"]
    for i, l in enumerate(lines, 1):
        out.append(f"{i}. {l}")
    return "\n".join(out)


def format_medical_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw medical response dict into a cleaned structure.

    The returned dict contains:
    - `emergency`: bool
    - `patient`: structured patient info (symptoms, age, gender, duration)
    - `risks`: list of risk strings
    - `recommended_tests`: list of {test_name, reason}
    - `immediate_actions`: prioritized short list of actions to take now
    - `summary`: one-paragraph summary
    - `pretty_text`: multi-paragraph human-readable text combining the above
    - `raw`: original response (unchanged)
    """
    # Safe lookups with defaults
    patient = response.get("patient") or {}
    risks = []
    if isinstance(response.get("risks"), dict):
        risks = response.get("risks", {}).get("risks", [])
    elif isinstance(response.get("risks"), list):
        risks = response.get("risks")

    # Tests
    tests = []
    raw_tests = response.get("tests") or {}
    if isinstance(raw_tests, dict):
        tests = raw_tests.get("tests", [])
    elif isinstance(raw_tests, list):
        tests = raw_tests

    # Remedy / immediate steps
    remedy_steps = []
    raw_remedy = response.get("remedy") or {}
    if isinstance(raw_remedy, dict):
        remedy_steps = raw_remedy.get("remedy_steps", [])

    # Emergency flag
    emergency = bool(response.get("is_emergency") or response.get("emergency") or False)

    # Build short prioritized immediate actions
    immediate_actions = []
    if emergency:
        # If emergency, ensure clear, high-priority actions exist
        if remedy_steps:
            immediate_actions = remedy_steps[:5]
        else:
            immediate_actions = [
                "Call emergency services immediately (e.g., 911).",
                "If unresponsive or not breathing, start CPR if trained.",
                "Sit upright to ease breathing if conscious, avoid lying flat.",
            ]
    else:
        immediate_actions = remedy_steps[:5]

    # Build a compact summary paragraph
    symptoms = patient.get("symptoms") or []
    age = patient.get("age")
    gender = patient.get("gender")
    duration = patient.get("duration_days")

    symptoms_text = ", ".join(symptoms) if symptoms else "no specific symptoms provided"
    demographics = []
    if age is not None:
        demographics.append(f"age {age}")
    if gender:
        demographics.append(gender)
    demographics_text = (", ".join(demographics)) if demographics else ""

    summary_parts = [f"Symptoms: {symptoms_text}."]
    if demographics_text:
        summary_parts.append(f"Patient: {demographics_text}.")
    if risks:
        summary_parts.append(f"Risks: {', '.join(risks)}.")
    summary = " ".join(summary_parts)

    # Compose pretty text
    pretty_sections = []
    pretty_sections.append("Summary:\n" + summary)

    if immediate_actions:
        pretty_sections.append(_join_lines("Immediate actions", immediate_actions))

    if tests:
        test_lines = [f"{t.get('test_name')} — {t.get('reason')}" if isinstance(t, dict) else str(t) for t in tests]
        pretty_sections.append(_join_lines("Recommended tests", test_lines))

    if risks:
        pretty_sections.append(_join_lines("Noted risks", risks))

    pretty_text = "\n\n".join([p for p in pretty_sections if p])

    formatted = {
        "emergency": emergency,
        "patient": {
            "symptoms": symptoms,
            "age": age,
            "gender": gender,
            "duration_days": duration,
        },
        "risks": risks,
        "recommended_tests": tests,
        "immediate_actions": immediate_actions,
        "summary": summary,
        "pretty_text": pretty_text,
        "raw": response,
    }

    return formatted
