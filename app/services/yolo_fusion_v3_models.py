"""Crop fusion classifier from TESTE_CONNEXT_FUSAO (ClassificadorRecortes, notebook v3)."""

from __future__ import annotations

import torch
import torch.nn as nn

FUSION_V3_IMG_SIZE = 224
FUSION_V3_CLASS_NAMES = ("MILCO", "NOMBO")
# MODO_FINAL=auto in the 3-parceiros notebook (best validation AUC among the three fusions).
FUSION_V3_BACKBONE_NAMES = ("convnext_pico", "edgenext_small")
FUSION_MOBILEVIT_BACKBONE_NAMES = ("convnext_pico", "mobilevitv2_100")


def _create_backbone(name: str) -> nn.Module:
    import timm

    backbone = timm.create_model(name, pretrained=False, num_classes=0)
    data_config = timm.data.resolve_data_config({}, model=backbone)
    backbone.register_buffer(
        "mu",
        torch.tensor(data_config["mean"]).view(1, 3, 1, 1),
        persistent=False,
    )
    backbone.register_buffer(
        "sd",
        torch.tensor(data_config["std"]).view(1, 3, 1, 1),
        persistent=False,
    )
    return backbone


class CropFusionClassifier(nn.Module):
    """Input tensors in [0, 1]; each backbone applies its ImageNet normalization."""

    def __init__(
        self,
        backbone_names: tuple[str, ...] = FUSION_V3_BACKBONE_NAMES,
        num_classes: int = 2,
    ) -> None:
        super().__init__()
        names = list(backbone_names)
        self.backbone = nn.ModuleList([_create_backbone(name) for name in names])

        was_training = self.training
        self.eval()
        with torch.no_grad():
            dims = [
                int(
                    branch(torch.zeros(1, 3, FUSION_V3_IMG_SIZE, FUSION_V3_IMG_SIZE)).shape[1]
                )
                for branch in self.backbone
            ]
        if was_training:
            self.train()
        feature_dim = sum(dims)

        if len(names) == 1:
            self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(feature_dim, num_classes))
        else:
            self.head = nn.Sequential(
                nn.Linear(feature_dim, 256),
                nn.ReLU(inplace=True),
                nn.Dropout(0.4),
                nn.Linear(256, num_classes),
            )

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        features = [branch((batch - branch.mu) / branch.sd) for branch in self.backbone]
        return self.head(torch.cat(features, dim=1))


def build_crop_fusion_classifier(
    state_dict: dict[str, torch.Tensor],
    backbone_names: tuple[str, ...] = FUSION_V3_BACKBONE_NAMES,
) -> CropFusionClassifier:
    model = CropFusionClassifier(backbone_names)
    model.load_state_dict({key: value.float() for key, value in state_dict.items()})
    return model.eval()
