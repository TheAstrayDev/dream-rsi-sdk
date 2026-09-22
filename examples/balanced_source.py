"""Executable source equivalent to the default BalancedPolicy, used as an incumbent.

This is the initial baseline, never a generated challenger or a manual repair of one.
The model receives this code and independently writes subsequent revisions.
"""

BALANCED_SOURCE = '''import math

def decide(view):
    frontier = view["frontier"]
    if not frontier:
        return {"expand": [], "stop": True}
    total_visits = sum([node["children_count"] + 1 for node in frontier])
    if total_visits == 0:
        total_visits = 1

    def priority(node):
        score = node["score"]
        if score is None:
            score = view["best_score"] or 0.0
        visits = node["children_count"] + 1
        if visits <= 0:
            visits = 1
        return score + 1.41 * math.sqrt(math.log(total_visits) / visits)

    ranked = sorted(frontier, key=priority, reverse=True)
    return {"expand": [node["id"] for node in ranked[:4]], "stop": False}
'''
