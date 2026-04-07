# from app.agents.intake import intake_agent
# from app.agents.diagnosis import diagnosis_agent
# from app.agents.risk_analyzer import risk_analyzer_agent
# from app.agents.test_recommender import test_recommender_agent
# from app.memory.vector_store import load_vector_store

# def run_pipeline(user_input: str):
#     # Step 1: Intake
#     load_vector_store() 
#     patient = intake_agent(user_input)

#     # Step 2: Diagnosis
#     diagnosis = diagnosis_agent(patient)

#     # Step 3: Risk Analysis
#     risks = risk_analyzer_agent(patient)

#     # Step 4: Test Recommendation
#     tests = test_recommender_agent(patient)

#     # Final Output
#     return {
#         "patient": patient.model_dump(),
#         "diagnosis": diagnosis.model_dump(),
#         "risks": risks,
#         "recommended_tests": tests
#     }


# if __name__ == "__main__":
#     user_input = input("Enter patient symptoms: ")

#     result = run_pipeline(user_input)

#     print("\n=== FINAL OUTPUT ===\n")
#     print(result)








import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.orchestrator.graph import build_graph
from app.memory.vector_store import load_vector_store
import json
from app.tools.formatter import format_medical_response

def run_agentic_system(user_input: str, chat_history: list):
    load_vector_store()
    graph = build_graph()
    
    result = graph.invoke({
        "user_input": user_input,
        "chat_history": chat_history
    })
    
    return result

if __name__ == "__main__":
    chat_history = []
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]:
            break
            
        result = run_agentic_system(user_input, chat_history)

        # Add the interaction to the chat history
        chat_history.append({"role": "user", "content": user_input})
        # Store the raw assistant output in the chat history
        chat_history.append({"role": "assistant", "content": json.dumps(result)})

        # Format the assistant response for human-friendly display
        try:
            formatted = format_medical_response(result)
            # Print an easy-to-read summary plus immediate actions
            print("\nAssistant (summary):\n")
            print(formatted.get("pretty_text", ""))
            # Also print the structured JSON for machine use
            print("\nAssistant (raw JSON):")
            print(json.dumps(formatted, indent=2))
        except Exception:
            # Fallback to raw output if formatting fails
            print("\nAssistant (raw):")
            print(json.dumps(result, indent=2))
        print("\n" + "="*50 + "\n")