"""Optional adapters for Runnable / compiled LangGraph interfaces."""

from __future__ import annotations

from dreamrsi._invoke import invoke
from dreamrsi.accounting import Usage
from dreamrsi.adapters import FunctionalAgentAdapter


class RunnableAgentAdapter(FunctionalAgentAdapter):
    """Accept a LangChain Runnable or compiled LangGraph exposing ainvoke/invoke.

    Supply input/output transforms for your graph schema. Model clients stay inside
    the runnable. Remote cancellation requires the optional cancel callback.
    Usage extraction must include nested calls if the runnable performs them.
    """

    def __init__(
        self,
        runnable,
        input_transform=None,
        output_transform=None,
        usage_extract=None,
        cancel=None,
    ):
        self.runnable = runnable
        self.input_transform = input_transform or (lambda state: state)
        self.output_transform = output_transform or (lambda output: output)
        self.usage_extract = usage_extract
        self.cancel_callback = cancel
        super().__init__(self._step)

    async def _step(self, state, context):
        config = {"metadata": {"dreamrsi_attempt_id": context["attempt_id"]}}
        fn = getattr(self.runnable, "ainvoke", None) or self.runnable.invoke
        result = await invoke(fn, self.input_transform(state), config=config)
        if self.usage_extract:
            usage = self.usage_extract(result)
            if not isinstance(usage, Usage):
                raise TypeError("usage_extract must return Usage")
            context["report_usage"](usage)
        return self.output_transform(result)

    async def cancel(self, attempt_id):
        if self.cancel_callback:
            return await invoke(self.cancel_callback, attempt_id)
        return False
