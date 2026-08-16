from datetime import datetime

from cookfully.application.jobs import JobService


def reconcile_jobs(service: JobService, *, now: datetime | None = None) -> dict[str, int]:
    released = service.release_due_retries(now=now)
    stalled = service.requeue_stalled(now=now)
    expired = service.reconcile_deadlines(now=now)
    return {"released": len(released), "stalled": len(stalled), "expired": len(expired)}
