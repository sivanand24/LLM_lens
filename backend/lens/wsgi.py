import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lens.settings")
# Under a WSGI server there is no autoreloader, so the check worker should always start.
os.environ.setdefault("LENS_START_WORKER", "true")

application = get_wsgi_application()
