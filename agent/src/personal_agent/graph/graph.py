from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.graph.nodes.generation import GenerationNode
from personal_agent.graph.nodes.file_review import apply_file_change, prepare_file_change, review_file_change
from personal_agent.graph.nodes.reminder_review import prepare_reminder, review_reminder, finish_reminder
from personal_agent.graph.nodes.reminder_change_review import prepare_reminder_change, review_reminder_change, finish_reminder_change
from personal_agent.graph.nodes.workflow import select_workflow
from personal_agent.graph.nodes.history_summarization import HistorySummarizationNode
from personal_agent.graph.routers import route_after_generation
from personal_agent.graph.state import AgentState
from personal_agent.tools.filesystem import create_file, list_directory, read_file, update_file
from personal_agent.tools.web_search import create_web_search_tool
from personal_agent.tools.reminder import propose_reminder
from personal_agent.tools.reminder_search import find_reminders
from personal_agent.tools.reminder_update import propose_update_reminder
from personal_agent.tools.reminder_delete import propose_delete_reminder
from personal_agent.tools.macos_shortcuts import get_macos_shortcuts


def build_agent_graph(
    models: ChatModels,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    web_search = create_web_search_tool()
    tools = [list_directory, read_file, web_search, create_file, update_file, propose_reminder,
             find_reminders, propose_update_reminder, propose_delete_reminder, get_macos_shortcuts]
    generation_node = GenerationNode(models, tools)
    history_summarization_node = HistorySummarizationNode(models)

    graph = StateGraph(AgentState)
    graph.add_node("select_workflow", select_workflow)
    graph.add_node("summarize_history", history_summarization_node.run)
    graph.add_node("generate", generation_node.run)
    graph.add_node("tools", ToolNode(
        [list_directory, read_file, web_search, find_reminders, get_macos_shortcuts],
        handle_tool_errors=(RuntimeError, TimeoutError, ValueError, FileNotFoundError, NotADirectoryError),
    ))
    graph.add_node("review_file_change", review_file_change)
    graph.add_node("prepare_file_change", prepare_file_change)
    graph.add_node("apply_file_change", apply_file_change)
    graph.add_node("prepare_reminder", prepare_reminder)
    graph.add_node("review_reminder", review_reminder)
    graph.add_node("finish_reminder", finish_reminder)
    # 기존 체크포인트의 대기 노드 이름을 유지하면서 수정·삭제 경로를 공유한다.
    graph.add_node("prepare_reminder_update", prepare_reminder_change)
    graph.add_node("review_reminder_update", review_reminder_change)
    graph.add_node("finish_reminder_update", finish_reminder_change)

    graph.add_edge(START, "select_workflow")
    graph.add_edge("select_workflow", "summarize_history")
    graph.add_edge("summarize_history", "generate")
    graph.add_conditional_edges(
        "generate",
        route_after_generation, # 다음 경로를 결정하는 함수
        {"tools": "tools", "review_file_change": "prepare_file_change", "review_reminder": "prepare_reminder", "review_reminder_update": "prepare_reminder_update", "end": END}, # 함수 결과와 실제 노드의 매핑
    )
    graph.add_edge("tools", "generate")
    graph.add_edge("prepare_file_change", "review_file_change")
    graph.add_edge("review_file_change", "apply_file_change")
    graph.add_edge("apply_file_change", "generate")
    graph.add_edge("prepare_reminder", "review_reminder")
    graph.add_edge("review_reminder", "finish_reminder")
    graph.add_edge("finish_reminder", "generate")
    graph.add_edge("prepare_reminder_update", "review_reminder_update")
    graph.add_edge("review_reminder_update", "finish_reminder_update")
    graph.add_edge("finish_reminder_update", "generate")
    return graph.compile(checkpointer=checkpointer)
