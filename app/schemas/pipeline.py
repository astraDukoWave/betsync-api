from datetime import date
from typing import Optional

from pydantic import BaseModel


class PipelineRunRequest(BaseModel):
    run_date: Optional[date] = None
    force: bool = False


class PipelineJobResponse(BaseModel):
    job_id: str
    status: str
    picks_suggested: Optional[int] = None
    parlays_suggested: Optional[int] = None
    completed_at: Optional[str] = None
    duration_sec: Optional[float] = None


class PipelineTriggerResponse(BaseModel):
    job_id: str
    status: str
    message: str
