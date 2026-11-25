"""전선 상세 편집기 — 선택한 경간의 전선 지지점 수정, 전선 추가·삭제, 자동값 복원

편집 로직은 core.wire.wire_overrides (경간 단위 편집 내용) 에 있고, 이 창은 표시와 입력만 맡는다.
적용 → rebuild() → MODEL_CHANGED 로 모든 화면이 갱신되며, 편집 내용은 이후 다른 편집으로 재계산돼도 유지된다.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from core.model_rebuilder import rebuild
from core.wire import wire_overrides
from event.events import MODEL_CHANGED, WIRE_SELECTED

STATUS_TEXT = {'auto': '자동', 'edited': '편집', 'added': '추가', 'removed': '삭제됨'}
TRACK_TEXT = {'main': '본선', 'sub': '상선'}
COLUMNS = (("label", "전선", 110), ("index", "인덱스", 60),
           ("sx", "시작 x", 70), ("sy", "시작 높이", 70), ("ex", "끝 x", 70), ("ey", "끝 높이", 70),
           ("yaw", "평면각", 80), ("pitch", "종단각", 80), ("status", "상태", 60))


def _fmt(value, digits=3):
    return '' if value is None else f'{value:.{digits}f}'


class WireEditor(tk.Toplevel):
    def __init__(self, runner, event=None, selection=None):
        """selection: 처음 보여줄 경간 (EditableWire 또는 (트랙, 앞 전주 pos))"""
        super().__init__()
        self.title("전선 상세 편집")
        self.geometry("820x560")
        self.runner = runner
        self.event = event
        self.track = None
        self.pos = None
        self.selected_key = None
        self._bound = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.exit_windows)
        self.bind_events()
        if selection is not None:
            self.show_span(*self._as_span(selection))
        else:
            self.refresh()

    # ── UI ─────────────────────────────────────────
    def _build_ui(self):
        self.span_var = tk.StringVar(value='편집기에서 전주를 선택하세요')
        ttk.Label(self, textvariable=self.span_var, font=("맑은 고딕", 10, "bold")).pack(fill="x", padx=10, pady=(10, 4))

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(table, columns=[c[0] for c in COLUMNS], show="headings", height=10,
                                 selectmode="browse")
        for key, text, width in COLUMNS:
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor="center")
        self.tree.tag_configure('edited', foreground='#1d4ed8')
        self.tree.tag_configure('added', foreground='#15803d')
        self.tree.tag_configure('removed', foreground='#9ca3af')
        self.tree.tag_configure('readonly', foreground='#6b7280')
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_row_selected)

        form = ttk.LabelFrame(self, text="선택한 전선")
        form.pack(fill="x", padx=10, pady=8)
        self.label_var = tk.StringVar()
        self.index_var = tk.IntVar(value=0)
        self.sx_var, self.sy_var = tk.DoubleVar(), tk.DoubleVar()
        self.ex_var, self.ey_var = tk.DoubleVar(), tk.DoubleVar()
        self.link_var = tk.BooleanVar(value=True)
        fields = (("전선 이름", self.label_var), ("오브젝트 인덱스", self.index_var),
                  ("시작 x 이격", self.sx_var), ("시작 높이", self.sy_var),
                  ("끝 x 이격", self.ex_var), ("끝 높이", self.ey_var))
        self.entries = {}
        for i, (text, var) in enumerate(fields):
            ttk.Label(form, text=text).grid(row=i // 2, column=(i % 2) * 2, padx=6, pady=3, sticky="e")
            entry = ttk.Entry(form, textvariable=var, width=14)
            entry.grid(row=i // 2, column=(i % 2) * 2 + 1, padx=6, pady=3, sticky="w")
            self.entries[text] = entry
        ttk.Checkbutton(form, text="앞뒤 경간 연결 유지 (시작점=앞 경간 끝점, 끝점=뒤 경간 시작점)",
                        variable=self.link_var).grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=3)
        ttk.Label(form, text="※ 이름·인덱스는 '전선 추가' 때만 사용합니다. 각도는 지지점과 선형으로 자동 계산됩니다.",
                  foreground="#6b7280").grid(row=4, column=0, columnspan=4, sticky="w", padx=6)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 6))
        self.btn_apply = ttk.Button(buttons, text="적용", command=self.apply_edit)
        self.btn_reset_wire = ttk.Button(buttons, text="이 전선 자동값", command=self.reset_wire)
        self.btn_remove = ttk.Button(buttons, text="전선 삭제", command=self.remove_wire)
        self.btn_add = ttk.Button(buttons, text="전선 추가", command=self.add_wire)
        self.btn_reset_span = ttk.Button(buttons, text="경간 전체 자동값", command=self.reset_span)
        for b in (self.btn_apply, self.btn_reset_wire, self.btn_remove, self.btn_add, self.btn_reset_span):
            b.pack(side="left", padx=3)
        ttk.Button(buttons, text="닫기", command=self.exit_windows).pack(side="right", padx=3)

        self.message_var = tk.StringVar()
        ttk.Label(self, textvariable=self.message_var, foreground="#6b7280").pack(fill="x", padx=10, pady=(0, 8))
        self._update_buttons(None)

    # ── 이벤트 ─────────────────────────────────────
    def bind_events(self):
        if self.event and not self._bound:
            self.event.bind(WIRE_SELECTED, self.on_wire_selected)
            self.event.bind(MODEL_CHANGED, self.on_model_changed)
            self._bound = True

    def exit_windows(self):
        if self.event and self._bound:  # 닫힌 창이 계속 이벤트를 받지 않도록
            self.event.unbind(WIRE_SELECTED, self.on_wire_selected)
            self.event.unbind(MODEL_CHANGED, self.on_model_changed)
            self._bound = False
        self.destroy()

    def on_wire_selected(self, ewire):
        if self.winfo_exists() and ewire is not None:
            self.show_span(*self._as_span(ewire))

    def on_model_changed(self):
        if self.winfo_exists():
            self.refresh()

    @staticmethod
    def _as_span(selection):
        if isinstance(selection, tuple):
            return selection
        return selection.wire.track_name, selection.wire.pos

    # ── 표시 ───────────────────────────────────────
    def show_span(self, track, pos):
        if (track, pos) != (self.track, self.pos):
            self.selected_key = None
        self.track, self.pos = track, pos
        self.refresh()

    def _info(self):
        if self.track is None or not self.runner or not self.runner.wire_data:
            return None
        return wire_overrides.span_info(self.runner, self.track, self.pos)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        info = self._info()
        if info is None:
            self.span_var.set('편집기에서 전주를 선택하세요' if self.track is None
                              else f'{TRACK_TEXT.get(self.track, self.track)} {self.pos}: 전선이 있는 경간이 아닙니다')
            self._update_buttons(None)
            return
        self.span_var.set(f'[{TRACK_TEXT.get(info.track, info.track)}] {info.pole.post_number} ({info.pos}) → '
                          f'{info.next_pole.post_number} ({info.next_pos}), 경간 {info.next_pos - info.pos}m')
        for row in info.wires:
            start = row.offset if row.offset else (None, None)
            end = row.end_point if row.end_point else (None, None)
            tag = row.status if row.status != 'auto' else ('readonly' if not row.editable else '')
            self.tree.insert("", "end", iid=row.key, tags=(tag,), values=(
                row.label, row.index, _fmt(start[0]), _fmt(start[1]), _fmt(end[0]), _fmt(end[1]),
                _fmt(row.adjusted_angle, 4), _fmt(row.topdown_angle, 4),
                STATUS_TEXT[row.status] + ('' if row.editable or row.status == 'removed' else ' (읽기 전용)')))
        if self.selected_key and self.tree.exists(self.selected_key):
            self.tree.selection_set(self.selected_key)
            self.tree.see(self.selected_key)
        else:
            self.selected_key = None
            self._update_buttons(None)

    def _row(self, key):
        info = self._info()
        return next((r for r in info.wires if r.key == key), None) if info else None

    def _on_row_selected(self, _event=None):
        sel = self.tree.selection()
        self.selected_key = sel[0] if sel else None
        row = self._row(self.selected_key) if self.selected_key else None
        if row is not None:
            self.label_var.set(row.label)
            self.index_var.set(row.index)
            if row.offset:
                self.sx_var.set(round(row.offset[0], 6))
                self.sy_var.set(round(row.offset[1], 6))
                self.ex_var.set(round(row.end_point[0], 6))
                self.ey_var.set(round(row.end_point[1], 6))
        self._update_buttons(row)

    def _update_buttons(self, row):
        has_span = self._info() is not None
        editable = row is not None and row.editable
        self.btn_apply.state(['!disabled'] if editable else ['disabled'])
        self.btn_remove.state(['!disabled'] if editable else ['disabled'])
        self.btn_reset_wire.state(['!disabled'] if row is not None and row.status != 'auto' else ['disabled'])
        self.btn_add.state(['!disabled'] if has_span else ['disabled'])
        self.btn_reset_span.state(['!disabled'] if has_span else ['disabled'])

    # ── 편집 동작 ───────────────────────────────────
    def _points(self):
        try:
            return (self.sx_var.get(), self.sy_var.get()), (self.ex_var.get(), self.ey_var.get())
        except tk.TclError:
            raise ValueError('지지점 값은 숫자로 입력하세요.') from None

    def _commit(self, message):
        """편집 내용 반영: 재계산 → 모든 화면 갱신"""
        rebuild(self.runner)
        self.runner.log(message)
        self.message_var.set(message)
        if self.event:
            self.event.emit(MODEL_CHANGED)  # 이 창도 on_model_changed 로 갱신됨
        else:
            self.refresh()

    def _run(self, action):
        try:
            action()
        except ValueError as e:
            messagebox.showerror('전선 편집', str(e), parent=self)

    def apply_edit(self):
        def action():
            row = self._row(self.selected_key)
            if row is None:
                raise ValueError('전선을 선택하세요.')
            start, end = self._points()
            changed = wire_overrides.set_wire(self.runner, self.track, self.pos, row.key, start, end,
                                              link_neighbors=self.link_var.get())
            self._commit(f'전선 편집: {row.label} (경간 {len(changed)}개 반영)')
        self._run(action)

    def reset_wire(self):
        def action():
            row = self._row(self.selected_key)
            if row is None:
                raise ValueError('전선을 선택하세요.')
            wire_overrides.reset_wire(self.runner, self.track, self.pos, row.key)
            self._commit(f'전선 자동값 복원: {row.label}')
        self._run(action)

    def remove_wire(self):
        def action():
            row = self._row(self.selected_key)
            if row is None:
                raise ValueError('전선을 선택하세요.')
            wire_overrides.remove_wire(self.runner, self.track, self.pos, row.key)
            self._commit(f'전선 삭제: {row.label}')
        self._run(action)

    def add_wire(self):
        def action():
            label = self.label_var.get().strip()
            if not label:
                raise ValueError('추가할 전선 이름을 입력하세요.')
            try:
                index = int(self.index_var.get())
            except (tk.TclError, ValueError):
                raise ValueError('오브젝트 인덱스는 정수로 입력하세요.') from None
            start, end = self._points()
            self.selected_key = wire_overrides.add_wire(self.runner, self.track, self.pos, label, index, start, end)
            self._commit(f'전선 추가: {label} (인덱스 {index})')
        self._run(action)

    def reset_span(self):
        def action():
            if self._info() is None:
                raise ValueError('경간을 선택하세요.')
            wire_overrides.reset_span(self.runner, self.track, self.pos)
            self.selected_key = None
            self._commit('경간 전선 전체 자동값 복원')
        self._run(action)
