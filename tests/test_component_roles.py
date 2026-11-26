"""구성품 역할(role/spec)·물량표: python -m pytest tests"""
import contextlib
import csv
import io
import os
import pickle
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import section_edit as se  # noqa: E402
from core.model_rebuilder import alignment_for, normalize, rebuild  # noqa: E402
from core.pole import pole_edit as pe  # noqa: E402
from enums.component_role import ComponentRole, infer_role, iter_components, known_indices  # noqa: E402
from tools import headless  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')


def run_case(name='synthetic_single_250', **overrides):
    cfg = headless.load_config(os.path.join(CASES, name, 'case.json'))
    cfg.update(overrides)
    runner = headless.build_runner(cfg)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
        poles = runner.poledata['main']
        for kind, k in (('airsection_single', 0), ('airsection_double', 1)):     # 에어섹션 구성품도 포함
            n = se.SECTION_KINDS[kind].n_poles
            free = [i for i in range(3, len(poles) - n) if all(poles[j].section is None for j in range(i, i + n))]
            se.apply_add(runner, se.plan_add(runner, 'main', poles[free[len(free) * (k + 1) // 3]].pos, kind),
                         alignment_for)
        rebuild(runner)
    return runner


def all_components(runner):
    return [(kind, obj) for poles in runner.poledata.values() for p in poles for kind, obj in iter_components(p)]


@pytest.mark.parametrize('case,aj', [('synthetic_single_250', 'single'), ('synthetic_double_rail_150', 'double_pole')])
def test_every_generated_component_has_role_and_inference_agrees(case, aj):
    runner = run_case(case, airjoint_type=aj)
    comps = all_components(runner)
    assert comps and all(getattr(o, 'role', '') for _, o in comps)
    roles = {o.role for _, o in comps}
    assert {ComponentRole.MAST, ComponentRole.FOUNDATION, ComponentRole.BRACKET, ComponentRole.BRACKET_F,
            ComponentRole.BRACKET_AJ, ComponentRole.FIT_STEADY, ComponentRole.FIT_MW, ComponentRole.FEEDER,
            ComponentRole.TENSION, ComponentRole.GUY} <= roles
    known = known_indices(runner.dataprocessor)
    for kind, obj in comps:                       # 구버전 데이터 추정이 자동 기록과 같음 (이름 없는 자리 제외)
        if not (getattr(obj, 'name', None) or getattr(obj, 'bracket_name', None) or getattr(obj, 'label', None)) \
                and getattr(obj, 'index', None) not in known:
            continue
        role, spec = infer_role(kind, obj, known)
        assert role == obj.role, (kind, obj)
    # 브래킷 형식(spec): 일반 I/O, 평행 개소 AJ I/O, 곡선당김금구 L/R
    for kind, obj in comps:
        if obj.role in (ComponentRole.BRACKET, ComponentRole.BRACKET_AJ):
            assert obj.spec in ('I', 'O')
        if obj.role == ComponentRole.FIT_STEADY:
            assert obj.spec in ('L', 'R')


def test_legacy_data_gets_roles_on_normalize():
    runner = run_case()
    legacy = pickle.loads(pickle.dumps(runner))
    for _, obj in all_components(legacy):        # 구버전: role/spec 속성 자체가 없음
        obj.__dict__.pop('role', None)
        obj.__dict__.pop('spec', None)
    assert all(getattr(o, 'role', '') == '' for _, o in all_components(legacy))   # 클래스 기본값
    normalize(legacy)
    restored = {(id(o), o.role) for _, o in all_components(legacy)}
    assert all(role for _, role in restored)
    before = [o.role for _, o in all_components(runner)]
    after = [o.role for _, o in all_components(legacy)]
    agree = sum(a == b for a, b in zip(before, after)) / len(before)
    assert agree == 1.0                            # 이름이 없어도 데이터셋 인덱스(금구·밴드·기둥)로 같은 역할


def test_added_components_and_rows_show_roles():
    import pandas as pd
    from xref_module.index_libmgr import IndexLibrary
    runner = run_case()
    runner.idxlib = IndexLibrary(pd.DataFrame([
        {'인덱스': 9001, '파일명': '테스트장비', '경로': 'x.csv'},
        {'인덱스': 9002, '파일명': '곡선당김금구R', '경로': 'y.csv'},
        {'인덱스': 9003, '파일명': '가동브래킷용밴드3호_P10', '경로': 'z.csv'}]))
    pole = next(p for p in runner.poledata['main'] if p.section is None and p.mast is not None)
    eq = pe.add_component(runner, pole, 'eq', index=9001, equipment_type='급전선설비')
    fit = pe.add_component(runner, pole, 'fit', index=9002, parent='br:0')
    acc = pe.add_component(runner, pole, 'acc', index=9003)
    br = pe.add_component(runner, pole, 'br', index=9001)
    rows = {r.key: r for r in pe.components(pole)}
    assert rows[eq].role == ComponentRole.FEEDER
    assert (rows[fit].role, rows[fit].spec) == (ComponentRole.FIT_STEADY, 'R')
    assert rows[acc].role == ComponentRole.BAND_BRACKET
    assert rows[br].role == ComponentRole.BRACKET and rows[br].spec == pole.base_type
    assert rows['mast'].role_text.startswith('기둥')


def test_bracket_abbreviations_in_drawing_labels():
    from core.drawing.plan_profile import _label_text
    runner = run_case()
    labels = {str(p.section): _label_text(p).split('\\P')[2] for p in runner.poledata['main'] if p.section}
    assert labels['에어조인트 (2호주)'] == 'F, AJ-I' and labels['에어조인트 중간주 (3호주)'] == 'AJ-I, AJ-O'
    assert labels['에어조인트 (4호주)'] == 'AJ-O, F'
    assert labels['에어섹션1구간_2호주'] == 'F, AS-I' and labels['에어섹션1구간_3호주'] == 'AS-O, AS-I'
    normal = next(p for p in runner.poledata['main'] if p.section is None)
    assert _label_text(normal).split('\\P')[2] == normal.base_type


def test_bill_of_quantities(tmp_path):
    from core.quantities import bill_of_quantities, write_bom_csv
    runner = run_case('synthetic_double_rail_150', airjoint_type='double_pole')
    rows = bill_of_quantities(runner)
    for track, key in (('본선', 'main'), ('상선', 'sub')):
        poles = runner.poledata[key]
        masts = sum(r.count for r in rows if r.track == track and r.role in ('기둥', '하수강') and r.category == '전주')
        units = sum(1 + (p.twin is not None and p.twin.mast is not None) for p in poles if p.mast is not None)
        hangers = sum(1 for p in poles for b in p.brackets for f in b.fittings
                      if f.role == ComponentRole.HANGER and f.index is not None)
        assert masts == units + hangers                   # 복주 뒤 전주·터널 하수강 포함
        wires = [r for r in rows if r.track == track and r.category == '전선']
        assert sum(r.count for r in wires) == sum(len([w for w in wd.wires if w.index is not None])
                                                  for wd in runner.wire_data[key])
        assert all(r.length > 0 for r in wires)
    path = write_bom_csv(rows, str(tmp_path / '물량표.csv'))
    with open(path, encoding='utf-8-sig') as f:
        data = list(csv.reader(f))
    assert data[0][:3] == ['트랙', '분류', '역할'] and len(data) == len(rows) + 1
