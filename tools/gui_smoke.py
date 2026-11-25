"""GUI 스모크 테스트: 실제 Tk 앱에서 편집 동작 후 테이블·배치도·전선·흐름방지가 서로 일치하는지 확인

    python -m tools.gui_smoke tests/regression_cases/synthetic_double_rail_150/case.json
    (Linux 화면 없는 환경: xvfb-run -a python -m tools.gui_smoke <case.json>)

창이 잠깐 열렸다 닫힌다. 전주 이동·삭제, 에어조인트 추가·제거, 흐름방지 수동 추가·삭제, 상선 편집을
편집기/배치도 함수로 직접 실행하고 단계마다 다음을 검사한다:
    테이블 행·측점 = 전주 데이터, 배치도 점 수 = 전주 수, 연속 전주마다 전선, 전선 기하 오차,
    흐름방지 태그 ↔ 장치 일치
사용자 PC 전용인 오브젝트 라이브러리 폴더 검사는 건너뛴다.
"""
import contextlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if len(sys.argv) != 2:
    sys.exit(__doc__)
case = sys.argv[1]
import xref_module.object_libraymgr as olm  # noqa: E402
olm.LibraryManager.scan_library = lambda self: None  # 사용자 PC 오브젝트 폴더 검사 생략
from tkinter import messagebox  # noqa: E402
messagebox.showerror = lambda *a, **k: print('  [messagebox]', a)
messagebox.showinfo = lambda *a, **k: None

from gui.maingui import AutoPoleApp  # noqa: E402
from tools import headless  # noqa: E402
from tools.verify import wire_errors, load_main_line, load_rail_line  # noqa: E402

app = AutoPoleApp()
app.update()
cfg = headless.load_config(case)
runner = headless.build_runner(cfg)
runner.log_widget = app.log_box
with contextlib.redirect_stdout(io.StringIO()):
    runner.run()
app.runner = runner
app._show_new_runner()
app.update()

ed, pl = app.editor, app.plotter
main_line = load_main_line(cfg['coord'])
sub_line = load_rail_line(cfg['rail_info'], cfg['sub_rail'], len(main_line)) if cfg.get('sub_rail') is not None else None
failures = []


def plotted_points():
    n = 0
    for coll in pl.ax.collections:
        if hasattr(coll, 'get_offsets') and coll.get_label() in ('본선 전주', '상선 전주'):
            n += len(coll.get_offsets())
    return n


def check(step):
    """테이블 행 = 전주 수, 배치도 점 = 전주 수, 전선 기하 오차, 흐름방지 장비·태그 일치"""
    app.update()
    poles = {t: runner.poledata[t] for t in runner.poledata}
    rows = {'main': len(ed.tree_main.get_children()), 'sub': len(ed.tree_sub.get_children())}
    total = sum(len(v) for v in poles.values())
    msgs = []
    for t, ps in poles.items():
        if rows[t] != len(ps):
            msgs.append(f'{t} 테이블 {rows[t]}행 ≠ 전주 {len(ps)}')
        # 테이블 측점 = 데이터 측점
        tree = ed.tree_main if t == 'main' else ed.tree_sub
        tps = [float(tree.item(c, 'values')[1]) for c in tree.get_children()]
        if tps != [float(p.pos) for p in ps]:
            msgs.append(f'{t} 테이블 측점 불일치')
        # 전주 연결
        for a, b in zip(ps, ps[1:]):
            if a.next_pos == b.pos and a.span != b.pos - a.pos:
                msgs.append(f'{t} span 불일치 at {a.pos}')
        # 흐름방지: 태그 전주 ↔ 장비/전선
        for p in ps:
            has_eq = any(e.type == '흐름방지장치' for e in p.equipments)
            if p.section in ('흐름방지 시작점', '흐름방지 끝점') and not has_eq:
                msgs.append(f'{t} {p.pos} 흐름방지 태그인데 장치 없음')
            if p.section not in ('흐름방지 시작점', '흐름방지 끝점') and has_eq:
                msgs.append(f'{t} {p.pos} 흐름방지 장치가 남아 있음 (태그 {p.section})')
    if plotted_points() != total:
        msgs.append(f'배치도 점 {plotted_points()} ≠ 전주 {total}')
    # 전선 기하 (본선, 상선은 rail_info 있을 때)
    for t, line in (('main', main_line), ('sub', sub_line)):
        if line is None or t not in runner.wire_data:
            continue
        by_pos = {p.pos: p for p in runner.poledata[t]}
        rows_ = [dict(pos=w.pos, next_pos=by_pos[w.pos].next_pos, start=list(s.offset), end=list(s.end_point),
                      yaw=s.adjusted_angle, station=s.station, label=s.label, radius=by_pos[w.pos].radius)
                 for w in runner.wire_data[t] for s in w.wires]
        errs = wire_errors(rows_, line)
        if errs and errs[0][0] > 0.001:
            msgs.append(f'{t} 전선 기하 오차 {errs[0][0]*100:.2f}cm at {errs[0][1]["pos"]}')
        # 전선은 전주 사이마다 있어야 함 (연속 전주)
        spans = {(p.pos) for p, q in zip(runner.poledata[t], runner.poledata[t][1:]) if p.next_pos == q.pos}
        wpos = {w.pos for w in runner.wire_data[t]}
        if spans != wpos:
            msgs.append(f'{t} 전선 경간 {len(wpos)} ≠ 연속 전주 경간 {len(spans)}')
    ok = not msgs
    n_dev = sum(1 for ps in poles.values() for p in ps if p.section == '흐름방지 중간점')
    print(f"[{'OK' if ok else 'FAIL'}] {step}: 전주 {[len(v) for v in poles.values()]}, 흐름방지 구간 {n_dev}")
    for m in msgs[:6]:
        print('     -', m)
    if not ok:
        failures.append(step)


