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


def test_preview_uses_bundled_objects_without_bve(settings, pole):
    """BVE Object 폴더가 없어도 저장소 assets/preview 의 배경 오브젝트로 미리보기 (레일·건축한계·중심선·노반)"""
    user_settings.set('bve_object_root', str(settings / 'nowhere'))
    for mode, track in (('single', 0), ('double', 0), ('double', 1)):
        result = ps.PreviewService().build(pole, track, mode=mode)
        assert not any('.csv' in m and ('노반' in m or 'temp' in m or '궤도' in m) for m in result.missing), result.missing
        assert len(result.objects) == (3 if track == 1 else 4)          # 복선 상선은 노반 단면 생략
        bundled = [o for o in result.objects if o.category == 'STRUCTURE']
        assert all(o.mesh.meshes for o in bundled)


def test_every_background_object_is_bundled_and_parses():
    from file_io.file_controler import FileController
    from xref_module.temp_parser import CSVObjectParser
    rels = [ps.TRACK_OBJECT, ps.CLEARANCE_OBJECT, ps.CENTERLINE_OBJECT, *ps.STRUCTURE_OBJECTS.values()]
    for rel in rels:
        path = os.path.join(ROOT, 'assets', 'preview', rel.split('/')[-1])
        assert os.path.isfile(path), rel
        fc = FileController()
        fc.set_path(path)
        fc.load()
        CSVObjectParser(fc.get_lines()).parse()


def test_object_folder_overrides_bundled(settings, pole):
    """Object 폴더에 같은 경로 파일이 있으면 그것을 먼저 (사용자 수정본)"""
    root = settings / 'Object'
    for rel in (ps.TRACK_OBJECT, ps.CLEARANCE_OBJECT, ps.CENTERLINE_OBJECT, ps.STRUCTURE_OBJECTS[('토공', 'single')]):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TRIANGLE, encoding='utf-8')
    user_settings.set('bve_object_root', str(root))
    assert PathResolver.preview_object(ps.TRACK_OBJECT) == str(root / ps.TRACK_OBJECT).replace('/', os.sep)
    assert PathResolver.preview_object(ps.STRUCTURE_OBJECTS[('터널', 'single')]).startswith(
        os.path.join(ROOT, 'assets', 'preview'))
    result = ps.PreviewService().build(pole, 0, mode='single')
    assert len(result.objects) == 4
    assert all(len(o.mesh.meshes) == 1 for o in result.objects if o.category == 'STRUCTURE')   # 삼각형 1개짜리 사용자 파일


def test_library_object_by_index_path_disambiguates_same_names(settings):
    """같은 이름 파일이 여러 폴더(교량용/토공)에 있으면 인덱스 라이브러리 경로로 정확한 파일 (대소문자 무시)"""
    import pandas as pd
    from xref_module.index_libmgr import IndexLibrary
    user_settings.set('bve_object_root', str(settings / 'nowhere'))
    lib = IndexLibrary(pd.DataFrame([
        {'인덱스': 512, '파일명': 'CaKo250-OpG3.5-I-L', '경로': r'철도표준라이브러리\전철전력\CAKO250\교량용\CaKo250-OpG3.5-I-L.csv'},
        {'인덱스': 540, '파일명': 'CaKo250-OpG3.5-I-L', '경로': r'철도표준라이브러리\전철전력\CAKO250\토공\CaKo250-OpG3.5-I-L.csv'},
        {'인덱스': 1010, '파일명': 'CaKo250-OpG3.5-I-L', '경로': r'원강선\전철전력\교량용\CaKo250-OpG3.5-I-L.csv'},
    ]))
    svc = ps.PreviewService(lib)
    bridge, earth = svc.find('CaKo250-OpG3.5-I-L', 512), svc.find('CaKo250-OpG3.5-I-L', 540)
    assert bridge and earth and bridge != earth
    assert os.path.join('cako250', '교량용') in bridge and os.path.join('cako250', '토공') in earth
    # 전철전력 라이브러리 밖 경로 → 이름 검색으로 (저장소에 같은 이름 파일 중 하나)
    assert svc.find('CaKo250-OpG3.5-I-L', 1010) is not None
    assert svc.find('없는오브젝트', None) is None
    # Object 폴더에 있으면 그 파일 먼저
    own = settings / 'obj' / '철도표준라이브러리' / '전철전력' / 'CAKO250' / '토공' / 'CaKo250-OpG3.5-I-L.csv'
    own.parent.mkdir(parents=True)
    own.write_text(TRIANGLE, encoding='utf-8')
    user_settings.set('bve_object_root', str(settings / 'obj'))
    assert ps.PreviewService(lib).find('CaKo250-OpG3.5-I-L', 540) == str(own)


