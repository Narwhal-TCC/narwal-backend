"""Seed demo campaign analyses from local YOLO-labeled sonar images (data/2018, data/2021)."""

from __future__ import annotations

import hashlib
import logging
import struct
from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.bootstrap.seed import MOCK_CAMPAIGN_NAME
from app.core.config import get_settings
from app.repositories.analyses import AnalysisRepository
from app.repositories.campaigns import CampaignRepository
from app.repositories.s3_store import S3ObjectStore
from app.repositories.users import UserRepository
from app.schemas.analysis import Detection
from app.services.primary_class import compute_primary_class, count_milco

logger = logging.getLogger(__name__)

YOLO_CLASS_LABELS = {0: "MILCO", 1: "NOMBO"}
SEED_YEARS = ("2018", "2021")
SEED_ANALYSIS_PREFIX = "seed-demo-"


def backend_data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def seed_analysis_id(stem: str) -> str:
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()[:26]
    return f"{SEED_ANALYSIS_PREFIX}{digest}"


def simulated_position(
    stem: str,
    *,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> tuple[float, float]:
    digest = hashlib.sha256(stem.encode("utf-8")).digest()
    lat_ratio = int.from_bytes(digest[0:4], "big") / 2**32
    lon_ratio = int.from_bytes(digest[4:8], "big") / 2**32
    lat = min_lat + lat_ratio * (max_lat - min_lat)
    lon = min_lon + lon_ratio * (max_lon - min_lon)
    return lat, lon


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index < len(data) - 1:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in (0xC0, 0xC1, 0xC2):
            height = struct.unpack(">H", data[index + 3 : index + 5])[0]
            width = struct.unpack(">H", data[index + 5 : index + 7])[0]
            return width, height
        if marker in (0xD9, 0xDA):
            break
        if index + 2 > len(data):
            break
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        index += segment_length
    return None


def image_dimensions(image_path: Path) -> tuple[int, int]:
    raw = image_path.read_bytes()
    jpeg = _jpeg_size(raw)
    if jpeg is not None:
        return jpeg
    with Image.open(BytesIO(raw)) as image:
        return int(image.width), int(image.height)


def yolo_line_to_detection(line: str, image_width: int, image_height: int) -> Detection:
    parts = line.split()
    if len(parts) < 5:
        raise ValueError(f"Invalid YOLO line: {line!r}")
    class_id = int(parts[0])
    if class_id not in YOLO_CLASS_LABELS:
        raise ValueError(f"Unknown YOLO class id {class_id}")
    center_x = float(parts[1])
    center_y = float(parts[2])
    box_w = float(parts[3])
    box_h = float(parts[4])
    x1 = (center_x - box_w / 2) * image_width
    y1 = (center_y - box_h / 2) * image_height
    x2 = (center_x + box_w / 2) * image_width
    y2 = (center_y + box_h / 2) * image_height
    label = YOLO_CLASS_LABELS[class_id]
    confidence = 0.92
    return Detection(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        confidence=confidence,
        label=label,  # type: ignore[arg-type]
        detector_score=confidence,
    )


def detections_from_label_file(txt_path: Path, image_path: Path) -> list[Detection]:
    raw = txt_path.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in raw if line.strip()]
    if not lines:
        return []
    width, height = image_dimensions(image_path)
    return [yolo_line_to_detection(line, width, height) for line in lines]


def iter_labeled_samples(
    data_root: Path,
    years: tuple[str, ...] = SEED_YEARS,
) -> Iterator[tuple[Path, Path]]:
    for year in years:
        year_dir = data_root / year
        if not year_dir.is_dir():
            continue
        for txt_path in sorted(year_dir.glob("*.txt")):
            image_path = txt_path.with_suffix(".jpg")
            if not image_path.is_file():
                continue
            if not txt_path.read_text(encoding="utf-8").strip():
                continue
            yield txt_path, image_path


