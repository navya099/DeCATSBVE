from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xref_module.preview.layer_object import PreviewLayerObject


@dataclass
class PreviewBuildResult:
    objects: list["PreviewLayerObject"]  # 모든 레이어 통합
    missing: list[str]


