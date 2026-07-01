"""
AIService base — mirrors broker's `app/core/ai/services/base.py`.

Subclasses define a ``PROMPT`` (path to system prompt file under SERVICES_PATH)
and call ``run(prompt)``. Output is parsed as JSON when EXPECT_JSON_RESPONSE is True.
"""

from __future__ import annotations

from .providers import AIClient, AnthropicClient
from .settings import AI_MODELS_SETTINGS, SERVICES_PATH, AIModel, AIResponse, Provider

__all__ = ("AIService",)


class AIService:
    AI_MODELS = AIModel
    DEFAULT_MODEL = AIModel.CLAUDE_HAIKU
    CLIENTS = {
        Provider.ANTHROPIC: AnthropicClient,
    }

    PROMPT: list[str] | str = None

    EXPECT_JSON_RESPONSE = True
    RAISE_ERROR_ON_EMPTY_RESPONSE = True

    EXPECTED_LIST = False
    EXPECTED_ARGS: tuple[str, ...] = ()

    def __init__(self, client: AIClient = None, **kwargs):
        super().__init__(**kwargs)
        self.client = client or self._get_client()

    def run(self, prompt: str, **kwargs) -> AIResponse:
        self._pre_processing(**kwargs)

        system_prompt = self._get_system_prompt() + self._get_custom_system_prompt()
        messages = [*kwargs.get("messages", []), *self._get_user_prompt(prompt)]
        content = self.client.make_request(
            system_prompt=system_prompt,
            messages=messages,
            is_json=self.EXPECT_JSON_RESPONSE,
        )

        if self.EXPECTED_LIST and isinstance(content, dict):
            expected = tuple(self.EXPECTED_ARGS or ())
            if expected and any(key in content for key in expected):
                content = [content]
            else:
                content = list(content.values())[0] if content else []

        if content is None and self.RAISE_ERROR_ON_EMPTY_RESPONSE:
            return None

        return self._post_processing(content, messages=messages, **kwargs)

    def _get_custom_system_prompt(self) -> list[str]:
        return []

    def _get_user_prompt(self, prompt: str) -> list[dict[str, str]]:
        return [{"role": "user", "content": prompt}]

    def _pre_processing(self, **kwargs) -> None:
        pass

    def _post_processing(self, content: AIResponse, **kwargs) -> AIResponse:
        return content

    def _get_client(self) -> AIClient:
        model_settings = AI_MODELS_SETTINGS[self.DEFAULT_MODEL]
        client_class = self.CLIENTS.get(model_settings["provider"])
        if not client_class:
            raise ValueError(f"Provider for {self.DEFAULT_MODEL} is not supported")
        return client_class(model=self.DEFAULT_MODEL)

    def _get_system_prompt(self) -> list[str]:
        if self.PROMPT is None:
            raise NotImplementedError("Subclasses must define a PROMPT")
        urls: tuple[str, ...] = (
            (self.PROMPT,) if isinstance(self.PROMPT, str) else tuple(self.PROMPT)
        )
        prompts = []
        for relative_url in urls:
            prompt_file = SERVICES_PATH / relative_url
            if not prompt_file.exists():
                raise ValueError(f"Prompt file '{relative_url}' not found.")
            prompts.append(prompt_file.read_text())
        return prompts

    def run_service(self, service: type, **kwargs) -> AIResponse:
        return service(client=self.client).run(**kwargs)
