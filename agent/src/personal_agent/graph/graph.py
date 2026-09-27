from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.graph.nodes.generation import GenerationNode
from personal_agent.graph.nodes.history_summarization import HistorySummarizationNode
from personal_agent.graph.routers import route_after_generation
from personal_agent.graph.state import AgentState
from personal_agent.tools.filesystem import create_file, list_directory


def build_agent_graph(
    models: ChatModels,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    tools = [list_directory, create_file]
    generation_node = GenerationNode(models, tools)
    history_summarization_node = HistorySummarizationNode(models)

    graph = StateGraph(AgentState)
    graph.add_node("summarize_history", history_summarization_node.run)
    graph.add_node("generate", generation_node.run)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "summarize_history")
    graph.add_edge("summarize_history", "generate")
    graph.add_conditional_edges(
        "generate",
        route_after_generation, # 다음 경로를 결정하는 함수
        {"tools": "tools", "end": END}, # 함수 결과와 실제 노드의 매핑
    )
    graph.add_edge("tools", "generate")
    return graph.compile(checkpointer=checkpointer)
