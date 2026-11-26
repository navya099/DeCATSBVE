"""전주 미리보기·도면: BVE Object 폴더를 사용자 설정에서 (이전: D:\\BVE\\... 고정), 없는 파일은 건너뛰고 누락 목록에"""
import contextlib
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from file_io import user_settings  # noqa: E402
from tools import headless  # noqa: E402
from xref_module.path_resolver import PathResolver  # noqa: E402
from xref_module.preview import preview_sevice as ps  # noqa: E402

TRIANGLE = 'CreateMeshBuilder\nAddVertex,0,0,0\nAddVertex,1,0,0\nAddVertex,0,1,0\nAddFace,0,1,2\n'


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('DECATSBVE_SETTINGS', str(tmp_path / 'settings.json'))
    return tmp_path


@pytest.fixture
def pole():
    runner = headless.build_runner(headless.load_config(
        os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_single_250', 'case.json')))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return next(p for p in runner.poledata['main'] if p.structure == '토공' and p.section is None)


def test_settings_default_and_persist(settings):
    assert user_settings.get('bve_object_root') == user_settings.DEFAULTS['bve_object_root']
    user_settings.set('bve_object_root', str(settings / 'obj'))
    assert PathResolver.object_root() == str(settings / 'obj')
    assert PathResolver.object_path('temp/건축한계.csv') == os.path.join(str(settings / 'obj'), 'temp', '건축한계.csv')
    assert PathResolver.library_root().endswith(os.path.join('철도표준라이브러리', '전철전력'))
    (settings / 'settings.json').write_text('{깨진 파일', encoding='utf-8')
    assert user_settings.get('bve_object_root') == user_settings.DEFAULTS['bve_object_root']   # 깨지면 기본값


def test_preview_missing_root_does_not_fail(settings, pole):
    user_settings.set('bve_object_root', str(settings / 'nowhere'))
    result = ps.PreviewService().build(pole, 0, mode='single')
    assert result.objects == []
    assert any('건축한계.csv' in m for m in result.missing)       # 이전: 파일 하나 없으면 미리보기 전체 예외


def test_preview_uses_object_root(settings, pole):
    root = settings / 'Object'
    for rel in (ps.TRACK_OBJECT, ps.CLEARANCE_OBJECT, ps.CENTERLINE_OBJECT, ps.STRUCTURE_OBJECTS[('토공', 'single')]):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TRIANGLE, encoding='utf-8')
    user_settings.set('bve_object_root', str(root))
    result = ps.PreviewService().build(pole, 0, mode='single')
    assert len(result.objects) == 4
    assert not any(str(root) in m for m in result.missing)
    # 복선 상선(트랙 1)은 노반 단면을 그리지 않음 (이전: dummy.csv)
    assert not any('6공구' in m for m in ps.PreviewService().build(pole, 1, mode='double').missing)
