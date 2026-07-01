from typing import Any

from app.core.users.models import User

__all__ = ("AppTestClient",)


class AppTestClient:
    """
    Allows to execute calls to API with extra checks.

    This is specially useful to check if user should have permissions to
    call specific endpoints, and if viewset is not generating to many db touches.

    The correct way to use is:
    ```
    with AppTestClient(locals(), user=some_optional_user) as tc:
        tc.get(some_url, expected_codes=[400])
        ....
    ```
    """

    ACCEPTED = (200, 201, 202, 203, 204, 205)
    DECLINED = (400, 401, 402, 403, 404, 405)

    def __init__(self, test_locals: dict[str, Any], user: User = None):
        """
        Initialize the with handler with test_locals and a specific user.

        ```
        with AppTestClient(locals(), user=some_optional_user) as tc:
        tc.get(some_url, expected_codes=[400])
            ....
        ```

        :param user: User to be used when calling .
        :type user: User|UUID|str | None
        """
        # Check if client  have been added to test_locals
        self.client = test_locals.get("client")
        assert self.client, "client should an argument of the test"

        # Check if django_assert_max_num_queries have been added to test_locals
        self.django_assert_max_num_queries = test_locals.get("django_assert_max_num_queries")
        assert self.django_assert_max_num_queries, "client should an argument of the test"

        # Defines user that is executing the calls
        self.user = user
        self.user_type = test_locals.get("user_type", (str(user) if user else "Unauthenticated"))

    def __enter__(self):
        """
        Login the user in the client when entering the handler.
        """
        if self.user:
            self.client.force_login(self.user)
        else:
            # Making sure client doesn't have any user attached
            self.client.logout()

        # Return self to be us with `as` statement
        return self

    def __exit__(self, *args, **kwargs):
        """
        Logout the user from the client when exiting the handler.
        """
        self.client.logout()

    def get(self, url, **kwargs):
        """Do a get request to the API client"""
        return self._request("get", url, **kwargs)

    def put(self, url: str, **kwargs):
        """Do a put request to the API client"""
        kwargs.setdefault("data", {})
        return self._request("put", url, **kwargs)

    def post(self, url: str, **kwargs):
        """Do a post request to the API client"""
        kwargs.setdefault("data", {})
        return self._request("post", url, **kwargs)

    def patch(self, url: str, **kwargs):
        """Do a patch request to the API client"""
        kwargs.setdefault("data", {})
        return self._request("patch", url, **kwargs)

    def delete(self, url: str, **kwargs):
        """Do a delete request to the API client"""
        return self._request("delete", url, **kwargs)

    def _request(  # pylint: disable=too-many-positional-arguments
        self,
        method: str,
        url: str,
        expected_codes: list[int] = None,
        max_queries: int = None,
        query_params: dict[str, Any] = None,
        **kwargs,
    ):
        """
        Do a request to the API client.

        :param method: Request method
        :param url: Request url
        :para expected_codes: List of codes that are expected as response status
        :param max_queries: Max of DB queries should be allowed to perform the request
        """

        url = self._get_absolute_url(url)
        if query_params:
            url += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())

        call = getattr(self.client, method)
        expected_codes = expected_codes or self.ACCEPTED
        kwargs.setdefault("content_type", "application/json")

        with self.django_assert_max_num_queries(max_queries or 30):
            response = call(url, **kwargs)

        assert response.status_code in expected_codes, (
            f"Unexpected code received when calling method `{method}` on "
            f"`{url}` with `{self.user_type}`.\n"
            f"{method.upper()}: {url}\n"
            f"DATA: {kwargs.get('data')}\n"
            f"RESPONSE: {getattr(response, 'data', response)}\n"
        )

        return response

    def _get_absolute_url(self, url: str):
        """
        Returns absolute url of the call.
        """
        # Making sure url starts and ends with /
        # No reason to fail the test because of it
        url = url if url.startswith("/") else f"/{url}"
        url = url if url.endswith("/") else f"{url}/"
        return f"/rest{url}"
