import time

from app.workers.tasks import run_recommendation_cycle


def main() -> None:
    """Minimal worker loop placeholder.

    Replace with Celery/RQ worker process in production deployment.
    """
    print("worker started")
    while True:
        _ = run_recommendation_cycle({"trigger": "heartbeat"})
        time.sleep(60)


if __name__ == "__main__":
    main()
