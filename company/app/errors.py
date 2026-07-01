from rest_framework.exceptions import ValidationError

__all__ = (
    "ERRORS",
    "get_error_message",
    "raise_error",
    "redirect_error",
)


class ErrorRegistry:  # pylint: disable=too-few-public-methods
    """Registry of error codes with descriptions."""

    def __init__(self, *error_tuples):
        self._descriptions: dict[str, str] = {}
        self._values: set[str] = set()
        for code, name, description in error_tuples:
            self._descriptions[code] = description
            self._values.add(code)
            setattr(self, name, code)

    def __getattr__(self, name: str) -> str:
        raise AttributeError(f"Error code '{name}' not found in ErrorRegistry")

    def get_description(self, code: str) -> str:
        """Return the description of an error code."""
        return self._descriptions[code]

    def get_values(self) -> set[str]:
        """Return the set of valid error codes."""
        return self._values


ERRORS = ErrorRegistry(
    ("ERR_PERM_DENIED", "PERMISSION_DENIED", "You do not have permission to perform this action."),
    ("ERR_NOT_VALIDATED", "DATA_NOT_VALIDATED", "Validate data before performing this action."),
    ("ERR_UNKNOWN", "UNKNOWN_ERROR", "Unknown error occurred."),
)


def get_error_message(code: str, extra_message: str = None) -> str:
    """
    Get the description of an error by its code.
    :param code: Error code to get the description for.
    :return: Description of the error.
    """
    return f"{code}: {ERRORS.get_description(code)}{f' {extra_message}' if extra_message else ''}"


def raise_error(code: str, field: str = None, extra_message: str = None, exc: Exception = None):
    """
    Raise an error with the given code.
    :param code: Error code to raise.
    :param field: Field to associate the error with.
    """
    if code not in ERRORS.get_values():
        code = "ERR_UNKNOWN"

    description = get_error_message(code, extra_message=extra_message)
    message = {field: description} if field else description
    if exc:
        raise ValidationError(message) from exc
    raise ValidationError(message)


def redirect_error(error, *, field: str):
    """
    Redirect an error to a specific field.
    :param error: Error to redirect.
    :param field: Field to associate the error with.
    """
    raise ValidationError({field: error})
