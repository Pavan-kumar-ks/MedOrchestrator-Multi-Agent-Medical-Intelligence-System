from langgraph.graph import StateGraph, END
from app.orchestrator.state import AgentState
from app.agents.domain_expert import domain_expert_agent
from app.agents.intake import intake_agent
from app.agents.triage import triage_agent
from app.agents.diagnosis import diagnosis_agent
from app.agents.risk_analyzer import risk_analyzer_agent
from app.agents.test_recommender import test_recommender_agent
from app.agents.emergency_remedy_agent import emergency_remedy_agent
from app.orchestrator.router import route_after_diagnosis
from app.orchestrator.agent_runner import call_agent

def build_graph():
    graph = StateGraph(AgentState)

    # Nodes
    def domain_expert_node(state):
        # Wrap domain expert in safe runner; fallback to non-medical
        res = call_agent(domain_expert_agent, args=(state["user_input"],), retries=1, fallback={"is_medical_query": False})
        payload = res.get("result") if res.get("ok") else res.get("result")
        is_medical = False
        try:
            if isinstance(payload, dict) and "is_medical_query" in payload:
                is_medical = bool(payload["is_medical_query"])
        except Exception:
            is_medical = False
        return {"is_medical": is_medical, "is_medical_query": is_medical}

    def intake_node(state):
        # Run intake with fallback that preserves the raw user input as a symptom
        fallback_patient = None
        try:
            from app.schemas.patient import PatientData
            fallback_patient = PatientData(symptoms=[state.get("user_input")])
        except Exception:
            fallback_patient = {"symptoms": [state.get("user_input")]}

        res = call_agent(intake_agent, args=(state,), retries=1, fallback=fallback_patient)
        patient_obj = res.get("result") if res.get("ok") else res.get("result")
        # If Pydantic object, normalize to dict
        try:
            patient_dict = patient_obj.model_dump() if hasattr(patient_obj, "model_dump") else dict(patient_obj)
        except Exception:
            patient_dict = {"symptoms": [state.get("user_input")]}
        return {"patient": patient_dict}

    def triage_node(state):
        from app.schemas.patient import PatientData
        patient = PatientData(**state["patient"])
        # Wrap triage with fallback 'not emergency'
        res = call_agent(triage_agent, args=(patient,), retries=1, fallback={"is_emergency": False})
        payload = res.get("result") if res.get("ok") else res.get("result")
        is_emergency = False
        try:
            if isinstance(payload, dict) and "is_emergency" in payload:
                is_emergency = bool(payload["is_emergency"])
        except Exception:
            is_emergency = False
        return {"is_emergency": is_emergency}

    def diagnosis_node(state):
        # Diagnosis may fail; fallback to Unknown diagnosis
        res = call_agent(diagnosis_agent, args=(state,), retries=1, fallback=None)
        diag_obj = res.get("result") if res.get("ok") else res.get("result")
        try:
            diagnosis_dict = diag_obj.model_dump() if hasattr(diag_obj, "model_dump") else (dict(diag_obj) if diag_obj is not None else {"diagnoses": [{"disease": "Unknown", "reason": "Diagnosis failed", "confidence": 0.0}]})
        except Exception:
            diagnosis_dict = {"diagnoses": [{"disease": "Unknown", "reason": "Diagnosis failed", "confidence": 0.0}]}
        return {"diagnosis": diagnosis_dict}

    def risk_node(state):
        from app.schemas.patient import PatientData
        patient = PatientData(**state["patient"])
        # Risk analyzer wrapped with fallback empty risks
        res = call_agent(risk_analyzer_agent, args=(patient,), retries=1, fallback={"risks": []})
        payload = res.get("result") if res.get("ok") else res.get("result")
        try:
            risks = payload if isinstance(payload, list) else payload.get("risks", payload)
        except Exception:
            risks = []
        return {"risks": risks}

    def test_node(state):
        from app.schemas.patient import PatientData
        patient = PatientData(**state["patient"])
        # Tests recommender with fallback empty list
        res = call_agent(test_recommender_agent, args=(patient,), retries=1, fallback=[])
        payload = res.get("result") if res.get("ok") else res.get("result")
        try:
            tests = payload
        except Exception:
            tests = []
        return {"tests": tests}

    def emergency_node(state):
        print("--- EMERGENCY DETECTED ---")
        print("Generating immediate first-aid advice...")
        from app.schemas.patient import PatientData
        patient = PatientData(**state["patient"])
        # Emergency remedy should be best-effort; fallback to a generic instruction
        res = call_agent(emergency_remedy_agent, args=(patient,), retries=1, fallback={"remedy_steps": ["Call emergency services immediately."]})
        remedy = res.get("result") if res.get("ok") else res.get("result")
        return {"remedy": remedy}

    def non_medical_node(state):
        print("This system is designed to answer medical queries only. Please provide a medical query.")
        return {}

    # Add nodes
    graph.add_node("domain_expert", domain_expert_node)
    graph.add_node("intake", intake_node)
    graph.add_node("triage", triage_node)
    graph.add_node("diagnosis", diagnosis_node)
    graph.add_node("risk", risk_node)
    graph.add_node("tests", test_node)
    graph.add_node("emergency", emergency_node)
    graph.add_node("non_medical", non_medical_node)

    # Flow
    graph.set_entry_point("domain_expert")

    # Conditional routing after domain expert
    def route_after_domain_expert(state):
        if state.get("is_medical_query"):
            return "intake"
        return "non_medical"

    graph.add_conditional_edges(
        "domain_expert",
        route_after_domain_expert,
        {
            "intake": "intake",
            "non_medical": "non_medical"
        }
    )
    graph.add_edge("non_medical", END)

    graph.add_edge("intake", "triage")

    # Conditional routing after triage
    def route_after_triage(state):
        if state.get("is_emergency"):
            return "emergency"
        return "diagnosis"

    graph.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "emergency": "emergency",
            "diagnosis": "diagnosis"
        }
    )
    
    graph.add_edge("emergency", "risk")

    # Conditional routing after diagnosis
    graph.add_conditional_edges(
        "diagnosis",
        route_after_diagnosis,
        {
            "risk": "risk",
            "tests": "tests"
        }
    )

    graph.add_edge("risk", "tests")
    graph.add_edge("tests", END)

    return graph.compile()