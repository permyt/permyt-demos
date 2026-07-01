"""
This file is used to replace the default django.db.models.

It imports the default django models and overrides it with custom fields and models.
This is important because our fields contains default values, methods and tracking systems.


It should be used like this:
```
from app import models

class MyClass(models.AppModel):
    name = models.NameField()
    description = models.CharField(max_length=256)
    ...

```
"""

from secured_fields.fields import *  # pylint: disable=wildcard-import, unused-wildcard-import
from django.db.models import *  # pylint: disable=wildcard-import, unused-wildcard-import
from app.mixins.models import AppModel  # pylint: disable=unused-import
from app.utils.fields import *  # pylint: disable=wildcard-import, unused-wildcard-import
