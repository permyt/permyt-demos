from typing import Any, Type

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, SAFE_METHODS
from rest_framework.viewsets import ModelViewSet

from django.db.models import QuerySet

from app.mixins.models import AppModel
from app.serializers import AppModelSerializer
from app.utils.datetime import parse_datetime
from app.utils.permissions import check_permissions


class AppModelViewSet(ModelViewSet):
    """
    AppModelViewSet which all viewsets from DJ models must inherit.
    Contains the routes and methods to list, retrieve, update, create
    and delete objects.
    """

    CAN_CREATE = True
    CAN_DELETE = True

    model: Type[AppModel]

    # If true, use always paginator even if query params is trying to deactivate.
    # This is useful when we know there is huge quantity of data from a viewset
    # and it is not viable to send all data at once.
    force_paginator: bool = False

    # Query params that can be used to filter the queryset
    filter_params: set[str] = set()

    def get_permissions(self):
        is_safe = (
            getattr(self.request, "_is_safe", False)
            or self.request.method in SAFE_METHODS
            or self.action == "ids"
        )
        if is_safe and getattr(self.model.objects, "_allow_guests", False):
            return [AllowAny()]
        return super().get_permissions()

    def get_serializer_class(self) -> Type[AppModelSerializer]:
        """Return model serializer class"""
        return self.model.get_serializer_class()

    def get_serializer(self, *args, **kwargs):
        """Return serializer with data already initialized"""
        kwargs.setdefault("details", self.action != "list")
        kwargs.setdefault("context", self.get_serializer_context())
        return self.get_serializer_class()(*args, **kwargs)

    @property
    def paginator(self):
        """The paginator instance associated with the view, or `None`."""
        if not self.force_paginator:
            use_paginator = self.request.query_params.get("paginator")
            if self.action == "ids" or (use_paginator and use_paginator.lower() in ("0", "false")):
                return None
        return super().paginator

    def get_queryset(self) -> QuerySet:
        """Return objects that user have access based on request method."""

        is_safe = (
            getattr(self.request, "_is_safe", False)
            or self.request.method in SAFE_METHODS
            or self.action == "ids"
        )
        permission = "as_reader" if is_safe else "as_writer"
        queryset = getattr(self.model.objects, permission)(
            self.request.user, **self._get_queryset_kwargs(is_safe=is_safe)
        )

        if self.action in ["list", "ids"]:
            # Get specific ids
            ids = (
                self.request.query_params.get("ids")
                if self.action == "list"
                else self.request.data.get("ids")
            )
            if ids:
                ids = ids.split(",") if isinstance(ids, str) else ids
                queryset = queryset.filter(id__in=ids)

            # Get only data that have been updated from a date
            last_update = parse_datetime(self.request.query_params.get("last_update"))
            if last_update:
                queryset = queryset.filter(updated_at__gte=last_update)

        # Prefetch and select related only can be done on get
        if self.request.method.lower() == "get":
            queryset = self.prefetch_queryset(queryset)

        return queryset

    def _get_queryset_kwargs(self, is_safe: bool = False) -> dict[str, Any]:
        """
        Return additional kwargs for the queryset.
        This can be overridden in subclasses to add custom manager filters.

        E.g. filtering by status of and object based on query params.
        """
        if not is_safe:
            return {}

        as_superuser = self.request.query_params.get("as_superuser")
        return {
            **{
                param: value
                for param, value in self.request.query_params.items()
                if param in self.filter_params
            },
            "as_superuser": as_superuser and as_superuser.lower() in ("1", "true"),
        }

    def prefetch_queryset(self, queryset: QuerySet) -> QuerySet:
        """
        Apply prefetch and select related to the queryset.
        """
        serializer_class = self.get_serializer_class()
        details = self.action != "list"

        # Attach select related to queryset if they exists
        select_related = serializer_class.get_select_related(details=details)
        if select_related:
            queryset = queryset.select_related(*select_related)

        # Attach select related to queryset if they exists
        prefetch_related = serializer_class.get_prefetch_related(details=details)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)

        return queryset

    @action(detail=False, methods=["post"], url_path="ids")
    def ids(self, request: Request, *args, **kwargs) -> Response:
        """Return list of objects, filtered and sorted, to be used in tables"""
        kwargs.setdefault("paginator", False)
        return self.list(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Check permissions to create objects"""
        # Check if user have permissions to create objects
        if not self.CAN_CREATE or not self.model.objects.can_create(request.user):
            raise MethodNotAllowed("POST")

        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk/create")
    def bulk_create(self, request: Request, *args, **kwargs) -> Response:
        """
        Generic endpoint to bulk create objects
        """
        # Check if user have permissions to create objects
        if not self.CAN_CREATE or not self.model.objects.can_create(request.user):
            raise MethodNotAllowed("POST")

        serializer_class = self.get_serializer_class()
        objects = []

        for item in request.data:
            serializer = serializer_class(details=True, data=item, context={"request": request})
            serializer.is_valid(raise_exception=True)
            objects.append(self.model(**serializer.validated_data))

        new_instances = self.model.bulk_create(objects)
        serializer = serializer_class(new_instances, many=True)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post", "patch"], url_path="bulk/update")
    def bulk_update(self, request: Request, *args, **kwargs) -> Response:
        """
        Generic endpoint to bulk update objects.

        This endpoint allows to post 2 different sets of data:

        1) Update a list of objects with the same data:
        {
            'ids': [1, 6, 7],
            'data': {
                'formula': '2',
            }
        }

        2) Update each object with different set of data:
        {
            '3': {'formula': '2'},
            '8': {'name': 'New name'},
            '9': {'formula': '3 kg', 'name': 'Mass'},
        }

        See description in related action on the AppModel.
        """
        data = request.data

        # 1) Update a list of objects with the same data
        if "ids" in data and "data" in data:
            obj_ids = data.get("ids")
            obj_data = data.get("data")
            data = {str(obj_id): obj_data for obj_id in obj_ids}  # Add same data for each object

        # 2) Update each object with different set of data
        else:
            obj_ids = data.keys()

        # Get objects and check permissions for each object
        objects = self.model.objects.as_writer(request.user).filter(id__in=obj_ids)
        check_permissions(objects, obj_ids)

        serialized_data = []
        updated_fields = set()  # Track updated fields to pass in bulk update
        db_fields = {field.name for field in self.model._meta.get_fields()}

        for obj in objects:
            serialized_result = {}  # Data to represent object in response with changed fields
            obj_data = data.get(str(obj.id))

            if obj_data:  # No need to validate or update object if its data is empty
                serializer = self.get_serializer(
                    obj, data=obj_data, partial=True, context={"request": request}
                )
                serializer.is_valid(raise_exception=True)

                # 1) Update object with validated and parsed data from serializer
                # 2) Use serializer fields to serialize response data using its
                #    own to_representation
                # 3) Track all updated fields to be used in updated_fields
                for field_name, value in serializer.validated_data.items():
                    setattr(obj, field_name, value)
                    serialized_result[field_name] = (
                        serializer.fields[field_name].to_representation(value)
                        if value is not None
                        else None
                    )
                    if field_name in db_fields:
                        updated_fields.add(field_name)

            serialized_data.append(serialized_result)

        self.model.bulk_update(objects, updated_fields)
        return Response(serialized_data)

    def destroy(self, *args, **kwargs) -> Response:
        """Check permissions to delete objects"""
        if not self.CAN_DELETE:
            raise MethodNotAllowed("DELETE")
        return super().destroy(*args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk/delete")
    def bulk_delete(self, request: Request, *args, **kwargs) -> Response:
        """Generic endpoint to bulk delete objects

        See description in related action on the AppModel.
        """
        if not self.CAN_DELETE:
            raise MethodNotAllowed("DELETE")

        obj_ids = request.data.get("ids")
        objects = self.model.objects.as_writer(request.user).filter(id__in=obj_ids)
        check_permissions(objects, obj_ids)
        self.model.bulk_delete(objects)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="bulk/add")
    def bulk_add_values(self, request: Request, *args, **kwargs) -> Response:
        """Bulk add one or more M2M values to the object

        See description in related action on the AppModel.
        TEST implemented in requirements/test_views.
        """
        obj_ids = request.data.get("ids")
        field = request.data.get("field")
        values = request.data.get("values")
        objects = self.model.objects.as_writer(request.user).filter(id__in=obj_ids)

        check_permissions(objects, obj_ids)

        updated_instances = self.model.bulk_add_values(objects, field, values)
        serializer_class = self.model.get_serializer_class()
        serializer = serializer_class(updated_instances, many=True)

        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="bulk/remove")
    def bulk_remove_values(self, request: Request, *args, **kwargs) -> Response:
        """Bulk remove one or more M2M values from the object

        See description in related action on the AppModel.
        TEST implemented in requirements/test_views.
        """
        obj_ids = request.data.get("ids")
        field = request.data.get("field")
        values = request.data.get("values")

        objects = self.model.objects.as_writer(request.user).filter(id__in=obj_ids)

        check_permissions(objects, obj_ids)

        updated_instances = self.model.bulk_remove_values(objects, field, values)
        serializer_class = self.model.get_serializer_class()
        serializer = serializer_class(updated_instances, many=True)

        return Response(serializer.data)
