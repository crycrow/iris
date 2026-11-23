from fastapi import APIRouter
from . import tasks, resources, releases, timesheet, metrics, reports, analytics

router = APIRouter()
for child in (tasks, resources, releases, timesheet, metrics, reports, analytics):
    router.include_router(child.router)