def select(track, pos):
    tree = ed.tree_main if track == 'main' else ed.tree_sub
    ed.notebook.select(0 if track == 'main' else 1)
    for c in tree.get_children():
        if float(tree.item(c, 'values')[1]) == pos:
            tree.selection_set(c)
            break
    ed.load_selected()
    app.update()


def normal_pole(track, k=0):
    ps = runner.poledata[track]
    cands = [i for i in range(2, len(ps) - 2) if all(ps[j].section is None for j in range(i - 2, i + 3))]
    return ps[cands[k]]


check('초기 실행')

# 1) 배치도에서 전주 이동 (+1m)
p = normal_pole('main', 3)
select('main', p.pos)
old = p.pos
pl.move_right()
check(f'전주 이동 {old}→{p.pos}')
assert pl.selected_epole.pole is p, '이동 후 선택 래퍼가 새 래퍼로 갱신되지 않음'

# 2) 전주 삭제: 경간이 경간표를 벗어나면 거부되어야 함
p = normal_pole('main', 6)
n_before = len(runner.poledata['main'])
select('main', p.pos)
ed.delete_pole()
assert len(runner.poledata['main']) == n_before, '경간표 밖 경간이 되는 삭제가 거부되지 않음'
check(f'전주 삭제 거부(경간 초과) {p.pos}')
# 마지막 전주 삭제는 허용 (새 경간 없음)
last = runner.poledata['main'][-1]
select('main', last.pos)
ed.delete_pole()
assert runner.poledata['main'][-1] is not last
check(f'마지막 전주 삭제 {last.pos}')

# 3) 에어조인트 추가 → 흐름방지 재계산 (새 장력구간 생김)
before = sum(1 for q in runner.poledata['main'] if q.section == '흐름방지 중간점')
p = normal_pole('main', 10)
select('main', p.pos)
ed.add_airjoint()
check(f'에어조인트 추가 중간주 {p.pos}')
after = sum(1 for q in runner.poledata['main'] if q.section == '흐름방지 중간점')
print(f'     흐름방지 구간(본선) {before} → {after}')

# 4) 같은 에어조인트 제거
select('main', p.pos)
ed.remove_airjoint()
check(f'에어조인트 제거 {p.pos}')

# 5) 흐름방지 수동 추가/삭제
p = normal_pole('main', 1)
select('main', p.pos)
ed.add_antidevice()
check(f'흐름방지 수동 추가 {p.pos}')
mid = next(q for q in runner.poledata['main'] if q.section == '흐름방지 중간점')
select('main', mid.pos)
ed.remove_antidevice()
check(f'흐름방지 삭제 {mid.pos}')
# 수동 요청이 이후 재계산에도 유지되는지 (다른 전주 이동 후)
p2 = normal_pole('main', 12)
select('main', p2.pos)
pl.move_left()
check('다른 전주 이동 후 수동 흐름방지 요청 유지')

# 6) 상선 편집 (복선일 때)
if 'sub' in runner.poledata and runner.poledata['sub']:
    p = normal_pole('sub', 4)
    select('sub', p.pos)
    pl.move_right()
    check(f'상선 전주 이동 {p.pos}')
    p = normal_pole('sub', 8)
    select('sub', p.pos)
    ed.add_airjoint()
    check(f'상선 에어조인트 추가 {p.pos}')

app.destroy()
print('RESULT', 'PASS' if not failures else f'FAIL {failures}')
sys.exit(1 if failures else 0)
