"""Bounded interpretation of Appendix B class syntax, without exec or host imports."""

from __future__ import annotations

import ast
import copy
from dataclasses import asdict

from dreamrsi.appendix import observation_signal
from dreamrsi.appendix.api import GridPlan, LLMDesignedMethod, Observation, finalize_result
from dreamrsi.artifacts import PolicyArtifact
from dreamrsi.errors import SandboxError
from dreamrsi.sandbox import PolicySandbox, _Interpreter

_API = {
    "LLMDesignedMethod",
    "GridPlan",
    "GridPlanningContext",
    "SimResult",
    "_budget_done",
    "_record_curve",
    "finalize_result",
}
_SIGNALS = {
    "branch_promising",
    "branch_failed_hard",
    "probe_improved_vs_parent",
    "probe_improved_vs_baseline",
    "successful",
    "trajectory_signal",
}
_IMPORTS = {
    "see.policy.api": _API,
    "dreamrsi.appendix.api": _API,
    "see.policy.observation_signal": _SIGNALS,
    "dreamrsi.appendix.observation_signal": _SIGNALS,
}


class _Lower(ast.NodeTransformer):
    def __init__(self, methods):
        self.methods = methods

    def visit_Call(self, node):
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr in self.methods
        ):
            node.args.insert(0, ast.Name(id="self", ctx=ast.Load()))
            node.func = ast.Name(id="policy" + node.func.attr, ctx=ast.Load())
        return self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            if node.attr.startswith("__"):
                raise SandboxError("Private Python object attributes are unavailable")
            return ast.copy_location(
                ast.Subscript(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    slice=ast.Constant(node.attr),
                    ctx=node.ctx,
                ),
                node,
            )
        return self.generic_visit(node)


def lower_source(source):
    if not isinstance(source, str) or len(source.encode()) > 131072:
        raise SandboxError("Appendix source limit exceeded")
    tree = ast.parse(source)
    if sum(1 for _ in ast.walk(tree)) > 16000:
        raise SandboxError("Appendix AST limit exceeded")
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1 or classes[0].name != "OptimalPolicy":
        raise SandboxError("Define exactly one class OptimalPolicy(LLMDesignedMethod)")
    cls = classes[0]
    if not any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "NAME"
        and isinstance(node.value, ast.Constant)
        and node.value.value == "OptimalPolicy"
        for node in tree.body
    ):
        raise SandboxError("Keep module NAME = 'OptimalPolicy'")
    if (
        cls.decorator_list
        or cls.keywords
        or len(cls.bases) != 1
        or not isinstance(cls.bases[0], ast.Name)
        or cls.bases[0].id != "LLMDesignedMethod"
    ):
        raise SandboxError("Only the virtual LLMDesignedMethod base is allowed")
    methods = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
    if not {"solve", "plan_grid"} <= methods.keys():
        raise SandboxError("Both solve and plan_grid must be implemented")
    if len(methods) != sum(isinstance(node, ast.FunctionDef) for node in cls.body):
        raise SandboxError("Duplicate policy method")
    for name, node in methods.items():
        if not node.args.args or node.args.args[0].arg != "self":
            raise SandboxError("Policy methods must take self")
        # Fixed within an episode. Only initialization can write beta/config.
        if name != "__init__":
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.Attribute)
                    and isinstance(item.ctx, ast.Store)
                    and item.attr in {"beta", "config"}
                ):
                    raise SandboxError("beta/config are fixed within an episode")
        node.name = "policy" + name
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
    body = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            allowed = _IMPORTS.get(node.module or "", set())
            if node.level or any(
                alias.name not in allowed or alias.asname for alias in node.names
            ):
                raise SandboxError("Only declared virtual Appendix API imports are supported")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    body.append(_Lower(methods).visit(child))
                elif isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant):
                    pass
                else:
                    raise SandboxError("Policy class may contain methods and a docstring only")
        else:
            body.append(node)
    body.extend(ast.parse("def decide(view):\n    return view\n").body)
    lowered = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
    text = ast.unparse(lowered)
    PolicySandbox().validate(text)
    return text, "__init__" in methods


