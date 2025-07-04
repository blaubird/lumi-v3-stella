from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from .confirm_pending import confirm_pending
from .send_reminders import send_reminders

scheduler = AsyncIOScheduler()


def init_scheduler(app: FastAPI) -> None:
    scheduler.add_job(confirm_pending, "interval", minutes=1)
    scheduler.add_job(send_reminders, "interval", minutes=1)

    @app.on_event("startup")
    async def start_scheduler() -> None:
        scheduler.start()

    @app.on_event("shutdown")
    async def stop_scheduler() -> None:
        scheduler.shutdown()
