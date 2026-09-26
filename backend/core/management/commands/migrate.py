"""Overrides Django's migrate: there is no SQL schema, so this just creates Mongo indexes."""
from django.core.management.base import BaseCommand
from django.db.migrations.autodetector import MigrationAutodetector

from core.db import ensure_indexes


class Command(BaseCommand):
    help = "Create MongoDB indexes (no SQL migrations in this project)."
    # Django 5.2's system check expects migrate and makemigrations to share this.
    autodetector = MigrationAutodetector

    def add_arguments(self, parser):
        # Accept and ignore Django's usual migrate arguments.
        parser.add_argument("args", nargs="*")
        parser.add_argument("--noinput", "--no-input", action="store_true")

    def handle(self, *args, **options):
        ensure_indexes()
        self.stdout.write(self.style.SUCCESS("MongoDB indexes ensured."))
