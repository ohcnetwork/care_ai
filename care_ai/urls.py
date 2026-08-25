from django.shortcuts import HttpResponse
from django.urls import path

from .views import AskAIView, EkaLabReportView


def healthy(request):
    return HttpResponse("Hello from ai")


urlpatterns = [
    path("health", healthy),
    path("ask/", AskAIView.as_view(), name="ask-ai"),
    path("eka/lab-report/", EkaLabReportView.as_view(), name="eka-lab-report"),
]
