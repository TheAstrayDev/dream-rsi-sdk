"""Real LangChain Runnable integration, no model account required.

Install: python -m pip install -e ".[langchain]"
Run: python examples/04_runnable.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langchain_core.runnables import RunnableLambda  # noqa: E402

from dreamrsi import Budget, DreamRSI  # noqa: E402
from dreamrsi.integrations import RunnableAgentAdapter  # noqa: E402
from dreamrsi.policies import DepthFirstPolicy  # noqa: E402

chain = RunnableLambda(lambda state: state / 2)
rsi = DreamRSI(adapter=RunnableAgentAdapter(chain), evaluator=lambda value: -value,
               policy=DepthFirstPolicy(), budget=Budget(model_calls=3))
result = rsi.run_sync(8)
print("Best:", result.best)
assert result.best == 1
