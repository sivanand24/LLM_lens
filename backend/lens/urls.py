from django.urls import path

from proxy.views import chat

urlpatterns = [
    path("v1/chat", chat),
]
