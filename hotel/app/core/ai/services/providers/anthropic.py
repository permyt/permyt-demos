"""Anthropic provider — mirrors broker pattern, Claude-only."""

from typing import Any

from anthropic import Anthropic, AnthropicError

from ..settings import Provider
from .base import AIClient

__all__ = ("AnthropicClient",)


class AnthropicClient(AIClient):
    PROVIDER = Provider.ANTHROPIC
    SETTINGS_KEY_ATTRIBUTE = "ANTHROPIC_API_KEY"
    CLIENT_EXCEPTIONS = (AnthropicError,)

    def _get_client(self):
        return Anthropic(api_key=self._get_api_key())

    def make_request(
        self,
        system_prompt: list[str],
        messages: list[dict[str, str]],
        is_json: bool = True,
        tries: int = 1,
    ) -> Any:
        response = self._request(
            self.client.messages.create,
            model=self.model,
            max_tokens=self._get_api_max_tokens(),
            system=[{"type": "text", "text": msg} for msg in system_prompt],
            messages=messages,
        )

        content = None
        if response and getattr(response, "content", None):
            content = response.content[0].text

        return self._validate_response(
            content, system_prompt, messages, is_json=is_json, tries=tries
        )
