from django.shortcuts import HttpResponse
from django.urls import path

from .views import AskAIView


def healthy(request):
    return HttpResponse("Hello from ai")


urlpatterns = [
    path("health", healthy),
    path("ask/", AskAIView.as_view(), name="ask-ai"),
]
