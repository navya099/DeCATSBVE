"""구간 편집기 — 에어조인트·에어섹션·흐름방지 구간 목록, 추가(미리보기·검증), 삭제

편집 로직과 구간 종류 등록표는 core.section_edit 에 있다. 이 창은 표시와 입력만 맡는다.
추가 기준 전주 = 편집기에서 선택한 전주 (구간 시작 전주). 적용 → rebuild() → MODEL_CHANGED.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from core import section_edit
from core.model_rebuilder import alignment_for, rebuild
from event.events import MODEL_CHANGED, POLE_SELECTED

TRACK_TEXT = {'main': '본선', 'sub': '상선'}
TRACK_CHOICES = {'본선': ['main'], '상선': ['sub'], '본선 + 상선': ['main', 'sub']}


class SectionEditor(tk.Toplevel):
    def __init__(self, runner, event=None, selection=None, focus_callback=None):
        """selection: 추가 기준 전주 (EditablePole 또는 PoleDATA).
        focus_callback(track, pos): 목록에서 '위치로 이동' 시 편집기 선택을 옮기는 함수"""
        super().__init__()
        self.title("구간 편집 (에어조인트·에어섹션·흐름방지)")
        self.geometry("900x700")
        self.runner = runner
        self.event = event
        self.focus_callback = focus_callback
        self.start = None            # (트랙, 측점)
        self._instances = {}
        self._bound = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.exit_windows)
        self.bind_events()
        self.set_start(selection)

    # ── UI ─────────────────────────────────────────
    def _build_ui(self):
        existing = ttk.LabelFrame(self, text="기존 구간")
        existing.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        cols = (("track", "트랙", 60), ("kind", "종류", 220), ("start", "시작(m)", 80), ("end", "끝(m)", 80),
                ("poles", "전주", 160), ("purpose", "용도", 200))
        list_box = ttk.Frame(existing)
        list_box.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.list_tree = ttk.Treeview(list_box, columns=[c[0] for c in cols], show="headings", height=9,
                                      selectmode="browse")
        for key, text, width in cols:
            self.list_tree.heading(key, text=text)
            self.list_tree.column(key, width=width, anchor="w" if key in ("kind", "purpose", "poles") else "center")
        self.list_tree.tag_configure('incomplete', foreground='#b91c1c')
        scroll = ttk.Scrollbar(list_box, orient="vertical", command=self.list_tree.yview)
        self.list_tree.configure(yscrollcommand=scroll.set)
        self.list_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        side = ttk.Frame(existing)
        side.pack(fill="x", padx=6, pady=6)
        self.btn_goto = ttk.Button(side, text="위치로 이동", command=self.goto_selected)
        self.btn_goto.pack(side="left", padx=(0, 4))
        self.btn_remove = ttk.Button(side, text="구간 삭제", command=self.remove_selected)
        self.btn_remove.pack(side="left")
        self.list_tree.bind("<<TreeviewSelect>>", lambda e: self._update_list_buttons())

        add = ttk.LabelFrame(self, text="구간 추가 (편집기에서 선택한 전주 = 구간 시작 전주)")
        add.pack(fill="both", expand=True, padx=10, pady=4)
        row = ttk.Frame(add)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="종류").pack(side="left")
        self._kind_by_label = {k.label: k for k in section_edit.SECTION_KINDS.values()}
        self.kind_var = tk.StringVar(value=next(iter(self._kind_by_label)))
        kind_combo = ttk.Combobox(row, textvariable=self.kind_var, values=list(self._kind_by_label),
                                  state="readonly", width=32)
        kind_combo.pack(side="left", padx=4)
        kind_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())
        ttk.Label(row, text="적용 트랙").pack(side="left", padx=(12, 0))
        self.track_var = tk.StringVar()
        self.track_combo = ttk.Combobox(row, textvariable=self.track_var, state="readonly", width=12)
        self.track_combo.pack(side="left", padx=4)
        self.track_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())
        self.start_var = tk.StringVar()
        ttk.Label(row, textvariable=self.start_var).pack(side="left", padx=(12, 0))
        self.purpose_var = tk.StringVar()
        ttk.Label(add, textvariable=self.purpose_var, foreground="#6b7280").pack(fill="x", padx=6)

        pcols = (("track", "트랙", 60), ("post", "전주번호", 100), ("pos", "측점(m)", 80),
                 ("current", "현재", 220), ("new", "→ 새 구간", 220))
        self.preview = ttk.Treeview(add, columns=[c[0] for c in pcols], show="headings", height=8)
        for key, text, width in pcols:
            self.preview.heading(key, text=text)
            self.preview.column(key, width=width, anchor="w" if key in ("current", "new") else "center")
        self.preview.tag_configure('conflict', foreground='#b91c1c')
        self.preview.pack(fill="both", expand=True, padx=6, pady=4)
        self.problem_var = tk.StringVar()
        ttk.Label(add, textvariable=self.problem_var, foreground="#b91c1c", wraplength=860,
                  justify="left").pack(fill="x", padx=6)
        self.btn_add = ttk.Button(add, text="추가", command=self.add)
        self.btn_add.pack(anchor="e", padx=6, pady=6)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        self.message_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.message_var, foreground="#6b7280").pack(side="left")
        ttk.Button(bottom, text="닫기", command=self.exit_windows).pack(side="right")

    # ── 이벤트 ─────────────────────────────────────
    def bind_events(self):
        if self.event and not self._bound:
            self.event.bind(POLE_SELECTED, self.on_pole_selected)
            self.event.bind(MODEL_CHANGED, self.on_model_changed)
            self._bound = True

    def exit_windows(self):
        if self.event and self._bound:  # 닫힌 창이 계속 이벤트를 받지 않도록
            self.event.unbind(POLE_SELECTED, self.on_pole_selected)
            self.event.unbind(MODEL_CHANGED, self.on_model_changed)
            self._bound = False
        self.destroy()

    def on_pole_selected(self, epole):
        if self.winfo_exists():
            self.set_start(epole)

    def on_model_changed(self):
        if self.winfo_exists():
            self.refresh()

    # ── 표시 ───────────────────────────────────────
    def set_start(self, selection):
        pole = getattr(selection, 'pole', selection)
        self.start = (pole.track, pole.pos) if pole is not None else None
        self.refresh()

    def _tracks_available(self):
        return [t for t in ('main', 'sub') if (self.runner.poledata or {}).get(t)]

    def refresh(self):
        # 적용 트랙 선택지 (복선이면 기본 '본선 + 상선' = 자동 배치와 같음)
        available = self._tracks_available()
        choices = [label for label, tracks in TRACK_CHOICES.items() if all(t in available for t in tracks)]
        self.track_combo.config(values=choices)
        if self.track_var.get() not in choices:
            self.track_var.set('본선 + 상선' if '본선 + 상선' in choices else (choices[0] if choices else ''))
        self._refresh_list()
        self.update_preview()

    def _refresh_list(self):
        selected = self.list_tree.selection()
        self.list_tree.delete(*self.list_tree.get_children())
        self._instances = {}
        for n, inst in enumerate(section_edit.find_sections(self.runner) if self.runner.poledata else []):
            iid = f'sec{n}'
            self._instances[iid] = inst
            self.list_tree.insert("", "end", iid=iid, tags=('incomplete',) if inst.kind is None else (), values=(
                TRACK_TEXT.get(inst.track, inst.track), inst.label, inst.start_pos, inst.end_pos,
                f'{inst.poles[0].post_number} ~ {inst.poles[-1].post_number}',
                inst.kind.purpose if inst.kind else '구간 삭제 후 다시 추가하세요'))
        if selected and self.list_tree.exists(selected[0]):
            self.list_tree.selection_set(selected[0])
        self._update_list_buttons()

    def _selected_instance(self):
        sel = self.list_tree.selection()
        return self._instances.get(sel[0]) if sel else None

    def _update_list_buttons(self):
        state = ['!disabled'] if self._selected_instance() is not None else ['disabled']
        self.btn_goto.state(state)
        self.btn_remove.state(state)

    def _plans(self):
        if self.start is None or not self.track_var.get():
            return []
        kind = self._kind_by_label[self.kind_var.get()]
        return section_edit.plan_add_tracks(self.runner, TRACK_CHOICES[self.track_var.get()], self.start[1], kind.id)

    def update_preview(self):
        self.preview.delete(*self.preview.get_children())
        kind = self._kind_by_label[self.kind_var.get()]
        self.purpose_var.set(f'{section_edit.CATEGORY_TEXT[kind.category]}: {kind.purpose}')
        if self.start is None:
            self.start_var.set('시작 전주: 편집기에서 전주를 선택하세요')
            self.problem_var.set('')
            self.btn_add.state(['disabled'])
            return
        self.start_var.set(f'시작 전주: {TRACK_TEXT.get(self.start[0], self.start[0])} {self.start[1]}m')
        plans = self._plans()
        problems = []
        for plan in plans:
            for pole, current, new in plan.assignments:
                self.preview.insert("", "end", tags=('conflict',) if current else (), values=(
                    TRACK_TEXT.get(plan.track, plan.track), pole.post_number, pole.pos,
                    section_edit.section_tag_label(current), str(new)))
            problems += [f'[{TRACK_TEXT.get(plan.track, plan.track)}] {m}' for m in plan.problems]
        self.problem_var.set('\n'.join(problems))
        self.btn_add.state(['!disabled'] if plans and all(p.ok for p in plans) else ['disabled'])

    # ── 편집 동작 ───────────────────────────────────
    def _commit(self, message):
        rebuild(self.runner)
        self.runner.log(message)
        self.message_var.set(message)
        if self.event:
            self.event.emit(MODEL_CHANGED)  # 이 창도 on_model_changed 로 갱신
        else:
            self.refresh()

    def add(self):
        plans = self._plans()
        if not plans or not all(p.ok for p in plans):
            messagebox.showerror('구간 추가', '\n'.join(m for p in plans for m in p.problems) or '시작 전주를 선택하세요.',
                                 parent=self)
            return
        for plan in plans:
            section_edit.apply_add(self.runner, plan, alignment_for)
        kind = plans[0].kind
        tracks = ', '.join(TRACK_TEXT.get(p.track, p.track) for p in plans)
        self._commit(f'{kind.label} 추가: {tracks} {self.start[1]}m 부터')

    def remove_selected(self):
        inst = self._selected_instance()
        if inst is None:
            return
        section_edit.remove(self.runner, inst, alignment_for)
        self._commit(f'{inst.label} 삭제: {TRACK_TEXT.get(inst.track, inst.track)} {inst.start_pos}~{inst.end_pos}m')

    def goto_selected(self):
        inst = self._selected_instance()
        if inst is not None and self.focus_callback:
            self.focus_callback(inst.track, inst.start_pos)
