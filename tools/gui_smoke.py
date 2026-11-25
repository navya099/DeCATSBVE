"""GUI 스모크 테스트: 실제 Tk 앱에서 편집 동작 후 테이블·배치도·전선·흐름방지가 서로 일치하는지 확인

    python -m tools.gui_smoke tests/regression_cases/synthetic_double_rail_150/case.json
    (Linux 화면 없는 환경: xvfb-run -a python -m tools.gui_smoke <case.json>)

창이 잠깐 열렸다 닫힌다. 전주 이동·삭제, 에어조인트 추가·제거, 흐름방지 수동 추가·삭제, 상선 편집을
편집기/배치도 함수로 직접 실행하고 단계마다 다음을 검사한다:
    테이블 행·측점 = 전주 데이터, 배치도 점 수 = 전주 수, 연속 전주마다 전선, 전선 기하 오차,
    흐름방지 태그 ↔ 장치 일치
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
from tkinter import messagebox  # noqa: E402
messagebox.showerror = lambda *a, **k: print('  [messagebox]', a)
messagebox.showinfo = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True  # 확인 대화상자는 '예'

from gui.maingui import AutoPoleApp  # noqa: E402
from tools import headless  # noqa: E402
from tools.verify import wire_errors, load_main_line, load_rail_line  # noqa: E402

app = AutoPoleApp()
app.update()
cfg = headless.load_config(case)
runner = headless.build_runner(cfg)
runner.log_widget = app.log_box
if runner.idxlib.df.empty:  # 합성 노선 등 인덱스 라이브러리가 없으면 자동 배치에 쓰는 인덱스로 최소 구성
    import pandas as pd  # noqa: E402
    from xref_module.index_libmgr import IndexLibrary  # noqa: E402
    used = set()
    def _collect(node):
        if isinstance(node, dict):
            for v in node.values():
                _collect(v)
        elif isinstance(node, int) and not isinstance(node, bool):
            used.add(node)
    _collect({k: v for k, v in runner.dataprocessor.dataset.items() if k != 'span_data'})
    runner.idxlib = IndexLibrary(pd.DataFrame([{'인덱스': i, '파일명': f'obj{i}', '경로': f'obj{i}.csv'} for i in sorted(used)]))
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
            if p.flowstop in ('흐름방지 시작점', '흐름방지 끝점') and not has_eq:
                msgs.append(f'{t} {p.pos} 흐름방지 태그인데 장치 없음')
            if p.flowstop not in ('흐름방지 시작점', '흐름방지 끝점') and has_eq:
                msgs.append(f'{t} {p.pos} 흐름방지 장치가 남아 있음 (흐름방지 {p.flowstop})')
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
    n_dev = sum(1 for ps in poles.values() for p in ps if p.flowstop == '흐름방지 중간점')
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
before = sum(1 for q in runner.poledata['main'] if q.flowstop == '흐름방지 중간점')
p = normal_pole('main', 10)
select('main', p.pos)
ed.add_airjoint()
check(f'에어조인트 추가 중간주 {p.pos}')
after = sum(1 for q in runner.poledata['main'] if q.flowstop == '흐름방지 중간점')
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
mid = next(q for q in runner.poledata['main'] if q.flowstop == '흐름방지 중간점')
select('main', mid.pos)
ed.remove_antidevice()
check(f'흐름방지 삭제 {mid.pos}')
# 수동 요청이 이후 재계산에도 유지되는지 (다른 전주 이동 후)
p2 = normal_pole('main', 12)
select('main', p2.pos)
pl.move_left()
check('다른 전주 이동 후 수동 흐름방지 요청 유지')

# 6) 전선 상세 편집기: 표에서 전선 선택 → 지지점 수정 적용 → 다른 편집 후 유지 → 전선 추가·삭제 → 경간 자동값
from event.events import MODEL_CHANGED, WIRE_SELECTED  # noqa: E402
from core.wire import wire_overrides  # noqa: E402
p = normal_pole('main', 5)
select('main', p.pos)
n_wire_listeners = len(app.events._listeners.get(WIRE_SELECTED, []))
n_model_listeners = len(app.events._listeners.get(MODEL_CHANGED, []))
we = ed.open_wire_editor()
app.update()


def wire_rows():
    return {we.tree.item(i, 'values')[0] + '|' + i: we.tree.item(i, 'values') for i in we.tree.get_children()}


def pick(key):
    we.tree.selection_set(key)
    we._on_row_selected()
    app.update()


def cw(pos, key='전차선#0'):
    info = wire_overrides.span_info(runner, 'main', pos)
    return next((r for r in info.wires if r.key == key), None)


if not we.tree.exists('전차선#0'):
    failures.append('전선 편집기 표에 전차선 없음'); print('     -', list(wire_rows()))
pick('전차선#0')
we.ex_var.set(0.33)
we.ey_var.set(5.31)
we.apply_edit()
check('전선 편집 적용')
nxt_pos = cw(p.pos).end_point and wire_overrides.span_info(runner, 'main', p.pos).next_pos
if cw(p.pos).end_point != (0.33, 5.31) or cw(nxt_pos).offset != (0.33, 5.31):
    failures.append('전선 편집(끝점·뒤 경간 시작점) 반영 안 됨'); print('     -', cw(p.pos), cw(nxt_pos))
if we.tree.item('전차선#0', 'values')[-1] != '편집':
    failures.append('편집기 표 상태가 갱신되지 않음')

q = normal_pole('main', 14)
select('main', q.pos)
pl.move_right()
check('다른 전주 이동 후 전선 편집 유지')
if cw(p.pos).end_point != (0.33, 5.31):
    failures.append('재계산 후 전선 편집 사라짐')

select('main', p.pos)      # 편집기가 선택을 따라옴
app.update()
we.label_var.set('부급전선')
we.index_var.set(1239)
we.sx_var.set(-2.5); we.sy_var.set(7.0); we.ex_var.set(-2.5); we.ey_var.set(7.0)
we.add_wire()
check('전선 추가')
added = [i for i in we.tree.get_children() if i.startswith('added:')]
if len(added) != 1 or we.tree.item(added[0], 'values')[-1] != '추가':
    failures.append('추가 전선이 편집기에 표시되지 않음')
af = next((i for i in we.tree.get_children() if we.tree.item(i, 'values')[0] == 'AF'), None)
pick(af)
we.remove_wire()
check('전선 삭제(AF)')
if we.tree.item(af, 'values')[-1] != '삭제됨':
    failures.append('삭제 전선 표시 안 됨')
we.reset_span()
check('경간 전체 자동값')
if any(i.startswith('added:') for i in we.tree.get_children()) or we.tree.item(af, 'values')[-1] != '자동':
    failures.append('경간 자동값 복원 안 됨')
for pos in list({cw(p.pos) and p.pos, nxt_pos}):
    wire_overrides.reset_span(runner, 'main', pos)
we.exit_windows()
app.update()
if (len(app.events._listeners.get(WIRE_SELECTED, [])) != n_wire_listeners
        or len(app.events._listeners.get(MODEL_CHANGED, [])) != n_model_listeners):
    failures.append('전선 편집기를 닫아도 이벤트 구독이 남음')

# 7) 전주 상세 편집기: 구성품 수정·추가·삭제 → 건식게이지 변경(편집 유지) → 자동 구성 → 선택 따라감 → 닫기
from core.pole import pole_edit  # noqa: E402
from event.events import POLE_SELECTED  # noqa: E402
p = normal_pole('main', 7)
select('main', p.pos)
n_pole_listeners = len(app.events._listeners.get(POLE_SELECTED, []))
n_model_listeners = len(app.events._listeners.get(MODEL_CHANGED, []))
pe = ed.open_equipment_editor()
app.update()
if pe.pole is not p or not pe.tree.exists('mast') or not pe.tree.exists('br:0'):
    failures.append('전주 편집기에 선택 전주 구성품이 표시되지 않음')
pe.tree.selection_set('br:0'); pe._on_row_selected(); app.update()
pe.x_var.set(0.12); pe.y_var.set(0.34); pe.rot_var.set(1.5)
pe.apply_edit()
check('전주 편집: 브래킷 위치 수정')
if (tuple(p.brackets[0].offset), p.brackets[0].rotation) != ((0.12, 0.34), 1.5):
    failures.append('브래킷 수정 반영 안 됨')
feeder = next(e for e in p.equipments if e.type == '급전선설비')
n_eq = len(p.equipments)
pe.addkind_var.set('장비'); pe.name_var.set(''); pe.index_var.set(str(feeder.index))
pe.x_var.set(p.gauge); pe.y_var.set(1.0); pe.rot_var.set(0.0); pe.eqtype_var.set('기타장비')
pe.add()
check('전주 편집: 장비 추가')
if len(p.equipments) != n_eq + 1 or not pe.tree.exists(f'eq:{n_eq}'):
    failures.append('장비 추가 반영 안 됨')
pe.tree.selection_set(f'eq:{n_eq}'); pe._on_row_selected(); app.update()
pe.remove()
check('전주 편집: 장비 삭제')
if len(p.equipments) != n_eq:
    failures.append('장비 삭제 반영 안 됨')
old_coord, new_gauge = p.coord, round(p.gauge * 1.1, 3)
pe.gauge_var.set(new_gauge)
pe.apply_gauge()
check(f'전주 편집: 건식게이지 {new_gauge}')
if p.gauge != new_gauge or p.coord == old_coord or abs(p.mast.offset[0] - new_gauge) > 1e-9:
    failures.append('건식게이지 변경(좌표·기둥 위치) 반영 안 됨')
if (tuple(p.brackets[0].offset), p.brackets[0].rotation) != ((0.12, 0.34), 1.5):
    failures.append('건식게이지 변경 후 직접 편집한 브래킷이 사라짐')
pe.regenerate()
check('전주 편집: 자동 구성으로 되돌리기')
if tuple(p.brackets[0].offset) == (0.12, 0.34):
    failures.append('자동 구성 되돌리기 안 됨')
q = normal_pole('main', 11)
select('main', q.pos)
if pe.pole is not q:
    failures.append('전주 편집기가 선택을 따라가지 않음')
pe.exit_windows()
app.update()
if (len(app.events._listeners.get(POLE_SELECTED, [])) != n_pole_listeners
        or len(app.events._listeners.get(MODEL_CHANGED, [])) != n_model_listeners):
    failures.append('전주 편집기를 닫아도 이벤트 구독이 남음')

# 8) 상선 편집 (복선일 때)
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
