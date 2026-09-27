"""Architectures matching the RetinaNet + GhostNetV2/MobileNetV2 training notebook.

AD-005: production analyze uses these dual PyTorch models (supersedes AD-001 `.keras` artifact).
"""

from __future__ import annotations

from functools import partial

import torch
import torch.nn as nn
from torchvision import models
from torchvision.models.detection import retinanet_resnet50_fpn_v2
from torchvision.models.detection.retinanet import RetinaNetClassificationHead

NUM_CLASSES_DET = 3  # background + MILCO + NOMBO
NUM_CLASSES_CLS = 2
CLASS_NAMES = ("MILCO", "NOMBO")
FUSION_IMG_SIZE = 224
CROP_MARGIN = 0.15
# RetinaNet eval filter from the training notebook (score_thresh=0.5).
DETECTOR_SCORE_THRESHOLD = 0.5


def build_retinanet(num_classes: int = NUM_CLASSES_DET) -> nn.Module:
    """Build RetinaNet ResNet50-FPN v2 with a custom classification head."""
    model = retinanet_resnet50_fpn_v2(weights=None)
    num_anchors = model.head.classification_head.num_anchors
    in_channels = model.backbone.out_channels
    model.head.classification_head = RetinaNetClassificationHead(
        in_channels=in_channels,
        num_anchors=num_anchors,
        num_classes=num_classes,
        norm_layer=partial(nn.GroupNorm, 32),
    )
    return model


class FusionGhostNetV2MobileNetV2(nn.Module):
    """Concatenate GhostNetV2 + MobileNetV2 features into a dense MILCO/NOMBO head."""

    def __init__(self, num_classes: int = NUM_CLASSES_CLS, *, pretrained: bool = False) -> None:
        super().__init__()
        import timm

        self.ghostnet = timm.create_model(
            "ghostnetv2_100",
            pretrained=pretrained,
            num_classes=0,
        )
        mobile_weights = models.MobileNet_V2_Weights.IMAGENET1K_V2 if pretrained else None
        self.mobilenet = models.mobilenet_v2(weights=mobile_weights)
        self.mobilenet.classifier = nn.Identity()

        with torch.no_grad():
            dummy = torch.zeros(1, 3, FUSION_IMG_SIZE, FUSION_IMG_SIZE)
            ghost_dim = int(self.ghostnet(dummy).shape[1])
            mobile_dim = int(self.mobilenet(dummy).shape[1])

        fused_dim = ghost_dim + mobile_dim
        self.classifier = nn.Sequential(
            nn.Linear(fused_dim, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.4),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        fused = torch.cat([self.ghostnet(x), self.mobilenet(x)], dim=1)
        return self.classifier(fused)
