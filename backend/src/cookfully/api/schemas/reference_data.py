from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.schemas.jobs import JobResponse

InstallUnit = Literal["foundation_sr_legacy", "branded"]


class ReferenceRelease(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_type: str = Field(alias="datasetType")
    release_id: str = Field(alias="releaseId")
    released_on: str = Field(alias="releasedOn")
    source_url: str = Field(alias="sourceUrl")
    license: str
    review_overdue: bool = Field(alias="reviewOverdue")


class ReferenceDataStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    available: bool
    missing: tuple[str, ...]
    releases: tuple[ReferenceRelease, ...]
    requested_datasets: tuple[str, ...] | None = Field(alias="requestedDatasets", default=None)
    job: JobResponse | None = None


class ReferenceDataInstallRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    datasets: tuple[InstallUnit, ...] = Field(min_length=1)
