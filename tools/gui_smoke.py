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
messagebox.showwarning = lambda *a, **k: print('  [warning]', a[0])
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
main_line = load_main_line(cfg.get('alignment') or cfg['coord'])
sub_line = (load_rail_line(cfg['rail_info'], cfg['sub_rail'], len(main_line), main_line.start)
            if cfg.get('sub_rail') is not None else None)
failures = []


from core.pole import pole_units  # noqa: E402
from core.model_rebuilder import alignment_for  # noqa: E402


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
    # 실제 전주 단위 (복주 지지점은 앞 -F / 뒤 -B 두 행·두 점)
    units = {t: pole_units.track_units(ps) for t, ps in poles.items()}
    total = sum(len(v) for v in units.values())
    msgs = []
    for t, ps in poles.items():
        if rows[t] != len(units[t]):
            msgs.append(f'{t} 테이블 {rows[t]}행 ≠ 전주 {len(units[t])}')
        # 테이블 전주번호·측점 = 전주 단위 번호·측점
        tree = ed.tree_main if t == 'main' else ed.tree_sub
        tps = [(str(tree.item(c, 'values')[0]), float(tree.item(c, 'values')[1])) for c in tree.get_children()]
        if tps != [(u.label, float(u.station)) for u in units[t]]:
            msgs.append(f'{t} 테이블 전주번호·측점 불일치')
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
# 구간(에어조인트 등) 전주는 테이블에서 삭제 불가 (구간이 반쪽만 남음)
aj_pole = next((p for p in runner.poledata['main'] if p.section is not None), None)
if aj_pole is not None:
    n_before = len(runner.poledata['main'])
    select('main', aj_pole.pos)
    ed.delete_pole()
    if len(runner.poledata['main']) != n_before:
        failures.append('구간 전주 삭제가 거부되지 않음')
    check(f'구간 전주 삭제 거부 {aj_pole.pos}')
# 전주 추가 창: 취소하면 추가되지 않음 (이전: 빈 전주가 추가됨)
from gui import pole_add_ui  # noqa: E402
_orig_add_ui = pole_add_ui.PoleADDUI
import gui.maineditor as _me  # noqa: E402
class _CancelUI(_orig_add_ui):
    def __init__(self):
        super().__init__()
        self.after(50, self.cancle)
_me.PoleADDUI = _CancelUI
n_before = len(runner.poledata['main'])
ed.notebook.select(0); ed.add_pole(); app.update()
_me.PoleADDUI = _orig_add_ui
if len(runner.poledata['main']) != n_before:
    failures.append('전주 추가 창을 취소했는데 전주가 추가됨')
check('전주 추가 창 취소')

# 3~5) 구간 편집기: 에어조인트 추가(→ 흐름방지 재계산)·삭제, 에어섹션 단일/이중, 흐름방지 수동 추가·삭제
from core import section_edit  # noqa: E402
from event.events import MODEL_CHANGED, POLE_SELECTED  # noqa: E402
n_pole_l = len(app.events._listeners.get(POLE_SELECTED, []))
n_model_l = len(app.events._listeners.get(MODEL_CHANGED, []))


def free_run(track, n, k=0, all_tracks=False):
    """연속 n 개가 모두 일반개소(흐름방지 없음)인 k 번째 시작 전주.
    all_tracks 면 다른 트랙에도 같은 측점부터 같은 조건인 위치만 (본선 + 상선 동시 추가용)"""
    def ok(ps, i):
        return all(ps[j].section is None and ps[j].flowstop is None for j in range(i - 1, i + n + 1))
    ps = runner.poledata[track]
    starts = []
    for i in range(2, len(ps) - n - 1):
        if not ok(ps, i):
            continue
        if all_tracks:
            others = [runner.poledata[t] for t in runner.poledata if t != track and runner.poledata[t]]
            idx = [next((j for j, q in enumerate(o) if q.pos == ps[i].pos), None) for o in others]
            if any(j is None or j < 2 or j > len(o) - n - 2 or not ok(o, j) for j, o in zip(idx, others)):
                continue
        starts.append(ps[i])
    return starts[k]


