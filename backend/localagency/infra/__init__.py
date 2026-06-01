"""localagency/infra/__init__.py"""

from localagency.infra.tasks import app as celery_app

__all__ = ["celery_app"]
