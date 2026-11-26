"""데이터셋 편집 (core.dataset_edit) 테스트: python -m pytest tests"""
import contextlib
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.dataset_edit import DatasetDocument  # noqa: E402
from dataset.dataset_manager import get_standard_dataset_paths  # noqa: E402
from tools import headless  # noqa: E402

CASE = os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_single_250', 'case.json')


@pytest.fixture
def doc():
    return DatasetDocument.from_standard(250)


def errors(d):
    return [p for p in d.validate() if p.level == 'error']


@pytest.mark.parametrize('speed', [150, 250, 350])
def test_standard_datasets_validate(speed):
    d = DatasetDocument.from_standard(speed)
    assert d.is_standard and errors(d) == []
    warnings = [p.where for p in d.validate() if p.level == 'warning']
    assert not any('에어섹션' in w for w in warnings)  # 모든 표준에 에어섹션 브래킷 인덱스 있음


def test_set_value_keeps_types(doc):
    assert doc.set(('mast', 'gauge', '토공'), '3.2') == 3.2
    assert doc.set(('mast', 'index', '일반개소', '토공'), '1371') == 1371
    assert doc.set(('mast', 'foundation', '터널'), '') is None          # 비우기 = null (인덱스 없음)
    assert doc.set(('design', 'prefix'), '시험용') == '시험용'
    with pytest.raises(ValueError):
        doc.set(('mast', 'gauge', '토공'), '세미터')                      # 숫자 자리에 문자
    with pytest.raises(ValueError):
        doc.set(('mast', 'gauge'), '3')                                  # 묶음에 값
    with pytest.raises(KeyError):
        doc.set(('mast', 'gauge', '없는구조물'), '3')
    assert doc.dirty
    assert ('mast', 'gauge', '토공') in doc.changed_paths()
    doc.reset_to_template(('mast', 'gauge', '토공'))
    assert doc.get(('mast', 'gauge', '토공')) == 3
    assert ('mast', 'gauge', '토공') not in doc.changed_paths()


def test_add_and_remove_keys(doc):
    doc.add_key(('wire', 'offset'), 'Extra', '{}')
    doc.add_key(('wire', 'offset', 'Extra'), '부급전선', '1.5')
    assert doc.get(('wire', 'offset', 'Extra', '부급전선')) == 1.5
    with pytest.raises(ValueError):
        doc.add_key(('wire', 'offset'), 'Extra')                          # 중복
    doc.remove_key(('wire', 'offset', 'Extra'))
    with pytest.raises(ValueError):
        doc.remove_key(('mast', 'gauge', '토공'))                          # 필수 항목


def test_validation_finds_problems(doc):
    del doc.data['bracket']['index']['일반개소']['토공']['I']
    doc.data['wire']['system_height']['교량'] = '1.2m'
    del doc.spans['보호선']
    doc.spans['급전선'].loc[1, '길이'] = doc.spans['급전선'].loc[0, '길이']
    where = {p.where for p in errors(doc)}
    assert 'bracket.index.일반개소.토공.I' in where                         # 필수 항목 누락 + 실제 조회 실패
    assert 'wire.system_height.교량' in where                               # 형식 오류
    assert '경간표:보호선' in where and '경간표:급전선' in where


