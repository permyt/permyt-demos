"""
This file is used to aggregate and run tests for the app package.

It imports and runs all relevant test cases from mixins and core data modules.

Usage:
    pytest app/tests.py
"""

# pylint: disable=wildcard-import,unused-wildcard-import,unused-import
from app.mixins.tests import *
from app.utils.tests import *
