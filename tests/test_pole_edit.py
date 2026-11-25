"""전주 상세 편집 (core.pole.pole_edit) 테스트: python -m pytest tests

전주 상세 편집기(gui/pole_assembler.py)가 부르는 것과 같은 API 로 편집한 뒤 rebuild 하여 검증한다.
"""
import contextlib
import io
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.model_rebuilder import alignment_for, normalize, rebuild  # noqa: E402
from core.pole import pole_edit as pe  # noqa: E402
from tools import headless  # noqa: E402
from tools.verify import load_main_line, wire_errors  # noqa: E402
from xref_module.index_libmgr import IndexLibrary  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')
LIB = [(1370, '강관주-P10-9m'), (1371, '강관주-P10-9m-교량'), (1375, '강관주-P12-9m'), (623, '기초-토공'),
       (685, '가동브래킷용밴드3호_P10'), (1296, 'Cako250_I'), (1297, 'Cako250_O'), (1234, '급전선현수조립체'),
       (531, '평행틀1m'), (9001, '테스트장비'), (9002, '테스트피팅'), (679, '흐름방지장치_강관주용')]


def run_case(name='synthetic_single_250'):
    runner = headless.build_runner(headless.load_config(os.path.join(CASES, name, 'case.json')))
    runner.idxlib = IndexLibrary(pd.DataFrame([{'인덱스': i, '파일명': n, '경로': n + '.csv'} for i, n in LIB]))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return runner


def quiet_rebuild(runner):
    with contextlib.redirect_stdout(io.StringIO()):
        rebuild(runner)


def outputs(runner, tmp_path, tag):
    out = tmp_path / tag
    headless.write_outputs(runner, str(out), '')
    return {f.name: f.read_text(encoding='utf-8') for f in out.iterdir() if f.suffix == '.txt'}


def pole_block(runner, pole, track='main'):
    """CSV 에서 이 전주 블록의 freeobj 줄"""
    from bve.bvecsv import BVECSV
    with contextlib.redirect_stdout(io.StringIO()):
        lines = BVECSV([pole], [], track_index=0).create_pole_csv()
    return [l for l in lines if '.freeobj' in l]


@pytest.fixture
def setup():
    runner = run_case()
    poles = runner.poledata['main']
    i = next(k for k in range(3, len(poles) - 3) if all(poles[j].section is None for j in range(k - 2, k + 3)))
    return runner, poles, poles[i]


def row(pole, key):
    return next(r for r in pe.components(pole) if r.key == key)


def test_components_listing(setup):
    _, _, pole = setup
    rows = pe.components(pole)
    kinds = [r.kind for r in rows]
    assert kinds[0] == 'mast' and 'br' in kinds and 'eq' in kinds
    assert len({r.key for r in rows}) == len(rows)
    feeder = next(r for r in rows if r.kind == 'eq')
    assert feeder.detail == '급전선설비' and feeder.editable


def test_set_mast_by_name_or_index_keeps_pole_in_csv(setup):
    runner, _, pole = setup
    pe.set_component(runner, pole, 'mast', name='강관주-P12-9m')
    assert (pole.mast.name, pole.mast.index) == ('강관주-P12-9m', 1375)
    pe.set_component(runner, pole, 'mast', index=1371)
    assert pole.mast.name == '강관주-P10-9m-교량'
    assert isinstance(pole.mast.offset, tuple)  # 이전 버그: offset=게이지(숫자) → CSV 에서 기둥 이후 줄 누락
    quiet_rebuild(runner)
    assert any(';1371;' in l for l in pole_block(runner, pole))


def test_unknown_object_rejected_without_changes(setup):
    runner, _, pole = setup
    before = (pole.mast.name, pole.mast.index)
    with pytest.raises(ValueError):
        pe.set_component(runner, pole, 'mast', name='없는기둥')
    with pytest.raises(ValueError):
        pe.set_component(runner, pole, 'mast', index=123456)
    assert (pole.mast.name, pole.mast.index) == before


def test_offset_rotation_edit_and_persist_across_rebuild(setup):
    runner, poles, pole = setup
    pe.set_component(runner, pole, 'br:0', offset=(0.1, 0.2), rotation=3.0)
    quiet_rebuild(runner)
    other = poles[poles.index(pole) + 4]
    other.pos += 0  # 다른 편집으로 재계산
    quiet_rebuild(runner)
    assert row(pole, 'br:0').offset == (0.1, 0.2) and row(pole, 'br:0').rotation == 3.0


