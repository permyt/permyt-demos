"""Claude-backed answering for the open-ended ``company.ask`` scope.

The company agent answers questions strictly from the company's knowledge base
(``CompanyKB.as_context()``). The requester's question is locked into the grant
at approval time, so the model never sees an unapproved question.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the official data agent for a company. Answer the question using ONLY "
    "the company context provided. Be concise and factual. If the context does not "
    "contain the answer, say so plainly instead of guessing. Never invent figures."
)


def answer_question(context: str, question: str) -> str:
    """Return the agent's answer to ``question`` grounded in ``context``.

    Falls back to the secondary model on a model error, and to a deterministic
    message if no API key is configured (keeps the demo runnable offline).
    """
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning stubbed company.ask answer.")
        return (
            "[stub answer — set ANTHROPIC_API_KEY to enable the live agent]\n\n"
            f"Question: {question}\n\nThe company context on file is:\n{context}"
        )

    try:
        import anthropic  # pylint: disable=import-outside-toplevel
    except ImportError:
        logger.error("anthropic package not installed.")
        return "The company agent is unavailable (anthropic package missing)."

    client = anthropic.Anthropic(api_key=api_key)
    user_content = f"Company context:\n{context}\n\nQuestion: {question}"

    for model in (settings.ANTHROPIC_MODEL, settings.ANTHROPIC_FALLBACK_MODEL):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            return "".join(block.text for block in resp.content if block.type == "text").strip()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(f"company.ask via {model} failed: {exc}")

    return "The company agent could not produce an answer at this time."
