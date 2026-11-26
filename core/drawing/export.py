"""도면 파일 저장: 평면도.dxf, 종단면도_본선.dxf (복선이면 종단면도_상선.dxf)"""
import os

from core.drawing.settings import DrawingSettings

TRACK_NAME = {'main': '본선', 'sub': '상선'}


def export_drawings(runner, out_dir, settings: DrawingSettings | None = None):
    """runner 의 전주·전선으로 도면 저장. 반환: 저장한 파일 경로 목록"""
    from core.drawing.plan_profile import draw_plan, draw_profile
    settings = settings or DrawingSettings()
    if not runner.poledata:
        raise ValueError('도면을 그릴 전주 데이터가 없습니다. 먼저 실행하세요.')
    os.makedirs(out_dir, exist_ok=True)
    files = []
    path = os.path.join(out_dir, '평면도.dxf')
    draw_plan(runner, settings).saveas(path)
    files.append(path)
    for track, poles in runner.poledata.items():
        if not poles:
            continue
        path = os.path.join(out_dir, f'종단면도_{TRACK_NAME.get(track, track)}.dxf')
        draw_profile(runner, track, settings).saveas(path)
        files.append(path)
    return files
