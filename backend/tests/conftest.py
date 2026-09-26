import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lens.settings")
django.setup()
