"""전차선로 도면(평면도·종단면도) 테스트: python -m pytest tests  (ezdxf 필요)"""
import contextlib
import io
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.drawing.settings import DrawingSettings, mast_dimensions, wire_layer  # noqa: E402
from core.pole import pole_units  # noqa: E402
from tools import headless  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')


def run_case(name='synthetic_double_rail_150', **overrides):
    cfg = headless.load_config(os.path.join(CASES, name, 'case.json'))
    cfg.update(overrides)
    runner = headless.build_runner(cfg)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return runner


def test_settings_and_mast_dimensions():
    s = DrawingSettings(plan_scale=1200, profile_v_scale=200)
    assert s.symbol == 1.2 and s.exaggeration == 6
    with pytest.raises(ValueError):
        DrawingSettings(plan_scale=0)
    assert mast_dimensions('강관주-P10-9m') == (9.0, 0.2674, 0.0)
    assert mast_dimensions('강관주-P12-8.5m') == (8.5, 0.312, 0.0)
    assert mast_dimensions('터널하수강') == (1.735, 0.25, 4.54)
    assert mast_dimensions('H형주-250X255-10m')[0] == 10.0
    assert mast_dimensions(None) == (9.0, 0.3, 0.0)                    # 모르면 기본값
    assert [wire_layer(x) for x in ('전차선', '본선전차선', '무효전차선', '무효조가선', '무효->본선전차선', '조가선',
                                    'AF', 'FPW', '흐름방지선', '부급전선', '기타')] == [
        'contact', 'contact', 'inactive', 'inactive', 'contact', 'messenger', 'feeder', 'protect', 'flowstop',
        'feeder', 'other_wire']


@pytest.mark.parametrize('airjoint_type', ['single', 'double_pole'])
def test_bracket_stations_match_bve_csv(airjoint_type):
    """도면의 브래킷 측점 = BVE CSV 에 쓰인 브래킷 측점 (같은 규칙)"""
    from bve.bvecsv import BVECSV
    from core import section_edit as se
    from core.model_rebuilder import alignment_for, rebuild
    runner = run_case('synthetic_single_250', airjoint_type=airjoint_type)
    poles = runner.poledata['main']
    for kind, k in (('airsection_single', 0), ('airsection_double', 1)):
        n = se.SECTION_KINDS[kind].n_poles
        free = [i for i in range(3, len(poles) - n) if all(poles[j].section is None for j in range(i, i + n))]
        se.apply_add(runner, se.plan_add(runner, 'main', poles[free[len(free) * (k + 1) // 3]].pos, kind), alignment_for)
    with contextlib.redirect_stdout(io.StringIO()):
        rebuild(runner)
        text = ''.join(BVECSV(poles, runner.wire_data['main'], 0).create_pole_csv())
    checked = 0
    for pole in poles:
        for bracket, dpos in pole_units.bracket_stations(pole):
            station = round(pole.pos + dpos, 6)
            assert f'\n{station},.freeobj 0;{bracket.index};' in '\n' + text, (pole.post_number, station)
            checked += 1
    assert checked > len(poles)


@pytest.fixture
def ezdxf():
    return pytest.importorskip('ezdxf')


def entities(doc, kind, layer):
    return [e for e in doc.modelspace() if e.dxftype() == kind and e.dxf.layer == layer]


def test_plan_matches_pole_and_wire_data(ezdxf):
    from core.alignment.alignment import as_alignment
    from core.drawing.plan_profile import draw_plan
    from core.model_rebuilder import alignment_for
    runner = run_case(airjoint_type='double_pole')
    doc = draw_plan(runner, DrawingSettings())
    poles = [p for ps in runner.poledata.values() for p in ps]
    units = [u for p in poles for u in pole_units.units(p)]
    assert len(entities(doc, 'CIRCLE', '전주')) == len(units)                         # 복주는 2개
    assert len(entities(doc, 'LINE', '브래킷')) == sum(len(pole_units.bracket_stations(p)) for p in poles)
    assert len(entities(doc, 'MTEXT', '전주번호')) == len(poles)
    assert len(entities(doc, 'LWPOLYLINE', '선형')) == len(runner.poledata)
    wires = sum(len(w.wires) for t, wds in runner.wire_data.items() for w in wds)
    wire_lines = sum(len(entities(doc, 'LINE', name)) for name in
                     ('전차선', '조가선', '무효선', '급전선', '보호선', '흐름방지선', '기타전선'))
    assert wire_lines == wires
    # 본선 첫 경간 전차선 = 선형에서 편위만큼 떨어진 두 지지점
    al = as_alignment(alignment_for(runner, 'main'))
    pole = runner.poledata['main'][0]
    w = next(x for x in runner.wire_data['main'][0].wires if x.label == '전차선')
    start, end = al.offset_point(pole.pos, w.offset[0]), al.offset_point(pole.next_pos, w.end_point[0])
    assert any(math.dist(tuple(e.dxf.start)[:2], start) < 1e-6 and math.dist(tuple(e.dxf.end)[:2], end) < 1e-6
               for e in entities(doc, 'LINE', '전차선'))
    # 전주 정보는 선로 바깥쪽 (본선·상선 글자가 겹치지 않음)
    texts = {round(e.dxf.insert.x, 3) for e in entities(doc, 'MTEXT', '전주번호')}
    assert len(texts) > 2


def test_profile_heights_and_masts(ezdxf):
    from core.drawing.plan_profile import draw_profile
    runner = run_case(airjoint_type='double_pole')
    settings = DrawingSettings(plan_scale=1000, profile_v_scale=100)                 # 높이 10배
    doc = draw_profile(runner, 'main', settings)
    poles = runner.poledata['main']
    assert len(entities(doc, 'LWPOLYLINE', '전주')) == sum(
        1 for p in poles for u in pole_units.units(p)
        if (p.twin.mast if u.which == pole_units.REAR else p.mast) is not None)
    pole = poles[0]
    w = next(x for x in runner.wire_data['main'][0].wires if x.label == '전차선')
    line = next(e for e in entities(doc, 'LINE', '전차선') if abs(e.dxf.start.x - pole.pos) < 1e-9)
    assert line.dxf.start.y == pytest.approx((pole.z + w.offset[1]) * 10)
    assert line.dxf.end.x == pole.next_pos
    messenger = next(e for e in entities(doc, 'LINE', '조가선') if abs(e.dxf.start.x - pole.pos) < 1e-9)
    system = runner.dataprocessor.get_system_height(pole.structure)
    assert messenger.dxf.start.y == pytest.approx((pole.z + w.offset[1] + system) * 10)
    # 전주 정보는 세로 글자
    assert all(e.dxf.rotation == 90 for e in entities(doc, 'MTEXT', '전주번호'))


def test_export_files_and_headless(ezdxf, tmp_path):
    from core.drawing import export_drawings
    runner = run_case()
    files = export_drawings(runner, str(tmp_path / 'dwg'), DrawingSettings())
    assert [os.path.basename(f) for f in files] == ['평면도.dxf', '종단면도_본선.dxf', '종단면도_상선.dxf']
    doc = ezdxf.readfile(files[0])
    assert doc.units == ezdxf.units.M and 'KOREAN' in doc.styles
    single = run_case('synthetic_single_250')
    assert len(export_drawings(single, str(tmp_path / 'single'))) == 2
    out = tmp_path / 'hl'
    assert headless.main(['--config', os.path.join(CASES, 'synthetic_single_250', 'case.json'), '--out', str(out),
                          '--dxf']) == 0
    assert (out / '평면도.dxf').exists() and (out / '종단면도_본선.dxf').exists()
