"""
The following models are used to test if decorators (pre and post signals) are
working as intended. They cannot be tested outside of a Model context and, because
of that, this models exists to be populated only during tests.
"""

from __future__ import annotations


from app import models
from app.utils.decorators import (
    on_pre_save,
    on_post_save,
    on_post_save_background,
    on_pre_delete,
    on_post_delete,
    on_post_delete_background,
)


class AbstractTstModel(models.AppModel):
    """
    Abstract class that contains the main fields and methods to preform the unittests
    """

    data = models.JSONField(default=dict)
    message = models.CharField(max_length=256, null=True)

    class Meta:
        abstract = True

    @classmethod
    def _generate_message(cls, action):
        """Generates a message with a combination of actions and classname"""
        return f"{action}_{cls.classname()}"

    @classmethod
    def _emit_save(
        cls,
        objects: list[TstMessage],
        fields: set[str],
        created: bool = False,
        action: str = None,
        priority: int = None,
        **kwargs,
    ):
        """Generates a message with the data and state from a save event"""
        TstMessage.objects.create(
            message=cls._generate_message(action),
            data={
                "action": action,
                "objects": [obj.id for obj in objects],
                "fields": fields,
                "created": created,
                "priority": priority,
                "class": cls.classname(),
            },
        )

    @classmethod
    def _emit_delete(
        cls,
        objects: list[TstMessage],
        action: str = None,
        priority: int = None,
        **kwargs,
    ):
        """Generates a message with the data and state from a delete event"""
        TstMessage.objects.create(
            message=cls._generate_message(action),
            data={
                "action": action,
                "objects": objects,
                "priority": priority,
                "class": cls.__name__,
            },
        )


class TstMessage(AbstractTstModel):
    """
    Model where tests message will be saved (to track events)

    The reason this is made like this is because it isn't possible to check if
    a function or signal have been executed. The solution found is to write
    a message from the event itself with its data and status.
    """