def realign_simulated_campaign_positions(
    *,
    campaign: dict,
    org_id: str,
    analysis_repo: AnalysisRepository,
    data_root: Path,
) -> int:
    """Move simulated points back inside the campaign box (offshore). Returns rows updated."""
    updated = 0
    min_lat = float(campaign["min_lat"])
    max_lat = float(campaign["max_lat"])
    min_lon = float(campaign["min_lon"])
    max_lon = float(campaign["max_lon"])

    for txt_path, _image_path in iter_labeled_samples(data_root):
        stem = txt_path.stem
        analysis_id = seed_analysis_id(stem)
        if analysis_repo.get_analysis(org_id, analysis_id) is None:
            continue
        lat, lon = simulated_position(
            stem,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )
        if analysis_repo.update_location(org_id, analysis_id, latitude=lat, longitude=lon):
            updated += 1

    records = analysis_repo.list_by_campaign(
        org_id,
        campaign["campaign_id"],
        limit=500,
    )
    for record in records:
        if record.get("location_source") != "simulated":
            continue
        analysis_id = record["id"]
        if analysis_id.startswith(SEED_ANALYSIS_PREFIX):
            continue
        lat, lon = simulated_position(
            analysis_id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )
        if analysis_repo.update_location(org_id, analysis_id, latitude=lat, longitude=lon):
            updated += 1

    return updated


def seed_demo_campaign_analyses(
    *,
    repository: UserRepository | None = None,
    store: S3ObjectStore | None = None,
    data_root: Path | None = None,
) -> int:
    """Insert labeled demo analyses for the mock campaign. Returns count of newly seeded rows."""
    settings = get_settings()
    users = repository or UserRepository()
    campaign_repo = CampaignRepository(users._path)
    analysis_repo = AnalysisRepository(users._path)
    s3 = store or S3ObjectStore()
    root = data_root or backend_data_root()

    demo_user = users.get_by_username(settings.seed_demo_username)
    if demo_user is None:
        return 0

    campaign = campaign_repo.get_by_name(settings.seed_demo_org_id, MOCK_CAMPAIGN_NAME)
    if campaign is None:
        return 0

    created = 0
    for txt_path, image_path in iter_labeled_samples(root):
        stem = txt_path.stem
        analysis_id = seed_analysis_id(stem)
        org_id = settings.seed_demo_org_id
        if analysis_repo.get_analysis(org_id, analysis_id) is not None:
            continue

        detections = detections_from_label_file(txt_path, image_path)
        if not detections:
            continue

        primary_class = compute_primary_class(detections)
        milco_count = count_milco(detections)
        lat, lon = simulated_position(
            stem,
            min_lat=float(campaign["min_lat"]),
            max_lat=float(campaign["max_lat"]),
            min_lon=float(campaign["min_lon"]),
            max_lon=float(campaign["max_lon"]),
        )

        image_bytes = image_path.read_bytes()
        image_key = s3.put_analysis_image(
            org_id=org_id,
            analysis_id=analysis_id,
            ext="jpg",
            data=image_bytes,
            content_type="image/jpeg",
        )

        year_suffix = stem.rsplit("_", 1)[-1]
        try:
            collected_year = int(year_suffix)
            collected_at = datetime(collected_year, 6, 15, tzinfo=UTC).isoformat()
        except ValueError:
            collected_at = None

        analysis_repo.put_analysis(
            analysis_id=analysis_id,
            org_id=org_id,
            user_id=demo_user["user_id"],
            status="succeeded",
            review_status="pending",
            primary_class=primary_class,
            campaign_name=campaign["name"],
            campaign_id=campaign["campaign_id"],
            latitude=lat,
            longitude=lon,
            location_source="simulated",
            collected_at=collected_at,
            milco_detection_count=milco_count,
            detections=[detection.model_dump() for detection in detections],
            image_s3_key=image_key,
            image_content_type="image/jpeg",
            created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            inference_ms=0,
        )
        created += 1

    repositioned = realign_simulated_campaign_positions(
        campaign=campaign,
        org_id=settings.seed_demo_org_id,
        analysis_repo=analysis_repo,
        data_root=root,
    )
    if created:
        logger.info("Seeded %s demo campaign analyses from %s", created, root)
    if repositioned:
        logger.info("Realigned %s simulated positions for demo campaign", repositioned)
    return created
