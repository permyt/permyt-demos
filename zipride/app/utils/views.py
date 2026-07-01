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
