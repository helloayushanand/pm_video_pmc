"""Phase 4A LangGraph foundation."""
from langgraph.graph import END, START, StateGraph
from app.agents.component_generation.state import DynamicComponentState

def prepare_scene_node(state: DynamicComponentState) -> dict:
    events = list(state.get("events", []))
    events.append({"node": "prepare_scene", "status": "completed"})
    return {"status": "scene_prepared", "events": events}

def phase_4a_ready_node(state: DynamicComponentState) -> dict:
    events = list(state.get("events", []))
    events.append({"node": "phase_4a_ready", "status": "completed"})
    return {"status": "ready_for_component_generator_agent", "events": events}

def build_phase_4a_graph():
    graph = StateGraph(DynamicComponentState)
    graph.add_node("prepare_scene", prepare_scene_node)
    graph.add_node("phase_4a_ready", phase_4a_ready_node)
    graph.add_edge(START, "prepare_scene")
    graph.add_edge("prepare_scene", "phase_4a_ready")
    graph.add_edge("phase_4a_ready", END)
    return graph.compile()
