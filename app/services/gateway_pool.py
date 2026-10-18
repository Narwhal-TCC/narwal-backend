from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.repositories.s3_store import S3ObjectStore
from app.services.model_gateway import ModelGateway, TwoStageTorchGateway
from app.services.model_registry import DEFAULT_MODEL_ID
from app.services.yolo_convnext import YoloConvnextGateway, YoloConvnextWeights

YOLO_BALANCED_ID = "yolo-convnext-balanced"
YOLO_RECALL_ID = "yolo-convnext-recall"
TWO_STAGE_ID = "two-stage-pt"

FUSION_CONF_BY_ID = {
    YOLO_BALANCED_ID: 0.4,
    YOLO_RECALL_ID: 0.2,
}

GatewayFactory = Callable[[], ModelGateway]


class GatewayPool:
    """Maps registered model ids to gateways; YOLO ids share one weights loader."""

    def __init__(
        self,
        store: S3ObjectStore | None = None,
        *,
        yolo_weights: YoloConvnextWeights | None = None,
        gateway_factories: dict[str, GatewayFactory] | None = None,
    ) -> None:
        self._store = store or S3ObjectStore()
        self._yolo_weights = yolo_weights
        self._gateway_factories = gateway_factories or {}
        self._gateways: dict[str, ModelGateway] = {}
        self._lock = threading.Lock()

    @property
    def yolo_weights(self) -> YoloConvnextWeights | None:
        return self._yolo_weights

    def get(self, model_id: str) -> ModelGateway:
        with self._lock:
            cached = self._gateways.get(model_id)
            if cached is not None:
                return cached
            gateway = self._build(model_id)
            self._gateways[model_id] = gateway
            return gateway

    def _shared_yolo_weights(self) -> YoloConvnextWeights:
        if self._yolo_weights is None:
            self._yolo_weights = YoloConvnextWeights(self._store)
        return self._yolo_weights

    def _build(self, model_id: str) -> ModelGateway:
        factory = self._gateway_factories.get(model_id)
        if factory is not None:
            return factory()
        if model_id == TWO_STAGE_ID:
            return TwoStageTorchGateway(store=self._store)
        fusion_conf = FUSION_CONF_BY_ID.get(model_id)
        if fusion_conf is not None:
            return YoloConvnextGateway(self._shared_yolo_weights(), fusion_conf)
        raise KeyError(f"Unregistered model id: {model_id}")

    def preload_default(self) -> Any:
        return self.get(DEFAULT_MODEL_ID).ensure_model_loaded()