def test_null_object_is_not_reported_missing(settings, pole):
    from core.equipment.equipment_data import EquipmentDATA
    pole.equipments.append(EquipmentDATA(name='null', index=0, offset=(0, 0)))
    assert 'null' not in ps.PreviewService().build(pole, 0, mode='single').missing


def _parse(text):
    from xref_module.temp_parser import CSVObjectParser
    return CSVObjectParser(text.splitlines()).parse()


def test_generated_centerline_and_outline():
    from tools import preview_objects as po
    c = _parse(po.centerline_csv(bottom=-0.5, top=7.0, width=0.01))
    xs = [v.x for m in c.meshes for v in m.vertices]
    ys = [v.y for m in c.meshes for v in m.vertices]
    assert len(c.meshes) == 1 and (min(xs), max(xs), min(ys), max(ys)) == (-0.005, 0.005, -0.5, 7.0)
    o = _parse(po.polylines_csv([[(-2.1, 0), (-2.1, 5.15), (2.1, 5.15), (2.1, 0)]], depth=0.05))
    m = o.meshes[0]
    assert len(m.vertices) == 8 and len(m.faces) == 3 * 4                      # 선분 3개 × 앞뒤 삼각형 4개
    assert {v.z for v in m.vertices} == {0.0, 0.05}
    # 저장소의 선로중심선·건축한계는 이 도구로 만든 것 (빈 메시 아님)
    with open(os.path.join(ROOT, 'assets', 'preview', '선로중심선.csv'), encoding='utf-8-sig') as f:
        assert len(_parse(f.read()).meshes) == 1
    with open(os.path.join(ROOT, 'assets', 'preview', '건축한계.csv'), encoding='utf-8-sig') as f:
        clearance = _parse(f.read())
    vs = [v for m in clearance.meshes for v in m.vertices]
    assert len(clearance.meshes) == 15
    assert (min(v.x for v in vs), max(v.x for v in vs)) == (-2.1, 2.1) and max(v.y for v in vs) == pytest.approx(6.45)


def test_outline_from_dxf(tmp_path):
    ezdxf = pytest.importorskip('ezdxf')
    from tools import preview_objects as po
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(1000, 500), (1000, 4500), (5000, 4500)], dxfattribs={'layer': '건축한계'})
    msp.add_arc((3000, 4500), 500, 0, 180, dxfattribs={'layer': '건축한계'})
    msp.add_line((0, 0), (9000, 0), dxfattribs={'layer': '기타'})
    path = tmp_path / 'outline.dxf'
    doc.saveas(path)
    lines = po.read_dxf_polylines(str(path), layer='건축한계', scale=0.001, origin=(3000, 500))
    assert len(lines) == 2                                                       # 다른 레이어 제외
    assert lines[0][0] == pytest.approx((-2.0, 0.0)) and lines[0][-1] == pytest.approx((2.0, 4.0))
    assert max(y for _, y in lines[1]) == pytest.approx(4.5, abs=0.01)           # 호 → 꺾은선
    assert len(_parse(po.polylines_csv(lines)).meshes) == 2
