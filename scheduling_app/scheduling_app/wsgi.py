"""
WSGI config for scheduling_app project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
import sys
from pathlib import Path

# Ensure the Django project dir (containing account/, scheduling/, dashboard/) is importable
# regardless of the working directory gunicorn is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scheduling_app.settings')

application = get_wsgi_application()
