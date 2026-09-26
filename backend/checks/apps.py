import os
import sys

from django.apps import AppConfig


def _should_start_worker() -> bool:
    if os.environ.get("LENS_START_WORKER", "").lower() == "true":
        return True
    if "runserver" in sys.argv:
        # The autoreloader runs ready() in a parent and a child; only the child serves requests.
        return os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv
    return False


class ChecksConfig(AppConfig):
    name = "checks"

    def ready(self):
        if _should_start_worker():
            from checks import worker

            worker.start()
