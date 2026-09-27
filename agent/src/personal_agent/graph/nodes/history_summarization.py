from langchain_core.runnables import RunnableConfig
from langmem.short_term import SummarizationNode

from personal_agent.llm.model_factory import ChatModels
from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState
from personal_agent.llm.model_definitions import ChatModelName, get_model_definition
from personal_agent.common.timing import log_timing

SUMMARY_CONTEXT_RATIO = 0.8
SUMMARY_TRIGGER_RATIO = 0.7


class HistorySummarizationNode:
    def __init__(self, models: ChatModels) -> None:
        definition = get_model_definition(ChatModelName.GRANITE)
        parameters = definition.parameters
        model = models.get_with_max_new_tokens(
            ChatModelName.GRANITE,
            parameters.summary_max_new_tokens,
        )

        self.node = SummarizationNode(
            model=model,
            max_tokens=int(parameters.context_window * SUMMARY_CONTEXT_RATIO),
            max_tokens_before_summary=int(
                parameters.context_window * SUMMARY_TRIGGER_RATIO
            ),
            max_summary_tokens=parameters.summary_max_new_tokens,
            output_messages_key="messages",
            name="summarize_history",
        )

    async def run(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> dict:
        with log_timing(LogMessages.HISTORY_SUMMARIZATION):
            return await self.node.ainvoke(state, config)
