"""Run a quick scenario that simulates an agent failure to demonstrate fallback handling.

This script monkey-patches the `diagnosis_agent` reference used by the graph
so that it raises an exception, then invokes the compiled graph and prints the result.
"""
import json
import traceback
import sys
import os

# Ensure project root is on Python path when running as a script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Pre-stub heavy optional ML libraries to avoid importing them during this quick test.
import types
for _mod in [
    "sentence_transformers",
    "sklearn",
    "pandas",
    "pyarrow",
    "sklearn.metrics",
    "sklearn.utils",
    "sklearn.utils.validation",
    "faiss",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# Provide minimal attr used by embeddings import
if not hasattr(sys.modules.get("sentence_transformers"), "SentenceTransformer"):
    sys.modules["sentence_transformers"].SentenceTransformer = lambda *a, **k: None

import app.orchestrator.graph as graph_module

# Define a failing diagnosis agent
def failing_diagnosis(state):
    raise RuntimeError("simulated diagnosis failure")

# Patch the graph module's reference (graph imports diagnosis_agent at module level)
graph_module.diagnosis_agent = failing_diagnosis

# Build and run the graph
try:
    graph = graph_module.build_graph()
    result = graph.invoke({"user_input": "I have severe chest pain and can't breathe", "chat_history": []})
    print("--- INVOCATION RESULT ---")
    print(json.dumps(result, indent=2))
except Exception as e:
    print("Script failed with exception:")
    traceback.print_exc()
