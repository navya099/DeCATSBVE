"""전주 상세 편집기 — 선택한 전주의 구성품(기둥·기초·밴드·브래킷·피팅·장비) 편집, 건식게이지 변경

편집 로직은 core.pole.pole_edit 에 있고 이 창은 표시와 입력만 맡는다.
적용 → rebuild() → MODEL_CHANGED 로 모든 화면이 갱신된다. 오브젝트 이름 ↔ 인덱스는 인덱스 라이브러리로 맞춘다.
(이전 '전주 조립기'는 외부 모듈을 이식한 것으로, 이 파일에서 전면 교체됨)
"""
import tkinter as tk
from tkinter import ttk, messagebox

from core.model_rebuilder import alignment_for, rebuild
from core.pole import pole_edit
from enums.section_type import section_label
from event.events import MODEL_CHANGED, POLE_SELECTED

TRACK_TEXT = {'main': '본선', 'sub': '상선'}
ADD_KIND_TEXT = {'브래킷': 'br', '피팅 (선택한 브래킷에)': 'fit', '장비': 'eq', '밴드/부속': 'acc'}
COLUMNS = (("kind", "종류", 90), ("name", "이름", 230), ("index", "인덱스", 60),
           ("x", "x", 70), ("y", "y", 70), ("rot", "회전", 70), ("detail", "비고", 110))


def _fmt(value, digits=3):
    return '' if value is None else f'{value:.{digits}f}'.rstrip('0').rstrip('.') if isinstance(value, float) else str(value)


