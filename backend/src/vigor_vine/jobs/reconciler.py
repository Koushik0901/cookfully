from vigor_vine.application.jobs import JobService


def reconcile_jobs(service: JobService) -> dict[str, int]:
    released = service.release_due_retries()
    stalled = service.requeue_stalled()
    expired = service.reconcile_deadlines()
    return {"released": len(released), "stalled": len(stalled), "expired": len(expired)}
