from pydantic import BaseModel, model_validator

from app.schemas.analysis import CampaignArea


class CampaignCreateBody(BaseModel):
    name: str
    area: CampaignArea
    simulated: bool = False


class CampaignPatchBody(BaseModel):
    name: str | None = None
    area: CampaignArea | None = None
    simulated: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "CampaignPatchBody":
        if self.name is None and self.area is None and self.simulated is None:
            msg = "at least one of name, area, or simulated is required"
            raise ValueError(msg)
        return self
