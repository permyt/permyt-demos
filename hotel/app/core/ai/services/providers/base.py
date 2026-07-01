"""
AI client base — mirrors the broker's `app/core/ai/services/providers/base.py`
so the field-mapping service uses the exact same shape as broker scope evaluation.
"""

import logging
from abc import ABC, abstractmethod
from time import sleep
from typing import Any

from django.conf import settings
from json_repair import repair_json

from ..settings import AI_MODELS_SETTINGS

logger = logging.getLogger("console")

__all__ = ("AIClient",)


class AIClient(ABC):
    CLIENT_EXCEPTIONS: tuple = (Exception,)
    SETTINGS_KEY_ATTRIBUTE: str = None
    PROVIDER: str = None

    def __init__(self, model: str, max_tries: int = 1, **kwargs):
        self._max_tries = max_tries
        self.model = model
        self.client = self._get_client()

    @abstractmethod
    def _get_client(self): ...

    def _get_api_key(self):
        return getattr(settings, self.SETTINGS_KEY_ATTRIBUTE or "", None)

    def _get_api_max_tokens(self):
        return AI_MODELS_SETTINGS.get(self.model, {}).get("max_tokens", 4096)

    @abstractmethod
    def make_request(
        self,
        system_prompt: list[str],
        messages: list[dict[str, str]],
        is_json: bool = True,
        tries: int = 1,
    ) -> Any: ...

    def _validate_response(  # pylint: disable=too-many-positional-arguments
        self,
        content: Any,
        system_prompt: list[str],
        messages: list[dict[str, str]],
        is_json: bool,
        tries: int = 1,
    ) -> Any:
        if content is not None:
            if not is_json or isinstance(content, dict | list):
                return content
            if isinstance(content, str):
                parsed = repair_json(content, return_objects=True)
                if parsed is not None:
                    return parsed

        if tries < self._max_tries:
            messages = messages + [
                {"role": "assistant", "content": content or ""},
                {
                    "role": "user",
                    "content": (
                        "The previous response was not a valid JSON object. "
                        "Please provide only a valid JSON object as a response."
                    ),
                },
            ]
            return self.make_request(
                system_prompt=system_prompt,
                messages=messages,
                is_json=is_json,
                tries=tries + 1,
            )
        return None

    def _request(self, request, *args, tries: int = 1, **kwargs):
        try:
            return request(*args, **kwargs)
        except self.CLIENT_EXCEPTIONS as exc:
            logger.error(f"AI provider error: {exc}")
            if tries < self._max_tries:
                sleep(1)
                return self._request(request, *args, tries=tries + 1, **kwargs)
        return None