def test_save_rules_and_custom_run(doc, tmp_path):
    with pytest.raises(ValueError):
        doc.save()                                                          # 표준(config/) 덮어쓰기 금지
    json_path, xlsx_path = tmp_path / 'my.json', tmp_path / 'my_span.xlsx'

    # 변경 없이 저장한 커스텀 = 표준과 같은 출력
    doc.save(str(json_path), str(xlsx_path))
    assert not doc.dirty and not doc.is_standard
    base_cfg = headless.load_config(CASE)
    custom_cfg = dict(base_cfg, custom_json=str(json_path), custom_spandata=str(xlsx_path))
    out = {}
    for name, cfg in (('standard', base_cfg), ('custom', custom_cfg)):
        with contextlib.redirect_stdout(io.StringIO()):
            headless.run(cfg, str(tmp_path / name))
        out[name] = (tmp_path / name / 'main_pole.txt').read_text(encoding='utf-8')
    assert out['custom'] == out['standard']

    # 게이지를 바꿔 저장 → 실행 결과에 반영
    reloaded = DatasetDocument.load(str(json_path), str(xlsx_path))
    reloaded.set(('mast', 'gauge', '토공'), '3.4')
    reloaded.save()
    with contextlib.redirect_stdout(io.StringIO()):
        headless.run(custom_cfg, str(tmp_path / 'changed'))
    changed = (tmp_path / 'changed' / 'main_pole.txt').read_text(encoding='utf-8')
    assert ';-3.4;' in changed and changed != out['standard']

    # 검사 오류가 있으면 저장 안 함 (파일 그대로)
    before = json_path.read_text(encoding='utf-8')
    del reloaded.data['mast']['gauge']['교량']
    with pytest.raises(ValueError):
        reloaded.save()
    assert json_path.read_text(encoding='utf-8') == before


def test_span_editing(doc):
    sheet = '토공전차선'
    n = len(doc.spans[sheet])
    row = doc.add_span_row(sheet)
    assert len(doc.spans[sheet]) == n + 1 and doc.spans[sheet].loc[row, '길이'] == doc.spans[sheet]['길이'].max()
    doc.set_span_cell(sheet, row, '인덱스', '9999')
    assert doc.to_dataset()['span_data'][sheet][doc.spans[sheet].loc[row, '길이']] == 9999
    with pytest.raises(ValueError):
        doc.set_span_cell(sheet, row, '길이', '오십')
    doc.remove_span_row(sheet, row)
    assert len(doc.spans[sheet]) == n


def test_template_for_unsupported_speed(doc):
    doc.set(('design', 'speed'), '200')
    d2 = DatasetDocument(doc.data, doc.spans)
    assert d2.template_speed == 250
    assert any(p.where == 'design.speed' and p.level == 'warning' for p in d2.validate())


def test_standard_paths_untouched():
    json_path, _ = get_standard_dataset_paths(250)
    before = open(json_path, encoding='utf-8').read()
    d = DatasetDocument.from_standard(250)
    d.set(('mast', 'gauge', '토공'), '9')
    assert open(json_path, encoding='utf-8').read() == before


def test_equipment_indices_from_dataset():
    """장력장치·지선·인류장치·장간애자·흐름방지장치·봉강지선 인덱스를 데이터셋에서 (이전: 코드에 고정)"""
    import contextlib
    import io
    from tools import headless
    from core import section_edit as se
    from core.model_rebuilder import alignment_for, rebuild
    cfg = headless.load_config(os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_single_250', 'case.json'))
    runner = headless.build_runner(cfg)
    custom = {'장력장치': 9101, '지선': 9102, '인류장치': 9103, '장간애자': 9104, '흐름방지장치': 9105, '봉강지선': 9106}
    runner.dataprocessor.dataset['equipment'] = custom
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
        poles = runner.poledata['main']
        start = next(poles[i] for i in range(20, len(poles) - 8)
                     if all(poles[j].section is None and poles[j].flowstop is None for j in range(i, i + 8)))
        se.apply_add(runner, se.plan_add(runner, 'main', start.pos, 'airsection_double'), alignment_for)
        rebuild(runner)
        fs = next(poles[i] for i in range(3, len(poles) - 3)
                  if all(poles[j].section is None and poles[j].flowstop is None for j in range(i, i + 3)))
        se.apply_add(runner, se.plan_add(runner, 'main', fs.pos, 'flowstop'), alignment_for)
        rebuild(runner)
    used = {e.index for p in poles for e in p.equipments}
    insulators = {i.index for w in runner.wire_data['main'] for i in (w.insulators or [])}
    assert {9101, 9102, 9103, 9105, 9106} <= used and 9104 in insulators
    assert not ({1247, 682, 679, 678} & (used | insulators))
    # 구버전 커스텀 데이터셋(equipment 없음) → 이전 값
    del runner.dataprocessor.dataset['equipment']
    assert runner.dataprocessor.get_equipment_index('장력장치') == 1247