class PoleEditor(tk.Toplevel):
    def __init__(self, runner, event=None, selection=None):
        """selection: 처음 보여줄 전주 (EditablePole 또는 PoleDATA)"""
        super().__init__()
        self.title("전주 상세 편집")
        self.geometry("860x640")
        self.runner = runner
        self.event = event
        self.pole = None
        self.selected_key = None
        self._bound = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.exit_windows)
        self.bind_events()
        self.show_pole(selection)

    # ── UI ─────────────────────────────────────────
    def _build_ui(self):
        self.header_var = tk.StringVar(value='편집기에서 전주를 선택하세요')
        ttk.Label(self, textvariable=self.header_var, font=("맑은 고딕", 10, "bold")).pack(fill="x", padx=10, pady=(10, 4))

        gauge_row = ttk.Frame(self)
        gauge_row.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(gauge_row, text="건식게이지").pack(side="left")
        self.gauge_var = tk.DoubleVar()
        ttk.Entry(gauge_row, textvariable=self.gauge_var, width=10).pack(side="left", padx=4)
        self.btn_gauge = ttk.Button(gauge_row, text="게이지 적용", command=self.apply_gauge)
        self.btn_gauge.pack(side="left", padx=3)
        self.btn_regen = ttk.Button(gauge_row, text="자동 구성으로 되돌리기", command=self.regenerate)
        self.btn_regen.pack(side="left", padx=3)

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(table, columns=[c[0] for c in COLUMNS], show="tree headings", height=12,
                                 selectmode="browse")
        self.tree.column("#0", width=28, stretch=False)
        for key, text, width in COLUMNS:
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor="w" if key in ("name", "detail") else "center")
        self.tree.tag_configure('readonly', foreground='#6b7280')
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_row_selected)

        form = ttk.LabelFrame(self, text="구성품")
        form.pack(fill="x", padx=10, pady=8)
        self.name_var = tk.StringVar()
        self.index_var = tk.StringVar()
        self.x_var, self.y_var, self.rot_var = tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()
        self.eqtype_var = tk.StringVar(value='기타장비')
        self.addkind_var = tk.StringVar(value='장비')

        ttk.Label(form, text="이름").grid(row=0, column=0, padx=6, pady=3, sticky="e")
        self.name_combo = ttk.Combobox(form, textvariable=self.name_var, width=36)
        self.name_combo.grid(row=0, column=1, columnspan=2, padx=6, pady=3, sticky="w")
        self.name_combo.bind("<Return>", lambda e: self.search())
        self.name_combo.bind("<<ComboboxSelected>>", self._on_search_pick)
        ttk.Button(form, text="라이브러리 검색", command=self.search).grid(row=0, column=3, padx=6, pady=3, sticky="w")
        ttk.Label(form, text="인덱스").grid(row=0, column=4, padx=6, pady=3, sticky="e")
        ttk.Entry(form, textvariable=self.index_var, width=10).grid(row=0, column=5, padx=6, pady=3, sticky="w")
        for col, (text, var) in enumerate((("x", self.x_var), ("y", self.y_var), ("회전", self.rot_var))):
            ttk.Label(form, text=text).grid(row=1, column=col * 2, padx=6, pady=3, sticky="e")
            ttk.Entry(form, textvariable=var, width=10).grid(row=1, column=col * 2 + 1, padx=6, pady=3, sticky="w")
        ttk.Label(form, text="장비 종류").grid(row=2, column=0, padx=6, pady=3, sticky="e")
        ttk.Entry(form, textvariable=self.eqtype_var, width=14).grid(row=2, column=1, padx=6, pady=3, sticky="w")
        ttk.Label(form, text="추가할 종류").grid(row=2, column=2, padx=6, pady=3, sticky="e")
        ttk.Combobox(form, textvariable=self.addkind_var, values=list(ADD_KIND_TEXT), state="readonly",
                     width=20).grid(row=2, column=3, columnspan=2, padx=6, pady=3, sticky="w")
        ttk.Label(form, text="※ 이름만 입력하면 인덱스를, 인덱스만 입력하면 이름을 인덱스 라이브러리에서 찾습니다.",
                  foreground="#6b7280").grid(row=3, column=0, columnspan=6, sticky="w", padx=6)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 6))
        self.btn_apply = ttk.Button(buttons, text="적용", command=self.apply_edit)
        self.btn_remove = ttk.Button(buttons, text="삭제", command=self.remove)
        self.btn_add = ttk.Button(buttons, text="추가", command=self.add)
        for b in (self.btn_apply, self.btn_remove, self.btn_add):
            b.pack(side="left", padx=3)
        ttk.Button(buttons, text="닫기", command=self.exit_windows).pack(side="right", padx=3)

        self.message_var = tk.StringVar()
        ttk.Label(self, textvariable=self.message_var, foreground="#6b7280").pack(fill="x", padx=10, pady=(0, 8))
        self._update_buttons(None)

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

    cancle = exit_windows  # 이전 이름 호환

    def on_pole_selected(self, epole):
        if self.winfo_exists():
            self.show_pole(epole)

    def on_model_changed(self):
        if not self.winfo_exists():
            return
        if self.pole is not None and not self._pole_exists(self.pole):
            self.pole = None  # 삭제됐거나 다른 전주로 교체됨
        self.refresh()

    def _pole_exists(self, pole):
        return any(p is pole for poles in (self.runner.poledata or {}).values() for p in poles)

    # ── 표시 ───────────────────────────────────────
    def show_pole(self, selection):
        pole = getattr(selection, 'pole', selection)
        if pole is not self.pole:
            self.selected_key = None
        self.pole = pole
        if pole is not None:
            self.gauge_var.set(pole.gauge)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        pole = self.pole
        if pole is None:
            self.header_var.set('편집기에서 전주를 선택하세요')
            self._update_buttons(None)
            return
        self.header_var.set(f'[{TRACK_TEXT.get(pole.track, pole.track)}] {pole.post_number} ({pole.pos}m)  '
                            f'{section_label(pole)} / {pole.structure} / {"곡선" if pole.radius else "직선"}  '
                            f'게이지 {pole.gauge}')
        for r in pole_edit.components(pole):
            parent = r.parent if r.parent and self.tree.exists(r.parent) else ""
            detail = r.detail + ('' if r.editable else ' (자동, 읽기 전용)')
            self.tree.insert(parent, "end", iid=r.key, open=True, tags=('' if r.editable else 'readonly',), values=(
                pole_edit.KIND_TEXT[r.kind], r.name, '' if r.index is None else r.index,
                _fmt(r.offset[0]), _fmt(r.offset[1]), _fmt(r.rotation), detail))
        if self.selected_key and self.tree.exists(self.selected_key):
            self.tree.selection_set(self.selected_key)
            self.tree.see(self.selected_key)
        else:
            self.selected_key = None
            self._update_buttons(None)

    def _row(self, key):
        return next((r for r in pole_edit.components(self.pole) if r.key == key), None) if self.pole else None

    def _on_row_selected(self, _event=None):
        sel = self.tree.selection()
        self.selected_key = sel[0] if sel else None
        r = self._row(self.selected_key) if self.selected_key else None
        if r is not None:
            self.name_var.set(r.name or '')
            self.index_var.set('' if r.index is None else str(r.index))
            self.x_var.set(r.offset[0])
            self.y_var.set(r.offset[1])
            self.rot_var.set(r.rotation)
            if r.kind == 'eq':
                self.eqtype_var.set(r.detail)
        self._update_buttons(r)

    def _update_buttons(self, row):
        has_pole = self.pole is not None
        editable = row is not None and row.editable
        self.btn_apply.state(['!disabled'] if editable else ['disabled'])
        self.btn_remove.state(['!disabled'] if editable and row.kind != 'mast' else ['disabled'])
        for b in (self.btn_add, self.btn_gauge, self.btn_regen):
            b.state(['!disabled'] if has_pole else ['disabled'])

    # ── 라이브러리 검색 ──────────────────────────────
    def search(self):
        results = pole_edit.search(self.runner.idxlib, self.name_var.get())
        self._search_results = {f'{name}  [{idx}]': (name, idx) for name, idx in results}
        self.name_combo.config(values=list(self._search_results))
        self.message_var.set(f'검색 결과 {len(results)}개' if results else '검색 결과가 없습니다')
        if results:
            self.name_combo.event_generate('<Down>')

    def _on_search_pick(self, _event=None):
        picked = getattr(self, '_search_results', {}).get(self.name_var.get())
        if picked:
            self.name_var.set(picked[0])
            self.index_var.set(str(picked[1]))

    # ── 편집 동작 ───────────────────────────────────
    def _values(self):
        try:
            offset = (self.x_var.get(), self.y_var.get())
            rotation = self.rot_var.get()
        except tk.TclError:
            raise ValueError('x, y, 회전은 숫자로 입력하세요.') from None
        index = self.index_var.get().strip()
        if index and not index.lstrip('-').isdigit():
            raise ValueError('인덱스는 정수로 입력하세요.')
        return self.name_var.get().strip(), (int(index) if index else None), offset, rotation

    def _commit(self, message):
        rebuild(self.runner)
        self.runner.log(f'{self.pole.post_number}: {message}')
        self.message_var.set(message)
        if self.event:
            self.event.emit(MODEL_CHANGED)  # 이 창도 on_model_changed 로 갱신
        else:
            self.refresh()

    def _run(self, action):
        if self.pole is None:
            messagebox.showerror('전주 편집', '편집기에서 전주를 선택하세요.', parent=self)
            return
        try:
            action()
        except ValueError as e:
            messagebox.showerror('전주 편집', str(e), parent=self)

    def apply_edit(self):
        def action():
            r = self._row(self.selected_key)
            if r is None:
                raise ValueError('구성품을 선택하세요.')
            name, index, offset, rotation = self._values()
            # 이름을 바꿨는데 인덱스는 그대로면 이름 기준으로 다시 찾음
            if name and name != r.name and index == r.index:
                index = None
            if r.kind == 'base':
                pole_edit.set_base(self.runner, self.pole, name or None, index,
                                   twin=r.key.startswith(pole_edit.TWIN))
                pole_edit.set_component(self.runner, self.pole, r.key, offset=offset, rotation=rotation)
            else:
                pole_edit.set_component(self.runner, self.pole, r.key, name or None, index, offset, rotation)
            self._commit(f'{pole_edit.KIND_TEXT[r.kind]} 수정: {name or r.name}')
        self._run(action)

    def remove(self):
        def action():
            r = self._row(self.selected_key)
            if r is None:
                raise ValueError('구성품을 선택하세요.')
            pole_edit.remove_component(self.pole, r.key)
            self.selected_key = None
            self._commit(f'{pole_edit.KIND_TEXT[r.kind]} 삭제: {r.name}')
        self._run(action)

    def add(self):
        def action():
            kind = ADD_KIND_TEXT[self.addkind_var.get()]
            name, index, offset, rotation = self._values()
            parent = None
            if kind == 'fit':
                parent = self.selected_key.split('/fit:')[0] if self.selected_key else None
            elif self.selected_key and pole_edit.component_pole(self.pole, self.selected_key) == 1:
                parent = 'twin'  # 복주: 뒤 전주 구성품을 선택한 상태면 뒤 전주에 추가
            self.selected_key = pole_edit.add_component(self.runner, self.pole, kind, name or None, index, offset,
                                                        rotation, parent=parent,
                                                        equipment_type=self.eqtype_var.get().strip() or '기타장비')
            self._commit(f'{pole_edit.KIND_TEXT[kind]} 추가: {name or index}')
        self._run(action)

    def apply_gauge(self):
        def action():
            try:
                gauge = self.gauge_var.get()
            except tk.TclError:
                raise ValueError('건식게이지는 숫자로 입력하세요.') from None
            moved, notices = pole_edit.set_gauge(self.runner, self.pole, gauge,
                                                 alignment_for(self.runner, self.pole.track))
            self._commit(f'건식게이지 {gauge} 적용 (게이지 위치 구성품 {moved}개 이동, 편집 내용 유지)')
            if notices:
                messagebox.showinfo('건식게이지 변경', '\n'.join(notices), parent=self)
        self._run(action)

    def regenerate(self):
        def action():
            if not messagebox.askyesno('자동 구성으로 되돌리기', '이 전주의 구성품을 자동 배치 규칙으로 다시 만듭니다.\n'
                                                         '직접 편집한 구성품은 사라집니다. 계속할까요?', parent=self):
                return
            pole_edit.regenerate(self.runner, self.pole, alignment_for(self.runner, self.pole.track))
            self.selected_key = None
            self._commit('자동 구성으로 되돌림')
        self._run(action)


PoleAssemblerApp = PoleEditor  # 이전 이름 호환
