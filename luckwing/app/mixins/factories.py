import factory
from factory.django import DjangoModelFactory

from django.contrib.contenttypes.models import ContentType


class ContentTypeModelFactory(DjangoModelFactory):
    """
    Abstract factory that populates `object_id` and `content_type`
    based on a content_object.

    How to use:
    ```
    class MyFactory(ContentTypeModelFactory):
        content_object = factory.SubFactory(OtherObjectFactory)
        ...
    ```
    """

    object_id = factory.SelfAttribute("content_object.id")
    content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.content_object)
    )

    class Meta:
        exclude = ["content_object"]
        abstract = True
