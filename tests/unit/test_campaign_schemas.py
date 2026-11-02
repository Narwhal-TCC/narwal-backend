import pytest
from pydantic import ValidationError

from app.schemas.campaigns import CampaignCreateBody, CampaignPatchBody


def test_create_body_defaults_simulated_to_false():
    body = CampaignCreateBody(
        name="Alpha",
        area={"min_lat": 38.6, "min_lon": -9.5, "max_lat": 38.7, "max_lon": -9.35},
    )
    assert body.simulated is False


def test_create_body_accepts_simulated_true():
    body = CampaignCreateBody(
        name="Alpha",
        area={"min_lat": 38.6, "min_lon": -9.5, "max_lat": 38.7, "max_lon": -9.35},
        simulated=True,
    )
    assert body.simulated is True


def test_create_body_requires_name_and_area():
    with pytest.raises(ValidationError):
        CampaignCreateBody.model_validate({"name": "Alpha"})
    with pytest.raises(ValidationError):
        CampaignCreateBody.model_validate(
            {"area": {"min_lat": 0, "min_lon": 0, "max_lat": 1, "max_lon": 1}}
        )


def test_patch_body_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        CampaignPatchBody.model_validate({})

    body = CampaignPatchBody.model_validate({"name": "Renamed"})
    assert body.name == "Renamed"
    assert body.area is None
    assert body.simulated is None
