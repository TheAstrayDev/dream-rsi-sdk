"""Call integrations without imposing an async-only interface."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def invoke(fn: Any, *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(fn) or inspect.iscoroutinefunction(
        getattr(type(fn), "__call__", None)  # noqa: B004 - inspecting async call, not callability
    ):
        result = fn(*args, **kwargs)
    else:
        result = await asyncio.to_thread(fn, *args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def with_context(fn: Any, candidate: Any, context: Any) -> Any:
    """Inspect the signature; never retry a user call after a TypeError."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return await invoke(fn, candidate)
    try:
        signature.bind(candidate, context=context)
    except TypeError:
        try:
            signature.bind(candidate, context)
        except TypeError:
            return await invoke(fn, candidate)
        return await invoke(fn, candidate, context)
    return await invoke(fn, candidate, context=context)
