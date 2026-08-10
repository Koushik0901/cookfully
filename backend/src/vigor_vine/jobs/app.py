from celery import Celery

from vigor_vine.infrastructure.config import get_settings

settings = get_settings()
celery_app = Celery("vigor_vine", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=False,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=55,
    task_time_limit=60,
    worker_send_task_events=True,
    task_send_sent_event=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 900},
    result_backend=None,
    imports=("vigor_vine.jobs.recipe_pipeline",),
)
celery_app.autodiscover_tasks(["vigor_vine.jobs"])


@celery_app.task(name="vigor_vine.health", ignore_result=True)  # type: ignore[untyped-decorator]
def worker_health() -> str:
    return "ok"
