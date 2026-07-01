from rest_framework.exceptions import ValidationError


def check_if_permissions_match(objects, ids: list[int]) -> None:
    """
    Checks whether objects match IDs and raises a permission Validation error if they don't.
    """
    if len(objects) < len(ids):
        valid_set = {obj.id for obj in objects}
        invalid_ids = [_id for _id in ids if _id not in valid_set]
        error_message = (
            "You do not have permission for the following ids: "
            f"{', '.join(str(vid) for vid in invalid_ids)}"
        )
        raise ValidationError(error_message)


class FakeRequest:
    """
    Creates a fake request. This is specially used for emulating a request
    for a specific user under background calculations.
    """

    def __init__(self, user=None, method: str = None, **kwargs) -> None:
        self.user = user
        self.method = method or "get"
        for key, value in kwargs.items():
            setattr(self, key, value)

    def build_absolute_uri(self, *args, **kwargs):
        """
        Returns the absolute URI for the given location name.
        """
        return "://"
