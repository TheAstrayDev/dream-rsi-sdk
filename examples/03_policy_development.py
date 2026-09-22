"""Offline developer plumbing demo. The source provider is a fixture, not an LLM.

Replace generate_source with your model call; keep the fixed agent/evaluator.
No Docker, network or API keys are required for this reproducible example.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dreamrsi import Budget, DreamRSI, LLMPolicyDeveloper  # noqa: E402

SOURCE = """def decide(view):
    if view["calls_used"] >= 1:
        return {"expand": [], "stop": True}
    return {"expand": [view["frontier"][0]["id"]]}
"""


async def generate_source(request):
    print("Developer revision:", request["revision"])
    print("Feedback fields:", list(request["feedback"]))
    # Substitute a real fixed model that returns SDK policy-language source here.
    return SOURCE


async def main():
    developer = LLMPolicyDeveloper(generate_source, revisions=2)
    rsi = DreamRSI(agent=lambda task: task, evaluator=float,
                   policy_optimizer=developer, budget=Budget(model_calls=4),
                   campaign_budget=Budget(model_calls=8, developer_calls=2))
    result = await rsi.improve(10, rounds=1)
    print("Revisions saved:", len(developer.history))
    print("Promotions:", result.metrics["policy_promotions"])
    print("Usage:", rsi.usage.spent)
    print("Toy result only; no evidence of real-model improvement.")


if __name__ == "__main__":
    asyncio.run(main())
