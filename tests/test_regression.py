"""출력 회귀 테스트: python -m pytest tests

- tests/regression_cases/*/case.json : 저장소에 포함된 합성 노선 케이스 (항상 실행)
- 환경변수 DECATSBVE_REGRESSION_CASES : 실제 노선 케이스 폴더들 (os.pathsep 구분, 각 폴더에 case.json +
  expected/). 노선 데이터는 저장소에 커밋하지 않고 로컬에서만 사용한다.
      Windows: set DECATSBVE_REGRESSION_CASES=D:\\regression\\충남선_250;D:\\regression\\도시철도_복선
기준 출력 갱신(의도한 변경일 때만): python -m tools.regression record <케이스 폴더>
"""
import glob
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import regression  # noqa: E402

BUILTIN = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(ROOT, 'tests', 'regression_cases', '*', 'case.json')))
EXTERNAL = [p for p in os.environ.get('DECATSBVE_REGRESSION_CASES', '').split(os.pathsep) if p.strip()]


@pytest.mark.parametrize('case_dir', BUILTIN + EXTERNAL, ids=lambda p: os.path.basename(os.path.normpath(p)))
def test_output_matches_expected(case_dir):
    ok, report = regression.check(case_dir)
    assert ok, '\n'.join(report)


def test_builtin_cases_exist():
    assert len(BUILTIN) >= 3


def test_check_detects_changed_output(tmp_path):
    """기준 출력이 바뀌면 실패해야 한다 (비교기가 실제로 비교하는지)"""
    src = os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_double_rail_150')
    case = tmp_path / 'case'
    shutil.copytree(src, case)
    # 상대경로 입력이 그대로 동작하도록 공유 노선 폴더도 같은 위치 관계로 복사
    shutil.copytree(os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_route'), tmp_path / 'synthetic_route')
    wire = case / 'expected' / 'sub_wire.txt'
    lines = wire.read_text(encoding='utf-8').splitlines(keepends=True)
    idx = next(i for i, l in enumerate(lines) if '.freeobj' in l)
    head, sep, tail = lines[idx].partition(';')
    lines[idx] = head + sep + tail.replace(';', ';9', 1)  # 숫자 하나 변조
    wire.write_text(''.join(lines), encoding='utf-8')
    ok, report = regression.check(str(case))
    assert not ok
    assert any('sub_wire.txt' in r for r in report)


def test_compare_lines_tolerance():
    assert regression.compare_lines(['1.0000001,a;2\n'], ['1.0000002,a;2\n'], 1e-6) == []
    assert regression.compare_lines(['1.0,a\n'], ['1.1,a\n'], 1e-6)
    assert regression.compare_lines(['1.0,a\n'], ['1.0,b\n'], 1e-6)
    assert regression.compare_lines(['x\n'], ['x\n', 'y\n'], 1e-6)