class _AppendixInterpreter(_Interpreter):
    def __init__(self, limits, timeout, question=None):
        super().__init__(limits, timeout)
        self.question = question

    def expr(self, node):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == self.math_alias:
                return super().expr(node)
            if isinstance(node.value, ast.Name) and node.value.id == "question":
                if node.attr not in {"baseline_score", "max_parallelism"} or self.question is None:
                    raise SandboxError("Only prefix-safe question attributes are readable")
                return self.checked(getattr(self.question, node.attr))
            # JSON records support field syntax, never Python object attributes.
            if not node.attr.startswith("_"):
                value = self.expr(node.value)
                if type(value) is dict and node.attr in value:
                    return value[node.attr]
        return super().expr(node)

    def call(self, node):
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "question"
        ):
            if self.question is None:
                raise SandboxError("plan_grid cannot inspect an episode")
            if fn.attr not in {
                "reset",
                "observed",
                "legal_actions",
                "legal_roots",
                "opened_branches",
                "meta",
                "probe_batch",
            }:
                raise SandboxError("Undeclared question capability")
            args = [self.expr(arg) for arg in node.args]
            kwargs = {}
            for keyword in node.keywords:
                if keyword.arg != "on_reveal" or fn.attr != "probe_batch" or kwargs:
                    raise SandboxError("Unsupported question keyword")
                callback = keyword.value
                if not isinstance(callback, ast.Lambda) or len(callback.args.args) != 1:
                    raise SandboxError("on_reveal must be a one-argument lambda")
                closure = dict(self.env)

                def reveal(obs, closure=closure, callback=callback):
                    previous = self.env
                    self.env = {**closure, callback.args.args[0].arg: self.checked(asdict(obs))}
                    try:
                        self.expr(callback.body)
                    finally:
                        self.env = previous

                kwargs["on_reveal"] = reveal
            value = getattr(self.question, fn.attr)(*args, **kwargs)
            if fn.attr == "observed":
                value = {cid: asdict(obs) for cid, obs in value.items()}
            elif fn.attr == "meta":
                value = asdict(value)
            elif fn.attr == "probe_batch":
                value = [asdict(obs) for obs in value]
            return self.checked(value)
        if isinstance(fn, ast.Name) and fn.id in _API | _SIGNALS:
            args = [self.expr(arg) for arg in node.args]
            if any(k.arg is None for k in node.keywords):
                raise SandboxError("Keyword unpacking is unavailable")
            kwargs = {k.arg: self.expr(k.value) for k in node.keywords}
            if fn.id == "GridPlan":
                return self.checked(asdict(GridPlan(*args, **kwargs)))
            if fn.id == "SimResult":
                if args or kwargs:
                    raise SandboxError("SimResult takes no arguments")
                return {"curve": []}
            if fn.id in _SIGNALS:
                if kwargs or len(args) != 1:
                    raise SandboxError("Observation helpers take one argument")
                value = (
                    [Observation(**row) for row in args[0]]
                    if fn.id == "trajectory_signal"
                    else Observation(**args[0])
                )
                return self.checked(getattr(observation_signal, fn.id)(value))
            if self.question is None:
                raise SandboxError("Episode helpers unavailable during planning")
            if fn.id == "_budget_done":
                return args[1] is not None and self.question.budget_spent >= args[1]
            if fn.id == "_record_curve":
                args[0]["curve"] = self.checked(asdict(finalize_result(self.question))["curve"])
                return None
            if fn.id == "finalize_result":
                return self.checked(asdict(finalize_result(self.question)))
            raise SandboxError("Unsupported virtual API call")
        return super().call(node)


class AppendixSourcePolicy(LLMDesignedMethod):
    """Model-written solve/plan_grid interpreted with only declared question capabilities."""

    def __init__(
        self, artifact: PolicyArtifact, config=None, *, sandbox=None, timeout_s: float = 5
    ):
        super().__init__(config)
        self.artifact = artifact
        self.sandbox = sandbox or PolicySandbox()
        if type(self.sandbox) is not PolicySandbox:
            raise SandboxError(
                "Appendix source currently requires the inline PolicySandbox profile"
            )
        self.timeout_s = timeout_s
        self._lowered, self._has_init = lower_source(artifact.source)
        self.sandbox.validate(self._lowered)
        engine = _AppendixInterpreter(self.sandbox, self.timeout_s)
        engine.run(self._lowered, {})
        state = self._initialize(engine)
        self.beta = state["beta"]

    def _initialize(self, engine):
        state = {"config": copy.deepcopy(self.config), "beta": self.beta}
        if self._has_init:
            engine.call_function("policy__init__", [state], {})
        # A supplied sweep beta overrides the baked-in constructor default.
        if "beta" in self.config and state.get("beta") != self.beta:
            raise SandboxError("Constructor must honor config beta")
        beta = state.get("beta")
        if not isinstance(beta, (float, int)) or isinstance(beta, bool) or not 0 <= beta <= 1:
            raise SandboxError("Invalid initialized beta")
        return state

    def _execute(self, method, argument, question=None, budget=None):
        engine = _AppendixInterpreter(self.sandbox, self.timeout_s, question)
        engine.run(self._lowered, {})
        state = self._initialize(engine)
        beta = state["beta"]
        args = [state, engine.checked(argument)]
        if method == "solve":
            args.append(budget)
        try:
            value = engine.call_function("policy" + method, args, {})
            if state.get("beta") != beta:
                raise SandboxError("beta changed inside the episode")
            return value
        except Exception as exc:
            raise SandboxError(f"Appendix {method}: {type(exc).__name__}: {exc}") from exc

    def plan_grid(self, context):
        value = self._execute("plan_grid", asdict(context))
        if type(value) is not dict:
            raise SandboxError("plan_grid must return GridPlan on every path")
        return context.validate(GridPlan(**value))

    def solve(self, question, budget=None):
        question.set_probe_budget(budget)
        value = self._execute("solve", None, question, budget)
        if type(value) is not dict:
            raise SandboxError("solve must return finalize_result(question, result)")
        return finalize_result(question)

    def to_dict(self):
        return {
            "kind": "appendix-source-v1",
            "artifact": self.artifact.to_dict(),
            "config": copy.deepcopy(self.config),
            "timeout_s": self.timeout_s,
            "sandbox": self.sandbox.capabilities(),
        }

    @classmethod
    def from_dict(cls, data, sandbox=None):
        sandbox = sandbox or PolicySandbox()
        if data.get("kind") != "appendix-source-v1" or data["sandbox"] != sandbox.capabilities():
            raise SandboxError("Appendix source requires its recorded sandbox profile")
        return cls(
            PolicyArtifact.from_dict(data["artifact"]),
            data["config"],
            sandbox=sandbox,
            timeout_s=data["timeout_s"],
        )
