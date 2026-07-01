import pytest
import subprocess

from django.conf import settings

from app.common.unittests.models import AbstractTstModel, TstMessage, TstModelA, TstModelB
from app.core.users.factories import User, UserFactory
from app.utils.middleware import SetCurrentUser


@pytest.mark.django_db(databases="__all__")
class TestAppModel:
    """
    This will test if the AppModel, are working as expected for individual and bulk
    actions, including the decorators that receives pre and post save/delete events.
    """

    ORDER = [10, 100, 1000]

    def _get_objects(self, model: AbstractTstModel, action: str):
        message = model._generate_message(action)
        return TstMessage.objects.filter(message=message).order_by("created_at")

    def _check_messages(
        self,
        model: AbstractTstModel,
        action: str,
        fields: set[str] = None,
        created: bool = None,
        user: User = None,
    ):
        tms = self._get_objects(model, action)
        assert len(tms) == 3, f"""
            It should have been created 3 messages from class
            `{model.classname()}` for action `{action}` (created={created}).
            """

        for i, tm in enumerate(tms):
            assert tm.data["action"] == action
            assert (
                tm.data["priority"] == self.ORDER[i]
            ), f"Wrong order for class `{model.classname()}` for action `{action}`."

            # Check if list of changed fields are correct
            if fields is not None:
                assert set(tm.data["fields"]) == set(fields)

            # Check if created is passed correctly
            if created is not None:
                assert tm.data["created"] == created

            # Check if user are recorded correctly for the messages
            # specially for background tasks
            if user is not None:
                assert tm.created_by_id == user.pk
                assert tm.updated_by_id == user.pk

    def _delete_messages(self):
        TstMessage.objects.all().delete()

    def test_create_update_and_delete_behaviors(self):
        """
        Connected with the TstModel, TstModelA and TstModelB definitions,
        when creating, updating and deleting objects from TstModelA,
        six TstModel messages should be create per action, three from
        TstModelA itself and other three from TstModelB.
        """

        user1 = UserFactory()
        user2 = UserFactory()

        # ---------------------------------------------------------------------
        # 1) Test individual creation
        # ---------------------------------------------------------------------

        with SetCurrentUser(user1):
            tsa = TstModelA.objects.create(message="Individual create")

        # Check if created_by and updated_by are updated correctly
        assert tsa.created_by_id == user1.pk
        assert tsa.updated_by_id == user1.pk

        # Check if own messages when object is created and order is correct
        self._check_messages(TstModelA, "pre_save", fields=[], created=True, user=user1)
        self._check_messages(TstModelA, "post_save", fields=[], created=True, user=user1)
        self._check_messages(TstModelA, "post_save_bg", fields=[], created=True, user=user1)

        # Check if TstModelB messages when object is created and order is correct
        self._check_messages(TstModelB, "pre_save", fields=[], created=True, user=user1)
        self._check_messages(TstModelB, "post_save", fields=[], created=True, user=user1)
        self._check_messages(TstModelB, "post_save_bg", fields=[], created=True, user=user1)

        self._delete_messages()

        # ---------------------------------------------------------------------
        # 2) Test individual update
        # ---------------------------------------------------------------------

        with SetCurrentUser(user2):
            tsa.message = "Individual update"
            tsa.save()

        # Check if created_by and updated_by are updated correctly
        assert tsa.created_by_id == user1.pk
        assert tsa.updated_by_id == user2.pk

        # Check if own messages when object is created and order is correct
        self._check_messages(TstModelA, "pre_save", fields=["message"], created=False, user=user2)
        self._check_messages(TstModelA, "post_save", fields=["message"], created=False, user=user2)
        self._check_messages(
            TstModelA, "post_save_bg", fields=["message"], created=False, user=user2
        )

        # Check if TstModelB messages when object is created and order is correct
        self._check_messages(TstModelB, "pre_save", fields=["message"], created=False, user=user2)
        self._check_messages(TstModelB, "post_save", fields=["message"], created=False, user=user2)
        self._check_messages(
            TstModelB, "post_save_bg", fields=["message"], created=False, user=user2
        )

        self._delete_messages()

        # ---------------------------------------------------------------------
        # 3) Test individual delete
        # ---------------------------------------------------------------------

        with SetCurrentUser(user1):
            tsa.delete()

        # Check if own messages when object is created and order is correct
        self._check_messages(TstModelA, "pre_delete", user=user1)
        self._check_messages(TstModelA, "post_delete", user=user1)
        self._check_messages(TstModelA, "post_delete_bg", user=user1)

        # Check if TstModelB messages when object is created and order is correct
        self._check_messages(TstModelB, "pre_delete", user=user1)
        self._check_messages(TstModelB, "post_delete", user=user1)
        self._check_messages(TstModelB, "post_delete_bg", user=user1)

        self._delete_messages()

        # ---------------------------------------------------------------------
        # 4) Test bulk creation
        # ---------------------------------------------------------------------

        with SetCurrentUser(user2):
            (tsa,) = TstModelA.bulk_create([TstModelA(message="Bulk create")])

        # Check if created_by and updated_by are updated correctly
        assert tsa.created_by_id == user2.pk
        assert tsa.updated_by_id == user2.pk

        # Check if own messages when object is created and order is correct
        self._check_messages(TstModelA, "pre_save", fields=[], created=True, user=user2)
        self._check_messages(TstModelA, "post_save", fields=[], created=True, user=user2)
        self._check_messages(TstModelA, "post_save_bg", fields=[], created=True, user=user2)

        # Check if TstModelB messages when object is created and order is correct
        self._check_messages(TstModelB, "pre_save", fields=[], created=True, user=user2)
        self._check_messages(TstModelB, "post_save", fields=[], created=True, user=user2)
        self._check_messages(TstModelB, "post_save_bg", fields=[], created=True, user=user2)

        self._delete_messages()

        # ---------------------------------------------------------------------
        # 5) Test bulk update
        # ---------------------------------------------------------------------

        with SetCurrentUser(user1):
            tsa.message = "Bulk update"
            TstModelA.bulk_update([tsa], ["message"])

        # Check if created_by and updated_by are updated correctly
        assert tsa.created_by_id == user2.pk
        assert tsa.updated_by_id == user1.pk

        # Check if own messages when object is created and order is correct
        self._check_messages(TstModelA, "pre_save", fields=["message"], created=False, user=user1)
        self._check_messages(TstModelA, "post_save", fields=["message"], created=False, user=user1)
        self._check_messages(
            TstModelA, "post_save_bg", fields=["message"], created=False, user=user1
        )

        # Check if TstModelB messages when object is created and order is correct
        self._check_messages(TstModelB, "pre_save", fields=["message"], created=False, user=user1)
        self._check_messages(TstModelB, "post_save", fields=["message"], created=False, user=user1)
        self._check_messages(
            TstModelB, "post_save_bg", fields=["message"], created=False, user=user1
        )

        self._delete_messages()

        # ---------------------------------------------------------------------
        # 6) Test bulk delete
        # ---------------------------------------------------------------------

        with SetCurrentUser(user2):
            TstModelA.bulk_delete([tsa])

        # Check if own messages when object is created and order is correct
        self._check_messages(TstModelA, "pre_delete", user=user2)
        self._check_messages(TstModelA, "post_delete", user=user2)
        self._check_messages(TstModelA, "post_delete_bg", user=user2)

        # Check if TstModelB messages when object is created and order is correct
        self._check_messages(TstModelB, "pre_delete", user=user2)
        self._check_messages(TstModelB, "post_delete", user=user2)
        self._check_messages(TstModelB, "post_delete_bg", user=user2)

        self._delete_messages()


@pytest.mark.code
class TestCode:
    """
    Test if code passes pylint and black
    """

    def _check(self, args: list[str | int], error_message: str = None):
        """
        Run a check and raises and AssertionError if it fails.

        :param args: List of arguments composing the command to be executed
        :param error_message: Custom message when check fails. Defaults to CalledProcessError msg.
        """
        try:
            subprocess.run(args, check=True)
        except subprocess.CalledProcessError as exc:
            raise AssertionError(error_message or str(exc)) from exc

    def test_black(self):
        """
        Test if code passes black checks
        """
        self._check(
            ["black", "--check", settings.BASE_DIR / "app"],
            error_message="Black checks failed. Some code should be reformated.",
        )

    def test_pylint(self):
        """
        Test if code passes pylint checks
        """
        self._check(
            ["pylint", settings.BASE_DIR / "app"],
            error_message="Pylint checks failed. Some code contain errors.",
        )
