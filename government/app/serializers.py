"""
This file is used to replace the default rest_framework serializers.

It imports the default rest_framework serializers and overrides it with custom fields and serializers.


It should be used like this:
```
from app import serializers

class MySerializer(serializers.AppModelSerializer):
    name = serializers.IDField()
    description = serializers.CharField(max_length=256)
    ...

```
"""

# pylint: disable=wildcard-import,unused-wildcard-import,unused-import
from rest_framework.serializers import *
from app.mixins.serializers import *
from app.utils.serializers import *