def sections(track='main', kind_id=None):
    return [i for i in section_edit.find_sections(runner, track) if kind_id is None or (i.kind and i.kind.id == kind_id)]


p = free_run('main', 5, 3, all_tracks=True)
select('main', p.pos)
sx = ed.open_section_editor()
app.update()
if sx.start != ('main', p.pos):
    failures.append('구간 편집기 시작 전주가 선택 전주가 아님')
both = 'sub' in runner.poledata and bool(runner.poledata['sub'])
if both and sx.track_var.get() != '본선 + 상선':
    failures.append('복선인데 적용 트랙 기본값이 본선 + 상선이 아님')
sx.kind_var.set(section_edit.SECTION_KINDS['airjoint_2span'].label); sx.update_preview(); app.update()
n_preview = len(sx.preview.get_children())
if n_preview != 5 * (2 if both else 1) or 'disabled' in sx.btn_add.state():
    failures.append(f'에어조인트 미리보기 이상 ({n_preview}행)')
before = len(sections('main', 'flowstop'))
sx.add()
check(f'구간 편집: 에어조인트 추가 {p.pos}')
aj = [i for i in sections('main', 'airjoint_2span') if i.start_pos == p.pos]
after = len(sections('main', 'flowstop'))
print(f'     흐름방지 구간(본선) {before} → {after}')
if len(aj) != 1 or after != before + 1:
    failures.append('에어조인트 추가 또는 흐름방지 재계산 안 됨')
if both and not [i for i in sections('sub', 'airjoint_2span') if i.start_pos == p.pos]:
    failures.append('상선에 에어조인트가 함께 추가되지 않음')
# 겹치는 위치에서는 추가 버튼 비활성 + 문제 표시
select('main', aj[0].poles[2].pos); app.update()
if 'disabled' not in sx.btn_add.state() or not sx.problem_var.get():
    failures.append('겹치는 구간 추가가 막히지 않음')
# 목록에서 골라 삭제 (삭제할 때마다 목록이 다시 만들어지므로 매번 다시 찾음)
while True:
    iid = next((i for i, inst in sx._instances.items()
                if inst.kind and inst.kind.id == 'airjoint_2span' and inst.start_pos == p.pos), None)
    if iid is None:
        break
    sx.list_tree.selection_set(iid); sx._update_list_buttons()
    sx.remove_selected()
    app.update()
check(f'구간 편집: 에어조인트 삭제 {p.pos}')
if [i for t in runner.poledata for i in sections(t, 'airjoint_2span') if i.start_pos == p.pos]:
    failures.append('에어조인트 삭제 안 됨')

for kid, k in (('airjoint_2span_double_pole', 4), ('airsection_single', 5), ('airsection_double', 6)):
    p = free_run('main', section_edit.SECTION_KINDS[kid].n_poles, k)
    select('main', p.pos)
    sx.track_var.set('본선'); sx.kind_var.set(section_edit.SECTION_KINDS[kid].label); sx.update_preview()
    sx.add()
    check(f'구간 편집: {kid} 추가 {p.pos}')
    found = [i for i in sections('main', kid) if i.start_pos == p.pos]
    if len(found) != 1:
        failures.append(f'{kid} 추가 안 됨')
        continue
    if kid == 'airjoint_2span_double_pole' and [q.twin is not None for q in found[0].poles] != [False, True, True,
                                                                                               True, False]:
        failures.append('복주 에어조인트 2·3·4호주에 두 번째 전주가 없음')
    if kid == 'airjoint_2span_double_pole':
        # 테이블에서 복주 뒤 전주(-B) 행 선택 → 배치도에 뒤 전주 위치·번호로 강조
        mid = found[0].poles[2]
        rear = pole_units.PoleUnit(mid, pole_units.REAR)
        ed.notebook.select(0); ed.tree_main.selection_set(rear.key); ed.load_selected(); app.update()
        want = rear.coord(alignment_for(runner, 'main'))
        if (ed.selected_pole is None or ed.selected_pole.pole is not mid or ed.selected_pole.which != 1
                or ed.entry_post_number_var.get() != f'{mid.post_number}-B'):
            failures.append('테이블 복주 -B 행 선택이 뒤 전주로 잡히지 않음')
        elif (pl.selected_pole_text is None or pl.selected_pole_text.get_text() != f'{mid.post_number}-B'
              or max(abs(a - b) for a, b in zip(pl.sel_xy, want)) > 1e-6):
            failures.append('배치도에 복주 뒤 전주가 따로 강조되지 않음')
        else:
            print(f'[OK] 복주 -B 행 선택 → 배치도 {mid.post_number}-B ({rear.station}m)')
    iid = next(i for i, inst in sx._instances.items() if inst.kind and inst.kind.id == kid and inst.start_pos == p.pos)
    sx.list_tree.selection_set(iid); sx.goto_selected(); app.update()
    if ed.selected_pole is None or ed.selected_pole.pole.pos != p.pos:
        failures.append('위치로 이동이 편집기 선택을 옮기지 않음')
    sx.remove_selected()
    check(f'구간 편집: {kid} 삭제')

