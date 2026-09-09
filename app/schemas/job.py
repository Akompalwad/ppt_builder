from enum import Enum
from pydantic import BaseModel
class JobStage(str, Enum): queued="QUEUED"; initializing="INITIALIZING"; researching="RESEARCHING"; validating="VALIDATING"; planning="PLANNING"; designing="DESIGNING"; planning_visuals="PLANNING_VISUALS"; composing="COMPOSING"; qa="QA"; rendering="RENDERING"; completed="COMPLETED"; failed="FAILED"
class JobStatus(BaseModel): id: str; presentation_id: str; status: str; progress: int; current_stage: str; error_message: str | None = None
