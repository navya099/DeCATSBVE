"""처리 오류(빠진 전주·전선)를 출력만 하고 넘어가지 않고 runner 에 모아 화면에 알리는지: python -m pytest tests"""
import contextlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bve.bvecsv import BVECSV  # noqa: E402
from core.model_rebuilder import rebuild  # noqa: E402
from tools import headless  # noqa: E402

CASE = os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_single_250', 'case.json')


def run(monkeypatch=None):
    runner = headless.build_runner(headless.load_config(CASE))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return runner


def test_no_errors_on_normal_run():
    runner = run()
    assert runner.pole_errors == [] and runner.wire_errors == [] and runner.processing_errors() == []


def test_pole_creation_failure_is_reported(monkeypatch):
    from core.airjoint import airjoint_processor
    def boom(pole, *a, **k):
        raise RuntimeError('테스트 실패')
    monkeypatch.setattr(airjoint_processor.AirJointProcessor, 'process', staticmethod(boom))
    runner = run()
    assert len(runner.pole_errors) == 5                                     # 에어조인트 전주 5개가 빠짐
    assert all('전주 생성 실패' in e and '테스트 실패' in e for e in runner.pole_errors)
    assert runner.processing_errors()[:5] == runner.pole_errors


def test_wire_failure_is_reported_and_cleared_on_rebuild(monkeypatch):
    from core.wire import section_handler
    runner = run()
    original = section_handler.WireSectionHandler.run
    target = runner.poledata['main'][10].pos

    def flaky(self, pole, *a, **k):
        if pole.pos == target:
            raise RuntimeError('전선 테스트 실패')
        return original(self, pole, *a, **k)
    monkeypatch.setattr(section_handler.WireSectionHandler, 'run', flaky)
    with contextlib.redirect_stdout(io.StringIO()):
        rebuild(runner)
    assert len(runner.wire_errors) == 1 and f'{target}m' in runner.wire_errors[0]
    monkeypatch.setattr(section_handler.WireSectionHandler, 'run', original)
    with contextlib.redirect_stdout(io.StringIO()):
        rebuild(runner)
    assert runner.wire_errors == []                                          # 재계산마다 새로 계산


def test_csv_missing_lines_are_reported():
    runner = run()
    poles = runner.poledata['main']
    poles[3].brackets = None                                                 # 브래킷 줄을 쓰다 실패
    saver = BVECSV(poles, runner.wire_data['main'], 0)
    with contextlib.redirect_stdout(io.StringIO()):
        saver.create_pole_csv()
        saver.create_wire_csv()
    assert any(f'{poles[3].pos}m 전주 CSV' in e for e in saver.errors)
    with contextlib.redirect_stdout(io.StringIO()):
        saver.create_pole_csv()                                              # 다시 만들어도 중복 누적 안 됨
    assert sum('전주 CSV' in e for e in saver.errors) == 1


def test_legacy_runner_without_error_fields():
    runner = run()
    del runner.pole_errors, runner.wire_errors
    assert runner.processing_errors() == []