class TstModelA(AbstractTstModel):
    """
    A model to tests the execution of decorators.
    It tests if the decorator is executed and if priority (order) is correct.
    """

    # -----------------------------------------------------------------------
    # Receive own pre save
    # -----------------------------------------------------------------------

    @on_pre_save()
    def pre_save_100(cls, *args, **kwargs):
        """Method to test pre save with priority 100"""
        cls._emit_save(*args, action="pre_save", priority=100, **kwargs)

    @on_pre_save(priority=10)
    def pre_save_10(cls, *args, **kwargs):
        """Method to test pre save with priority 10"""
        cls._emit_save(*args, action="pre_save", priority=10, **kwargs)

    @on_pre_save(priority=1000)
    def pre_save_1000(cls, *args, **kwargs):
        """Method to test pre save with priority 1000"""
        cls._emit_save(*args, action="pre_save", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive own post save
    # -----------------------------------------------------------------------

    @on_post_save()
    def post_save_100(cls, *args, **kwargs):
        """Method to test post save with priority 100"""
        cls._emit_save(*args, action="post_save", priority=100, **kwargs)

    @on_post_save(priority=10)
    def post_save_10(cls, *args, **kwargs):
        """Method to test post save with priority 10"""
        cls._emit_save(*args, action="post_save", priority=10, **kwargs)

    @on_post_save(priority=1000)
    def post_save_1000(cls, *args, **kwargs):
        """Method to test post save with priority 1000"""
        cls._emit_save(*args, action="post_save", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive own post save background
    # -----------------------------------------------------------------------

    @on_post_save_background()
    def post_save_bg_100(cls, *args, **kwargs):
        """Method to test post save background with priority 100"""
        cls._emit_save(*args, action="post_save_bg", priority=100, **kwargs)

    @on_post_save_background(priority=10)
    def post_save_bg_10(cls, *args, **kwargs):
        """Method to test post save background with priority 10"""
        cls._emit_save(*args, action="post_save_bg", priority=10, **kwargs)

    @on_post_save_background(priority=1000)
    def post_save_bg_1000(cls, *args, **kwargs):
        """Method to test post save background with priority 1000"""
        cls._emit_save(*args, action="post_save_bg", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive own pre delete
    # -----------------------------------------------------------------------

    @on_pre_delete()
    def pre_delete_100(cls, *args, **kwargs):
        """Method to test pre delete with priority 100"""
        cls._emit_delete(*args, action="pre_delete", priority=100, **kwargs)

    @on_pre_delete(priority=10)
    def pre_delete_10(cls, *args, **kwargs):
        """Method to test pre delete with priority 10"""
        cls._emit_delete(*args, action="pre_delete", priority=10, **kwargs)

    @on_pre_delete(priority=1000)
    def pre_delete_1000(cls, *args, **kwargs):
        """Method to test pre delete with priority 1000"""
        cls._emit_delete(*args, action="pre_delete", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive own post delete
    # -----------------------------------------------------------------------

    @on_post_delete()
    def post_delete_100(cls, *args, **kwargs):
        """Method to test post delete with priority 100"""
        cls._emit_delete(*args, action="post_delete", priority=100, **kwargs)

    @on_post_delete(priority=10)
    def post_delete_10(cls, *args, **kwargs):
        """Method to test post delete with priority 10"""
        cls._emit_delete(*args, action="post_delete", priority=10, **kwargs)

    @on_post_delete(priority=1000)
    def post_delete_1000(cls, *args, **kwargs):
        """Method to test post delete with priority 1000"""
        cls._emit_delete(*args, action="post_delete", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive own post delete background
    # -----------------------------------------------------------------------

    @on_post_delete_background()
    def post_delete_bg_100(cls, *args, **kwargs):
        """Method to test post delete background with priority 100"""
        cls._emit_delete(*args, action="post_delete_bg", priority=100, **kwargs)

    @on_post_delete_background(priority=10)
    def post_delete_bg_10(cls, *args, **kwargs):
        """Method to test post delete background with priority 10"""
        cls._emit_delete(*args, action="post_delete_bg", priority=10, **kwargs)

    @on_post_delete_background(priority=1000)
    def post_delete_bg_1000(cls, *args, **kwargs):
        """Method to test post delete background with priority 1000"""
        cls._emit_delete(*args, action="post_delete_bg", priority=1000, **kwargs)


class TstModelB(AbstractTstModel):
    """
    A model to tests the execution of decorators.
    It tests if the decorator is executed and if priority (order) is correct
    when operations are performed in a different model.
    """

    # -----------------------------------------------------------------------
    # Receive TstModelA pre save
    # -----------------------------------------------------------------------

    @on_pre_save(model=TstModelA)
    def pre_save_100(cls, *args, **kwargs):
        """Method to test pre save with priority 100"""
        cls._emit_save(*args, action="pre_save", priority=100, **kwargs)

    @on_pre_save(model=TstModelA, priority=10)
    def pre_save_10(cls, *args, **kwargs):
        """Method to test pre save with priority 10"""
        cls._emit_save(*args, action="pre_save", priority=10, **kwargs)

    @on_pre_save(model=TstModelA, priority=1000)
    def pre_save_1000(cls, *args, **kwargs):
        """Method to test pre save with priority 1000"""
        cls._emit_save(*args, action="pre_save", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive TstModelA post save
    # -----------------------------------------------------------------------

    @on_post_save(model=TstModelA)
    def post_save_100(cls, *args, **kwargs):
        """Method to test post save with priority 100"""
        cls._emit_save(*args, action="post_save", priority=100, **kwargs)

    @on_post_save(model=TstModelA, priority=10)
    def post_save_10(cls, *args, **kwargs):
        """Method to test post save with priority 10"""
        cls._emit_save(*args, action="post_save", priority=10, **kwargs)

    @on_post_save(model=TstModelA, priority=1000)
    def post_save_1000(cls, *args, **kwargs):
        """Method to test post save with priority 1000"""
        cls._emit_save(*args, action="post_save", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive TstModelA post save background
    # -----------------------------------------------------------------------

    @on_post_save_background(model=TstModelA)
    def post_save_bg_100(cls, *args, **kwargs):
        """Method to test post save background with priority 100"""
        cls._emit_save(*args, action="post_save_bg", priority=100, **kwargs)

    @on_post_save_background(model=TstModelA, priority=10)
    def post_save_bg_10(cls, *args, **kwargs):
        """Method to test post save background with priority 10"""
        cls._emit_save(*args, action="post_save_bg", priority=10, **kwargs)

    @on_post_save_background(model=TstModelA, priority=1000)
    def post_save_bg_1000(cls, *args, **kwargs):
        """Method to test post save background with priority 1000"""
        cls._emit_save(*args, action="post_save_bg", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive TstModelA pre delete
    # -----------------------------------------------------------------------

    @on_pre_delete(model=TstModelA)
    def pre_delete_100(cls, *args, **kwargs):
        """Method to test pre delete with priority 100"""
        cls._emit_delete(*args, action="pre_delete", priority=100, **kwargs)

    @on_pre_delete(model=TstModelA, priority=10)
    def pre_delete_10(cls, *args, **kwargs):
        """Method to test pre delete with priority 10"""
        cls._emit_delete(*args, action="pre_delete", priority=10, **kwargs)

    @on_pre_delete(model=TstModelA, priority=1000)
    def pre_delete_1000(cls, *args, **kwargs):
        """Method to test pre delete with priority 1000"""
        cls._emit_delete(*args, action="pre_delete", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive TstModelA post delete
    # -----------------------------------------------------------------------

    @on_post_delete(model=TstModelA)
    def post_delete_100(cls, *args, **kwargs):
        """Method to test post delete with priority 100"""
        cls._emit_delete(*args, action="post_delete", priority=100, **kwargs)

    @on_post_delete(model=TstModelA, priority=10)
    def post_delete_10(cls, *args, **kwargs):
        """Method to test post delete with priority 10"""
        cls._emit_delete(*args, action="post_delete", priority=10, **kwargs)

    @on_post_delete(model=TstModelA, priority=1000)
    def post_delete_1000(cls, *args, **kwargs):
        """Method to test post delete with priority 1000"""
        cls._emit_delete(*args, action="post_delete", priority=1000, **kwargs)

    # -----------------------------------------------------------------------
    # Receive TstModelA post delete background
    # -----------------------------------------------------------------------

    @on_post_delete_background(model=TstModelA)
    def post_delete_bg_100(cls, *args, **kwargs):
        """Method to test post delete background with priority 100"""
        cls._emit_delete(*args, action="post_delete_bg", priority=100, **kwargs)

    @on_post_delete_background(model=TstModelA, priority=10)
    def post_delete_bg_10(cls, *args, **kwargs):
        """Method to test post delete background with priority 10"""
        cls._emit_delete(*args, action="post_delete_bg", priority=10, **kwargs)

    @on_post_delete_background(model=TstModelA, priority=1000)
    def post_delete_bg_1000(cls, *args, **kwargs):
        """Method to test post delete background with priority 1000"""
        cls._emit_delete(*args, action="post_delete_bg", priority=1000, **kwargs)
