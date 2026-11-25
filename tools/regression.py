"""출력 회귀 비교: 기준 출력(expected/)을 기록하고, 현재 코드 출력과 비교

케이스 폴더 구성:
    <case>/case.json     tools.headless 설정 (+ 선택: "verify": {"main_max_cm": 0.1, "sub_max_cm": 0.1})
    <case>/expected/     record 로 생성되는 기준 출력 (main/sub _pole.txt, _wire.txt, summary.json)

사용 예:
    python -m tools.regression check tests/regression_cases/synthetic_single
    python -m tools.regression check D:/regression/충남선_250 D:/regression/도시철도_복선
    python -m tools.regression record D:/regression/충남선_250     # 의도한 변경 후 기준 갱신

비교 규칙:
    - 줄 수, 문자열 부분은 정확히 일치
    - 숫자는 허용오차(--tol, 기본 1e-6) 이내면 일치 (OS/파이썬 버전별 부동소수점 끝자리 차이 무시)
    - summary.json: 트랙별 전주/경간 수, 처리 오류 수
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import headless, verify  # noqa: E402

COMPARED_FILES = ('main_pole.txt', 'main_wire.txt', 'sub_pole.txt', 'sub_wire.txt')
NUMBER = re.compile(r'[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?')


def _tokens(line):
    """(문자열 조각들, 숫자들)"""
    return NUMBER.split(line), [float(m) for m in NUMBER.findall(line)]


def compare_lines(expected, actual, tol):
    """차이 목록 [(줄번호, 기대, 실제, 사유)]"""
    diffs = []
    if len(expected) != len(actual):
        diffs.append((0, f'{len(expected)}줄', f'{len(actual)}줄', '줄 수 다름'))
    for i, (e, a) in enumerate(zip(expected, actual), start=1):
        if e == a:
            continue
        (es, en), (as_, an) = _tokens(e), _tokens(a)
        if es != as_ or len(en) != len(an):
            diffs.append((i, e.rstrip('\n'), a.rstrip('\n'), '내용 다름'))
            continue
        worst = max(abs(x - y) for x, y in zip(en, an))
        if worst > tol:
            diffs.append((i, e.rstrip('\n'), a.rstrip('\n'), f'숫자 차이 {worst:.3g}'))
    return diffs


def _summary_key(summary):
    return {'tracks': summary.get('tracks', {}), 'error_count': len(summary.get('errors', []))}


def load_case(case_dir):
    return headless.load_config(os.path.join(case_dir, 'case.json'))


def run_case(case_dir, out_dir):
    cfg = load_case(case_dir)
    summary = headless.run(cfg, out_dir)
    return cfg, summary


def record(case_dir):
    """현재 코드 출력으로 expected/ 갱신"""
    expected = os.path.join(case_dir, 'expected')
    with tempfile.TemporaryDirectory() as tmp:
        _, summary = run_case(case_dir, tmp)
        if os.path.isdir(expected):
            shutil.rmtree(expected)
        os.makedirs(expected)
        for name in COMPARED_FILES:
            src = os.path.join(tmp, name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(expected, name))
        with open(os.path.join(expected, 'summary.json'), 'w', encoding='utf-8') as f:
            json.dump(_summary_key(summary), f, ensure_ascii=False, indent=2)
    return summary


def check(case_dir, tol=1e-6, keep_output=None):
    """기준 출력과 비교. (성공 여부, 보고 문자열 목록)"""
    expected = os.path.join(case_dir, 'expected')
    if not os.path.isdir(expected):
        return False, [f'기준 출력 없음: {expected} (먼저 record 실행)']
    report = []
    ok = True
    tmp = keep_output or tempfile.mkdtemp()
    try:
        cfg, summary = run_case(case_dir, tmp)

        with open(os.path.join(expected, 'summary.json'), encoding='utf-8') as f:
            exp_summary = json.load(f)
        if _summary_key(summary) != exp_summary:
            ok = False
            report.append(f'summary 다름: 기대 {exp_summary} / 실제 {_summary_key(summary)}')

        for name in COMPARED_FILES:
            exp_path, act_path = os.path.join(expected, name), os.path.join(tmp, name)
            if not os.path.exists(exp_path) and not os.path.exists(act_path):
                continue
            if os.path.exists(exp_path) != os.path.exists(act_path):
                ok = False
                report.append(f'{name}: 파일 유무 다름 (기대 {os.path.exists(exp_path)}, 실제 {os.path.exists(act_path)})')
                continue
            with open(exp_path, encoding='utf-8') as f:
                exp_lines = f.readlines()
            with open(act_path, encoding='utf-8') as f:
                act_lines = f.readlines()
            diffs = compare_lines(exp_lines, act_lines, tol)
            if diffs:
                ok = False
                report.append(f'{name}: {len(diffs)}곳 다름')
                for line_no, e, a, why in diffs[:5]:
                    report.append(f'    {line_no}행 ({why})\n      기대: {e}\n      실제: {a}')

        limits = cfg.get('verify') or {}
        if limits:
            sub_rail = cfg.get('sub_rail')
            rail_info = cfg.get('rail_info') or os.path.join(os.path.dirname(cfg['coord']), 'rail_info.txt')
            geo = verify.verify(tmp, cfg['coord'], rail_info if sub_rail is not None else None, sub_rail)
            for track, r in geo.items():
                limit = limits.get(f'{track}_max_cm')
                if limit is not None and r['max_cm'] > limit:
                    ok = False
                    report.append(f'[{track}] 전선 기하 오차 최대 {r["max_cm"]:.2f}cm > 허용 {limit}cm, 최악: {r["worst"][:2]}')
                else:
                    report.append(f'[{track}] 전선 {r["wires"]}개 기하 오차 최대 {r["max_cm"]:.3f}cm')
    finally:
        if keep_output is None:
            shutil.rmtree(tmp, ignore_errors=True)
    return ok, report


def main(argv=None):
    ap = argparse.ArgumentParser(description='DeCATSBVE 출력 회귀 비교')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_check = sub.add_parser('check', help='기준 출력과 비교')
    p_check.add_argument('cases', nargs='+')
    p_check.add_argument('--tol', type=float, default=1e-6)
    p_check.add_argument('--keep', help='실제 출력 보관 폴더 (케이스별 하위 폴더)')
    p_record = sub.add_parser('record', help='현재 출력으로 기준 갱신')
    p_record.add_argument('cases', nargs='+')
    a = ap.parse_args(argv)

    failed = 0
    for case in a.cases:
        name = os.path.basename(os.path.normpath(case))
        if a.cmd == 'record':
            s = record(case)
            print(f'[기록] {name}: {s["tracks"]}, 처리 오류 {len(s["errors"])}건')
            continue
        keep = os.path.join(a.keep, name) if a.keep else None
        ok, report = check(case, a.tol, keep)
        print(f'[{"통과" if ok else "실패"}] {name}')
        for line in report:
            print('   ', line)
        failed += not ok
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
