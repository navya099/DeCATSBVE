"""복주(複柱) 에어조인트 테스트: python -m pytest tests

복주 = 2·3·4호주 위치에 전주 2개(브래킷 1개씩). 브래킷·전선 규칙은 단주 에어조인트와 같고,
전주만 측점 ± 간격/2 에 따로 선다 (데이터셋 airjoint.double_pole: spacing, feeder).
"""
import contextlib
import io
import os
import pickle
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import section_edit as se  # noqa: E402
from core.model_rebuilder import alignment_for, normalize, rebuild  # noqa: E402
from core.pole import pole_edit as pe  # noqa: E402
from enums.section_type import AIRJOINT_DOUBLE_POLE_SEQUENCE, DOUBLE_POLE_PAIRED_ROLES, SectionType  # noqa: E402
from tools import headless  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')


def run_case(name='synthetic_single_250', **overrides):
    cfg = headless.load_config(os.path.join(CASES, name, 'case.json'))
    cfg.update(overrides)
    runner = headless.build_runner(cfg)
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


def without_comments(text):
    return [line for line in text.splitlines() if not line.startswith(',;')]


def freeobj_positions(text, index):
    return [float(m.group(1)) for m in re.finditer(rf'^([\d.]+),\.freeobj \d+;{index};', text, re.M)]


def paired(poles):
    return [p for p in poles if p.section is not None and p.section.is_double_pole
            and p.section.role in DOUBLE_POLE_PAIRED_ROLES]


@pytest.mark.parametrize('case', ['synthetic_single_250', 'synthetic_double_rail_150'])
def test_auto_double_pole_layout(case, tmp_path):
    single = run_case(case)
    double = run_case(case, airjoint_type='double_pole')
    for track, poles in double.poledata.items():
        kinds = {i.kind.id for i in se.find_sections(double, track) if i.kind and i.kind.category == 'airjoint'}
        assert kinds == {'airjoint_2span_double_pole'}
        assert [p.pos for p in poles] == [p.pos for p in single.poledata[track]]   # 지지점(경간)은 단주와 같음
        assert paired(poles)
        for p in poles:
            if p in paired(poles):
                assert p.twin is not None and p.twin.spacing == 1.0
                assert [b.on_twin for b in p.brackets] == [False, True]               # 앞 = 첫 브래킷, 뒤 = 둘째
                assert all(e.type != '평행틀' for e in p.equipments + p.twin.equipments)
                feeders = [e for e in p.equipments + p.twin.equipments if e.type == '급전선설비']
                assert len(feeders) == 2                                               # 기본: 두 전주 모두
                if p.structure != '터널':
                    assert p.mast.index == double.dataprocessor.get_mast_index(p.structure, None)  # 일반개소 기둥
                    assert p.twin.mast.index == p.mast.index
            else:
                assert p.twin is None
    a, b = outputs(single, tmp_path, 'single'), outputs(double, tmp_path, 'double')
    for name in a:
        if name.endswith('_wire.txt'):
            assert without_comments(a[name]) == without_comments(b[name])              # 전선은 단주와 같음


def test_double_pole_csv_positions(tmp_path):
    runner = run_case(airjoint_type='double_pole')
    poles = runner.poledata['main']
    pole = next(p for p in paired(poles) if p.structure != '터널')
    text = outputs(runner, tmp_path, 'out')['main_pole.txt']
    mast_positions = freeobj_positions(text, pole.mast.index)
    assert pole.pos - 0.5 in mast_positions and pole.pos + 0.5 in mast_positions
    br_front, br_rear = pole.brackets
    assert pole.pos - 0.5 in freeobj_positions(text, br_front.index)
    assert pole.pos + 0.5 in freeobj_positions(text, br_rear.index)


def test_rebuild_reproduces_double_pole_output(tmp_path):
    runner = run_case('synthetic_double_rail_150', airjoint_type='double_pole')
    first = outputs(runner, tmp_path, 'first')
    quiet_rebuild(runner)
    assert outputs(runner, tmp_path, 'rebuilt') == first


def test_section_editor_add_remove_double_pole(tmp_path):
    runner = run_case()
    auto = outputs(runner, tmp_path, 'auto')
    poles = runner.poledata['main']
    kind = se.SECTION_KINDS['airjoint_2span_double_pole']
    assert kind.n_poles == 5 and kind.sequence == AIRJOINT_DOUBLE_POLE_SEQUENCE
    start = next(poles[i] for i in range(20, len(poles) - 5)
                 if all(poles[j].section is None and poles[j].flowstop is None for j in range(i, i + 5)))
    se.apply_add(runner, se.plan_add(runner, 'main', start.pos, kind.id), alignment_for)
    quiet_rebuild(runner)
    found = next(i for i in se.find_sections(runner, 'main') if i.start_pos == start.pos)
    assert found.kind.id == kind.id
    assert [p.twin is not None for p in found.poles] == [False, True, True, True, False]
    # 복주 에어조인트 사이에도 흐름방지가 계산됨 (단주와 같은 규칙)
    assert any(p.flowstop is not None for p in poles)
    se.remove(runner, found, alignment_for)
    quiet_rebuild(runner)
    assert all(p.twin is None for p in found.poles)
    assert outputs(runner, tmp_path, 'removed') == auto


