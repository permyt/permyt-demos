from django.urls import path, re_path

from .views import NoteFieldListView, NoteFieldView, PermytInboundView, ScopeCallView

urlpatterns = [
    re_path(r"^permyt/inbound/?$", PermytInboundView.as_view(), name="permyt-inbound"),
    path("notes/", NoteFieldListView.as_view(), name="note-field-list"),
    path("notes/<str:field_name>/", NoteFieldView.as_view(), name="note-field"),
    path("<str:field_name>/<str:action>/", ScopeCallView.as_view(), name="scope-call"),
]