p = free_run('main', 3, 1)
select('main', p.pos)
sx.track_var.set('본선'); sx.kind_var.set(section_edit.SECTION_KINDS['flowstop'].label); sx.update_preview()
sx.add()
check(f'구간 편집: 흐름방지 수동 추가 {p.pos}')
fs = [i for i in sections('main', 'flowstop') if i.start_pos == p.pos]
if len(fs) != 1:
    failures.append('흐름방지 수동 추가 안 됨')
p2 = normal_pole('main', 12)
select('main', p2.pos)
pl.move_left()
check('다른 전주 이동 후 수동 흐름방지 요청 유지')
if len([i for i in sections('main', 'flowstop') if i.start_pos == p.pos]) != 1:
    failures.append('재계산 후 수동 흐름방지 사라짐')
iid = next(i for i, inst in sx._instances.items() if inst.kind and inst.kind.id == 'flowstop' and inst.start_pos == p.pos)
sx.list_tree.selection_set(iid); sx._update_list_buttons()
sx.remove_selected()
check(f'구간 편집: 흐름방지 삭제 {p.pos}')
sx.exit_windows()
app.update()
if (len(app.events._listeners.get(POLE_SELECTED, [])) != n_pole_l
        or len(app.events._listeners.get(MODEL_CHANGED, [])) != n_model_l):
    failures.append('구간 편집기를 닫아도 이벤트 구독이 남음')

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
# 표 셀 편집: 전주를 다시 만들지 않고 직접 편집한 구성품 유지
old_number, old_pos = p.post_number, p.pos
ed.apply_cell_edit(p, 0, f'{old_number}A')
ed.apply_cell_edit(p, 1, str(old_pos + 1))
app.update()
check(f'표 편집: 전주번호·측점 {old_pos}→{p.pos}')
if p.post_number != f'{old_number}A' or p.pos != old_pos + 1:
    failures.append('표 편집(전주번호·측점) 반영 안 됨')
if (tuple(p.brackets[0].offset), p.brackets[0].rotation) != ((0.12, 0.34), 1.5):
    failures.append('표 편집(측점) 후 직접 편집한 브래킷이 사라짐')
try:
    ed.apply_cell_edit(p, 0, runner.poledata['main'][0].post_number)
    failures.append('중복 전주번호가 거부되지 않음')
except ValueError:
    pass
ed.apply_cell_edit(p, 1, str(old_pos))
ed.apply_cell_edit(p, 0, old_number)
select('main', p.pos)
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
    p = free_run('sub', 5, 8)
    select('sub', p.pos)
    sx = ed.open_section_editor()
    sx.track_var.set('상선'); sx.kind_var.set(section_edit.SECTION_KINDS['airjoint_2span'].label); sx.update_preview()
    sx.add()
    check(f'상선 에어조인트 추가 {p.pos}')
    if not [i for i in sections('sub', 'airjoint_2span') if i.start_pos == p.pos]:
        failures.append('상선 에어조인트 추가 안 됨')
    sx.exit_windows()

