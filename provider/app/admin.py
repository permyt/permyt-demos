from django.contrib.admin import *  # pylint: disable=wildcard-import,unused-wildcard-import
from app.mixins.admin import *  # pylint: disable=wildcard-import,unused-wildcard-import


def get_app_list(self, request, app_label=None):
    """
    GET the list of apps to be displayed in the admin page.

    The idea is to be able to select where we want an app to be displayed.
    If the app doesn't have a specific indication, it will be displayed on its own place.
    """
    apps_data = self._build_app_dict(request, app_label)
    for app_name, app_data in apps_data.items():
        for model in app_data["models"]:
            admin_class = site._registry.get(model["model"])
            if not admin_class:
                continue
            target_app = getattr(admin_class, "target_app", None) or app_name
            apps_data[target_app].setdefault("new_models", []).append(model)

    # Order apps and models, and remove apps without models
    app_dict = {}
    app_list = []
    for app_name, app_data in sorted(apps_data.items(), key=lambda x: x[0]):
        if not app_data.get("new_models"):
            continue
        app_dict[app_name] = app_data
        app_dict[app_name]["models"] = sorted(app_data["new_models"], key=lambda x: x["name"])
        app_list.append(app_data)
    return app_list


AdminSite.get_app_list = get_app_list
