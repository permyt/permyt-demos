from pathlib import Path
from typing import Any, TypeAlias

from django.db.models import TextChoices

SERVICES_PATH = Path(__file__).parent

AIModelType: TypeAlias = str
AIMessages: TypeAlias = list[dict[str, str]]
AIResponse: TypeAlias = dict[str, Any] | list[Any]


class Provider(TextChoices):
    ANTHROPIC = "anthropic", "Anthropic"


class AIModel(TextChoices):
    CLAUDE_SONNET = "claude-sonnet-4-6", "Claude Sonnet"
    CLAUDE_HAIKU = "claude-haiku-4-5", "Claude Haiku"


AI_MODELS_SETTINGS = {
    AIModel.CLAUDE_SONNET: {"provider": Provider.ANTHROPIC, "max_tokens": 8192},
    AIModel.CLAUDE_HAIKU: {"provider": Provider.ANTHROPIC, "max_tokens": 4096},
}