def test_add_and_remove_components(setup):
    runner, _, pole = setup
    n_br, n_eq = len(pole.brackets), len(pole.equipments)
    k_br = pe.add_component(runner, pole, 'br', name='Cako250_O', offset=(0, 0))
    k_fit = pe.add_component(runner, pole, 'fit', index=9002, parent=k_br)
    k_eq = pe.add_component(runner, pole, 'eq', name='테스트장비', offset=(pole.gauge, 1.0))
    k_acc = pe.add_component(runner, pole, 'acc', name='가동브래킷용밴드3호_P10', offset=(pole.gauge, 7.0))
    assert row(pole, k_fit).parent == k_br and row(pole, k_fit).name == '테스트피팅'
    assert row(pole, k_eq).detail == '기타장비'
    quiet_rebuild(runner)
    csv = pole_block(runner, pole)
    assert any(';9001;' in l for l in csv) and any(';9002;' in l for l in csv)

    pe.remove_component(pole, k_fit)
    pe.remove_component(pole, k_br)
    pe.remove_component(pole, k_eq)
    pe.remove_component(pole, k_acc)
    assert (len(pole.brackets), len(pole.equipments)) == (n_br, n_eq)  # 이전 버그: '-' 버튼이 데이터를 안 지움
    with pytest.raises(ValueError):
        pe.add_component(runner, pole, 'fit', index=9002, parent=None)
    with pytest.raises(ValueError):
        pe.remove_component(pole, 'mast')


def test_flowstop_equipment_read_only_and_not_duplicated(setup):
    runner, poles, pole = setup
    i = poles.index(pole)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.anticreeping_pr.add_manual_section('main', poles[i - 1].pos, poles[i + 1].pos, pole.pos)
    start = poles[i - 1]
    fs = next(r for r in pe.components(start) if r.detail == '흐름방지장치')
    assert not fs.editable
    with pytest.raises(ValueError):
        pe.set_component(runner, start, fs.key, rotation=0)
    with pytest.raises(ValueError):
        pe.remove_component(start, fs.key)
    # 다른 구성품을 편집하고 재계산해도 흐름방지장치가 중복되지 않음 (이전: '기타장비'로 저장돼 계속 쌓임)
    pe.set_component(runner, start, 'mast', offset=row(start, 'mast').offset)
    quiet_rebuild(runner)
    quiet_rebuild(runner)
    assert sum(e.type == '흐름방지장치' for e in start.equipments) == 1


def test_set_gauge_regenerates_components_and_coord(setup):
    runner, _, pole = setup
    old_coord, old = pole.coord, pole.gauge
    new = old * 1.2
    pe.set_gauge(runner, pole, new, alignment_for(runner, 'main'))
    quiet_rebuild(runner)
    assert pole.gauge == new and pole.coord != old_coord
    assert row(pole, 'mast').offset[0] == pytest.approx(new)
    assert all(r.offset[0] == pytest.approx(new) for r in pe.components(pole) if r.kind in ('base', 'acc'))
    line = load_main_line(os.path.join(CASES, 'synthetic_route', 'bve_coordinates.txt'))
    by_pos = {p.pos: p for p in runner.poledata['main']}
    rows = [dict(pos=wd.pos, next_pos=by_pos[wd.pos].next_pos, start=list(w.offset), end=list(w.end_point),
                 yaw=w.adjusted_angle, station=w.station, label=w.label, radius=0)
            for wd in runner.wire_data['main'] for w in wd.wires]
    assert wire_errors(rows, line)[0][0] < 1e-5  # 게이지를 따르는 AF/FPW 전선도 새 위치로
    with pytest.raises(ValueError):
        pe.set_gauge(runner, pole, -new, alignment_for(runner, 'main'))  # 좌우 변경 불가


def test_regenerate_restores_auto_output(setup, tmp_path):
    runner, _, pole = setup
    auto = outputs(runner, tmp_path, 'auto')
    pe.set_component(runner, pole, 'mast', name='강관주-P12-9m')
    pe.add_component(runner, pole, 'eq', name='테스트장비')
    pe.remove_component(pole, 'br:0')
    quiet_rebuild(runner)
    assert outputs(runner, tmp_path, 'edited') != auto
    pe.regenerate(runner, pole, alignment_for(runner, 'main'))
    quiet_rebuild(runner)
    assert outputs(runner, tmp_path, 'regenerated') == auto


def test_normalize_repairs_legacy_mast_offset(setup):
    runner, _, pole = setup
    complete = pole_block(runner, pole)
    pole.mast.offset = pole.gauge  # 이전 조립기 버그로 저장된 형태
    broken = pole_block(runner, pole)
    assert len(broken) < len(complete)  # 기둥 이후(기둥·밴드·기초·브래킷) 줄이 CSV 에서 빠짐
    normalize(runner)
    assert isinstance(pole.mast.offset, tuple) and pole.mast.offset[0] == pole.gauge
    assert pole_block(runner, pole) == complete
