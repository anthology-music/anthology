"""API and stream schemas of the quality analysis."""

from pydantic import BaseModel

from anthology.sync.messages import StreamRow


class AnalysisStart(BaseModel):
    # Re-analyse results of an older version of the analysis.
    full: bool = False


class AnalysisStarted(BaseModel):
    job_id: str | None


class QualitySummaryRow(StreamRow):
    """Active originals per quality status (spec: quality-analysis, Quality overview)."""

    unanalysed: int
    genuine: int
    suspicious: int
    upscaled: int
    confirmed_genuine: int
