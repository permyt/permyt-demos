"""Hotel mapping service — maps provider responses to hotel form fields."""

from ..base import AIService
from ..settings import AIModel

__all__ = ("HotelMappingService",)


class HotelMappingService(AIService):
    """
    Normalize a list of provider responses (varying field names/shapes) into
    the hotel check-in form's four fields: full_name, address, country, vat.

    The hotel must not assume which provider answered nor what scope names
    were used — this service treats provider data as opaque key-value blobs
    and uses Claude to extract the relevant identity fields.
    """

    PROMPT = "hotel/prompts/mapping.txt"
    DEFAULT_MODEL = AIModel.CLAUDE_HAIKU
    EXPECT_JSON_RESPONSE = True
    EXPECTED_ARGS = ("mapped_fields",)
