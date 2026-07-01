from django.apps import AppConfig


class appConfig(AppConfig):
    name = "app"
    label = "app"
    verbose_name = "app"
    default = True

    def ready(self):
        """
        The following setup, only can be run after all models being ready
        """
        super().ready()
        self._setup_changes_decorators()

    def _setup_changes_decorators(self):
        """
        Set up change decorators for models.
        """
        # Setup pre and post save/delete decorators
        # They only can be setup after all model being ready
        # pylint: disable=import-outside-toplevel
        from app.utils.decorators import DecoratorReceivers

        DecoratorReceivers.setup()
