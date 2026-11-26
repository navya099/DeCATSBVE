"""전차선로 도면 (DXF): 평면도·종단면도

    from core.drawing import DrawingSettings, export_drawings
    files = export_drawings(runner, out_dir, DrawingSettings(plan_scale=1000, profile_v_scale=100))

도면은 BVE 출력과 같은 데이터(runner.poledata·wire_data·선형)를 그대로 그린다
(이전 레거시 도면은 전주·전선 값을 따로 다시 계산해 BVE 출력과 어긋날 수 있었음).
"""
from core.drawing.settings import DrawingSettings
from core.drawing.export import export_drawings

__all__ = ['DrawingSettings', 'export_drawings']
