from langchain_core.runnables import RunnableConfig
from langmem.short_term import SummarizationNode

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState
from personal_agent.common.timing import log_timed

SUMMARY_CONTEXT_RATIO = 0.8
SUMMARY_TRIGGER_RATIO = 0.7


class HistorySummarizationNode:
    def __init__(self, models: ChatModels) -> None:
        model, parameters = models.get_summary_model()

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

    @log_timed(LogMessages.HISTORY_SUMMARIZATION)
    async def run(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> dict:
        return await self.node.ainvoke(state, config)
