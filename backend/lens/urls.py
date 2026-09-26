from django.urls import path

from proxy.views import chat
from stats import views as stats

urlpatterns = [
    path("v1/chat", chat),
    path("api/stats/summary", stats.summary),
    path("api/stats/timeseries", stats.timeseries),
    path("api/stats/flags", stats.flags),
    path("api/calls", stats.calls),
    path("api/calls/<str:request_id>", stats.call_detail),
    path("api/alerts", stats.alerts),
    path("api/alerts/<str:alert_id>/ack", stats.acknowledge_alert),
    path("api/baselines/<str:app_id>", stats.baseline_detail),
    path("api/baselines/<str:app_id>/rebuild", stats.rebuild_baseline),
    path("api/apps", stats.apps),
]
