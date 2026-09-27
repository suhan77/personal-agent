from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.graph.nodes.generation import GenerationNode
from personal_agent.graph.nodes.file_review import apply_file_change, prepare_file_change, review_file_change
from personal_agent.graph.nodes.reminder_review import prepare_reminder, review_reminder, finish_reminder
from personal_agent.graph.nodes.workflow import select_workflow
from personal_agent.graph.nodes.history_summarization import HistorySummarizationNode
from personal_agent.graph.routers import route_after_generation
from personal_agent.graph.state import AgentState
from personal_agent.tools.filesystem import create_file, list_directory, read_file, update_file
from personal_agent.tools.web_search import create_web_search_tool
from personal_agent.tools.reminder import propose_reminder
from personal_agent.tools.reminder_search import find_reminders


def build_agent_graph(
    models: ChatModels,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    web_search = create_web_search_tool()
    tools = [list_directory, read_file, web_search, create_file, update_file, propose_reminder, find_reminders]
    generation_node = GenerationNode(models, tools)
    history_summarization_node = HistorySummarizationNode(models)

    graph = StateGraph(AgentState)
    graph.add_node("select_workflow", select_workflow)
    graph.add_node("summarize_history", history_summarization_node.run)
    graph.add_node("generate", generation_node.run)
    graph.add_node("tools", ToolNode(
        [list_directory, read_file, web_search, find_reminders],
        handle_tool_errors=(RuntimeError, TimeoutError),
    ))
    graph.add_node("review_file_change", review_file_change)
    graph.add_node("prepare_file_change", prepare_file_change)
    graph.add_node("apply_file_change", apply_file_change)
    graph.add_node("prepare_reminder", prepare_reminder)
    graph.add_node("review_reminder", review_reminder)
    graph.add_node("finish_reminder", finish_reminder)

    graph.add_edge(START, "select_workflow")
    graph.add_edge("select_workflow", "summarize_history")
    graph.add_edge("summarize_history", "generate")
    graph.add_conditional_edges(
        "generate",
        route_after_generation, # 다음 경로를 결정하는 함수
        {"tools": "tools", "review_file_change": "prepare_file_change", "review_reminder": "prepare_reminder", "end": END}, # 함수 결과와 실제 노드의 매핑
    )
    graph.add_edge("tools", "generate")
    graph.add_edge("prepare_file_change", "review_file_change")
    graph.add_edge("review_file_change", "apply_file_change")
    graph.add_edge("apply_file_change", "generate")
    graph.add_edge("prepare_reminder", "review_reminder")
    graph.add_edge("review_reminder", "finish_reminder")
    graph.add_edge("finish_reminder", "generate")
    return graph.compile(checkpointer=checkpointer)