def test_feeder_front_only_and_spacing_option():
    runner = run_case()
    runner.dataprocessor.dataset['airjoint']['double_pole'] = {'spacing': 2.0, 'feeder': 'front'}
    poles = runner.poledata['main']
    start = next(poles[i] for i in range(20, len(poles) - 5)
                 if all(poles[j].section is None and poles[j].flowstop is None for j in range(i, i + 5)))
    se.apply_add(runner, se.plan_add(runner, 'main', start.pos, 'airjoint_2span_double_pole'), alignment_for)
    for p in paired(poles):
        assert p.twin.spacing == 2.0 and p.station_offsets == (-1.0, 1.0)
        assert [e.type for e in p.twin.equipments] == []
        assert sum(e.type == '급전선설비' for e in p.equipments) == 1


@pytest.mark.parametrize('bad', [{'spacing': 0}, {'feeder': 'middle'}])
def test_invalid_double_pole_settings(bad):
    runner = run_case()
    runner.dataprocessor.dataset['airjoint']['double_pole'] = {'spacing': 1.0, 'feeder': 'both', **bad}
    with pytest.raises(ValueError):
        runner.dataprocessor.get_double_pole_settings()
    del runner.dataprocessor.dataset['airjoint']['double_pole']          # 구버전 커스텀 데이터셋 → 기본값
    assert runner.dataprocessor.get_double_pole_settings() == {'spacing': 1.0, 'feeder': 'both'}


def test_pole_editor_twin_components():
    from xref_module.index_libmgr import IndexLibrary
    import pandas as pd
    runner = run_case(airjoint_type='double_pole')
    pole = next(p for p in paired(runner.poledata['main']) if p.structure != '터널')
    runner.idxlib = IndexLibrary(pd.DataFrame([{'인덱스': 9001, '파일명': '테스트장비', '경로': 'x.csv'}]))
    rows = {r.key: r for r in pe.components(pole)}
    assert {'twin/mast', 'twin/base', 'twin/eq:0'} <= set(rows)
    assert rows['br:0'].detail.endswith('(앞 전주)') and rows['br:1'].detail.endswith('(뒤 전주)')
    assert pe.component_pole(pole, 'br:1') == 1 and pe.component_pole(pole, 'twin/eq:0') == 1
    assert pe.component_pole(pole, 'br:0') == 0 and pe.component_pole(pole, 'mast') == 0
    # 두 번째 전주 장비 수정·추가·삭제
    pe.set_component(runner, pole, 'twin/eq:0', offset=(-3.3, 0.5))
    assert tuple(pole.twin.equipments[0].offset) == (-3.3, 0.5)
    key = pe.add_component(runner, pole, 'eq', index=9001, offset=(1, 1), parent='twin')
    assert key == f'twin/eq:{len(pole.twin.equipments) - 1}' and pole.twin.equipments[-1].index == 9001
    pe.remove_component(pole, key)
    assert all(e.index != 9001 for e in pole.twin.equipments)
    with pytest.raises(ValueError):
        pe.remove_component(pole, 'twin/mast')
    # 건식게이지 변경: 두 번째 전주 기둥도 따라감
    old = pole.gauge
    new = round(old * 1.1, 3)
    pe.set_gauge(runner, pole, new, alignment_for(runner, 'main'))
    assert pole.twin.mast.offset[0] == pytest.approx(new) and pole.mast.offset[0] == pytest.approx(new)
    # 자동 구성으로 되돌리기: 복주 유지
    pe.regenerate(runner, pole, alignment_for(runner, 'main'))
    assert pole.twin is not None and [b.on_twin for b in pole.brackets] == [False, True]


def test_save_load_and_legacy_objects(tmp_path):
    from file_io.filemanager import load_runner, save_runner
    runner = run_case(airjoint_type='double_pole')
    expected = outputs(runner, tmp_path, 'before')
    path = tmp_path / 'runner.dat'
    save_runner(runner, str(path))
    loaded = load_runner(str(path))
    normalize(loaded)
    assert loaded.airjoint_type == 'double_pole'
    assert any(p.twin is not None for p in loaded.poledata['main'])
    quiet_rebuild(loaded)
    assert outputs(loaded, tmp_path, 'after') == expected
    # 구버전 객체(twin·on_twin 속성 없이 저장됨)도 기본값으로 동작
    pole = runner.poledata['main'][0]
    state = pickle.loads(pickle.dumps(pole))
    state.__dict__.pop('twin')
    for b in state.brackets:
        b.__dict__.pop('on_twin')
    assert state.twin is None and all(b.on_twin is False for b in state.brackets)


def test_section_type_roles():
    assert SectionType.AJD_2.role is SectionType.AJ_2 and SectionType.AJD_2.is_airjoint
    assert SectionType.AJD_2.is_double_pole and not SectionType.AJ_2.is_double_pole
    assert SectionType.AS1_1.role is SectionType.AS1_1
    assert SectionType.parse('복주 에어조인트 중간주 (3호주)') is SectionType.AJD_MIDDLE