# 9) 데이터셋 편집기: 값 수정·표준값 복원, 하위 항목 추가·삭제, 경간표 편집, 잘못된 입력, 오류 시 저장 차단, 저장 후 커스텀 사용
import tempfile  # noqa: E402
import gui.dataset_gui as dataset_gui  # noqa: E402
de = app.edit_dataset()
app.update()
if de is None or not de.tree.exists('mast.gauge.토공') or not de.doc.is_standard:
    failures.append('데이터셋 편집기가 표준 데이터셋 설정값을 표시하지 않음')
else:
    def pick_value(iid):
        parent = de.tree.parent(iid)
        while parent:
            de.tree.item(parent, open=True); parent = de.tree.parent(parent)
        de.tree.selection_set(iid); de._on_value_selected(); app.update()
    pick_value('mast.gauge.토공')
    de.value_var.set('3.25'); de.apply_value()
    if de.doc.get(('mast', 'gauge', '토공')) != 3.25 or de.tree.item('mast.gauge.토공', 'values')[2] != '변경됨':
        failures.append('데이터셋 값 수정·변경 표시 안 됨')
    de.reset_value()
    if de.doc.get(('mast', 'gauge', '토공')) == 3.25:
        failures.append('표준값으로 되돌리기 안 됨')
    de.value_var.set('세미터'); de.apply_value()   # 숫자 자리에 문자 → 오류 안내, 값 그대로
    if de.doc.get(('mast', 'gauge', '토공')) == '세미터':
        failures.append('잘못된 입력이 저장됨')
    pick_value('wire.offset')
    de.new_key_var.set('Extra'); de.new_value_var.set('{}'); de.add_key()
    if not de.tree.exists('wire.offset.Extra'):
        failures.append('하위 항목 추가 안 됨')
    pick_value('wire.offset.Extra'); de.remove_key()
    if de.tree.exists('wire.offset.Extra'):
        failures.append('하위 항목 삭제 안 됨')
    de.notebook.select(1); de.sheet_var.set('토공전차선'); de._refresh_span_table()
    de.span_tree.selection_set('0'); de._on_span_selected()
    old_idx = de.doc.spans['토공전차선'].at[0, '인덱스']
    de.span_vars['인덱스'].set(str(int(old_idx) + 1)); de.apply_span_row()
    if de.doc.spans['토공전차선'].at[0, '인덱스'] != int(old_idx) + 1:
        failures.append('경간표 행 수정 안 됨')
    n_rows = len(de.doc.spans['토공전차선'])
    de.add_span_row()
    de.remove_span_row()
    if len(de.doc.spans['토공전차선']) != n_rows:
        failures.append('경간표 행 추가·삭제 안 됨')
    tmp = tempfile.mkdtemp()
    answers = iter([os.path.join(tmp, 'c.json'), os.path.join(tmp, 'c_span.xlsx')] * 2)
    dataset_gui.asksaveasfilename = lambda *a, **k: next(answers)
    saved_gauge = de.doc.data['mast']['gauge'].pop('교량')   # 검사 오류 상태로 저장 시도 → 차단
    de.save_and_use()
    if os.path.exists(os.path.join(tmp, 'c.json')) or app.is_custom_mode.get():
        failures.append('검사 오류가 있는데 저장됨')
    de.doc.data['mast']['gauge']['교량'] = saved_gauge
    de.save_and_use()
    app.update()
    if not (os.path.exists(os.path.join(tmp, 'c.json')) and app.is_custom_mode.get()
            and app.custom_dataset_json == os.path.join(tmp, 'c.json')
            and app.dataset['_source']['json'] == os.path.join(tmp, 'c.json')):
        failures.append('저장 후 커스텀으로 사용 안 됨')
    print(f"[{'OK' if not de.doc.dirty else 'FAIL'}] 데이터셋 편집기: 수정·경간표·검사·저장 후 커스텀 사용")
    de.close()

app.destroy()
print('RESULT', 'PASS' if not failures else f'FAIL {failures}')
sys.exit(1 if failures else 0)
