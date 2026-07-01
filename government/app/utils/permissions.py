from uuid import UUID

from rest_framework.exceptions import ValidationError


def check_permissions(objects, ids: list[UUID]) -> None:
    """Checks whether objects match IDs and raises a permission Validation error if not."""
    if len(objects) < len(ids):
        valid_set = {obj.id for obj in objects}
        invalid_ids = [_id for _id in ids if _id not in valid_set]
        error_message = (
            "You do not have permission for the following ids: "
            f'{", ".join(str(vid) for vid in invalid_ids)}'
        )
        raise ValidationError(error_message)
