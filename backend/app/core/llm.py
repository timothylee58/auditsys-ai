"""Thin chat-completion helper for the audit-grade pipeline.

Agent code depends on the ``ChatFn`` callable, not on a client, so every
stage (claim generation, grading, rewriting, verification) can be tested
with a stub and swapped for a different provider without touching logic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from openai import AsyncAzureOpenAI

from app.core.settings import settings

# messages -> raw model text (JSON when the stage asked for it)
ChatFn = Callable[[list[dict[str, str]]], Awaitable[str]]


def make_chat_fn(
    deployment: str | None,
    *,
    json_mode: bool = True,
    max_tokens: int = 1500,
) -> ChatFn:
    """Build a ``ChatFn`` bound to an Azure OpenAI deployment.

    The client is created lazily on first use so importing this module (and
    building the agent graph at startup) never needs credentials.
    """
    client: AsyncAzureOpenAI | None = None

    async def chat(messages: list[dict[str, str]]) -> str:
        nonlocal client
        if client is None:
            client = AsyncAzureOpenAI(
                api_key=settings.azure_openai_api_key,
                azure_endpoint=settings.azure_openai_endpoint or "",
                api_version=settings.azure_openai_api_version,
            )
        kwargs: dict = {
            "model": deployment,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    return chat


def main_chat_fn(**kwargs) -> ChatFn:
    """Chat function on the main answer-generation deployment."""
    return make_chat_fn(settings.azure_openai_deployment, **kwargs)


def verifier_chat_fn(**kwargs) -> ChatFn:
    """Chat function on the (smaller) verifier deployment, falling back to the main one."""
    return make_chat_fn(
        settings.azure_openai_verifier_deployment or settings.azure_openai_deployment, **kwargs
    )
