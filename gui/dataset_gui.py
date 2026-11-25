"""데이터셋 편집기 — 설계 데이터셋(JSON) 설정값 트리, 경간표(spandata) 편집, 검사, 커스텀 저장

편집 로직은 core.dataset_edit 에 있고 이 창은 표시와 입력만 맡는다.
표준 데이터셋(config/)은 덮어쓰지 않으며, '다른 이름으로 저장' 또는 '저장 후 커스텀으로 사용'으로 커스텀 데이터셋을 만든다.
검사 오류가 있으면 저장되지 않는다.
"""
import os
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.filedialog import asksaveasfilename

from core.dataset_edit import KEY_TEXT, DatasetDocument, path_text

STATUS_TAGS = {'error': '#b91c1c', 'warning': '#b45309', 'changed': '#1d4ed8'}


def _fmt(value):
    if value is None:
        return 'null'
    if isinstance(value, float):
        return f'{value:g}'
    return str(value)


class DatasetEditor(tk.Toplevel):
    def __init__(self, document: DatasetDocument, on_use=None):
        """on_use(json_path, xlsx_path): '저장 후 커스텀으로 사용' 시 메인 화면에서 커스텀 데이터셋으로 지정하는 함수"""
        super().__init__()
        self.title("데이터셋 편집")
        self.geometry("980x720")
        self.doc = document
        self.on_use = on_use
        self._paths = {}          # 트리 iid → 경로
        self._problems = {}       # 경로 문자열 → [Problem]
        self._span_row = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_all()

    # ── UI ─────────────────────────────────────────
    def _build_ui(self):
        self.header_var = tk.StringVar()
        ttk.Label(self, textvariable=self.header_var, font=("맑은 고딕", 10, "bold")).pack(fill="x", padx=10, pady=(10, 2))
        self.subheader_var = tk.StringVar()
        ttk.Label(self, textvariable=self.subheader_var, foreground="#6b7280").pack(fill="x", padx=10)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=6)
        self._build_values_tab()
        self._build_spans_tab()
        self._build_check_tab()

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        self.btn_save = ttk.Button(bottom, text="저장", command=self.save)
        self.btn_save.pack(side="left", padx=3)
        ttk.Button(bottom, text="다른 이름으로 저장…", command=self.save_as).pack(side="left", padx=3)
        self.btn_use = ttk.Button(bottom, text="저장 후 커스텀으로 사용", command=self.save_and_use)
        self.btn_use.pack(side="left", padx=3)
        ttk.Button(bottom, text="닫기", command=self.close).pack(side="right", padx=3)
        self.message_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.message_var, foreground="#6b7280").pack(side="left", padx=10)

    def _build_values_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="설정값")
        box = ttk.Frame(tab)
        box.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree = ttk.Treeview(box, columns=("value", "template", "status"), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="항목")
        self.tree.column("#0", width=300)
        for key, text, width in (("value", "값", 220), ("template", "표준값", 220), ("status", "상태", 160)):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor="w")
        for tag, color in STATUS_TAGS.items():
            self.tree.tag_configure(tag, foreground=color)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_value_selected)

        form = ttk.LabelFrame(tab, text="선택한 항목")
        form.pack(fill="x", padx=6, pady=(0, 6))
        self.path_var = tk.StringVar()
        ttk.Label(form, textvariable=self.path_var).grid(row=0, column=0, columnspan=6, sticky="w", padx=6, pady=3)
        ttk.Label(form, text="값").grid(row=1, column=0, sticky="e", padx=6)
        self.value_var = tk.StringVar()
        value_entry = ttk.Entry(form, textvariable=self.value_var, width=30)
        value_entry.grid(row=1, column=1, sticky="w", padx=6, pady=3)
        value_entry.bind("<Return>", lambda e: self.apply_value())
        self.btn_apply = ttk.Button(form, text="값 적용", command=self.apply_value)
        self.btn_apply.grid(row=1, column=2, padx=3)
        self.btn_template = ttk.Button(form, text="표준값으로", command=self.reset_value)
        self.btn_template.grid(row=1, column=3, padx=3)
        ttk.Label(form, text="하위 항목 추가: 이름").grid(row=2, column=0, sticky="e", padx=6)
        self.new_key_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.new_key_var, width=18).grid(row=2, column=1, sticky="w", padx=6, pady=3)
        ttk.Label(form, text="값 (비우면 null, {} 이면 묶음)").grid(row=2, column=2, sticky="e")
        self.new_value_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.new_value_var, width=14).grid(row=2, column=3, sticky="w", padx=6)
        self.btn_add_key = ttk.Button(form, text="추가", command=self.add_key)
        self.btn_add_key.grid(row=2, column=4, padx=3)
        self.btn_remove_key = ttk.Button(form, text="항목 삭제", command=self.remove_key)
        self.btn_remove_key.grid(row=2, column=5, padx=3)
        ttk.Label(form, text="※ 숫자 자리에 빈 값을 넣으면 null(인덱스 없음)입니다. 목록은 [1, 2] 처럼 입력합니다.",
                  foreground="#6b7280").grid(row=3, column=0, columnspan=6, sticky="w", padx=6, pady=(0, 3))

    def _build_spans_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="경간표")
        top = ttk.Frame(tab)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="시트").pack(side="left")
        self.sheet_var = tk.StringVar()
        self.sheet_combo = ttk.Combobox(top, textvariable=self.sheet_var, state="readonly", width=20)
        self.sheet_combo.pack(side="left", padx=4)
        self.sheet_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_span_table())
        ttk.Label(top, text="경간 길이(m) → 전선 오브젝트 인덱스", foreground="#6b7280").pack(side="left", padx=10)
        box = ttk.Frame(tab)
        box.pack(fill="both", expand=True, padx=6)
        self.span_tree = ttk.Treeview(box, show="headings", selectmode="browse")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.span_tree.yview)
        self.span_tree.configure(yscrollcommand=scroll.set)
        self.span_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.span_tree.bind("<<TreeviewSelect>>", self._on_span_selected)
        self.span_form = ttk.LabelFrame(tab, text="선택한 행")
        self.span_form.pack(fill="x", padx=6, pady=6)
        self.span_vars = {}
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(buttons, text="행 적용", command=self.apply_span_row).pack(side="left", padx=3)
        ttk.Button(buttons, text="행 추가", command=self.add_span_row).pack(side="left", padx=3)
        ttk.Button(buttons, text="행 삭제", command=self.remove_span_row).pack(side="left", padx=3)

    def _build_check_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="검사")
        self.check_tab = tab
        ttk.Button(tab, text="다시 검사", command=self.refresh_all).pack(anchor="w", padx=6, pady=6)
        self.check_tree = ttk.Treeview(tab, columns=("level", "where", "message"), show="headings")
        for key, text, width in (("level", "수준", 60), ("where", "위치", 280), ("message", "내용", 560)):
            self.check_tree.heading(key, text=text)
            self.check_tree.column(key, width=width, anchor="w")
        self.check_tree.tag_configure('error', foreground=STATUS_TAGS['error'])
        self.check_tree.tag_configure('warning', foreground=STATUS_TAGS['warning'])
        self.check_tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.check_tree.bind("<Double-1>", self._goto_problem)

    # ── 표시 ───────────────────────────────────────
    def refresh_all(self):
        problems = self.doc.validate()
        self._problems = {}
        for p in problems:
            self._problems.setdefault(p.where, []).append(p)
        src = self.doc.json_path or '(저장 안 됨)'
        kind = '표준 데이터셋 — 저장 시 커스텀으로 저장' if self.doc.is_standard else '커스텀 데이터셋'
        speed = self.doc.data.get('design', {}).get('speed')
        self.header_var.set(f'{kind}: 설계속도 {speed}km/h  {"(수정됨)" if self.doc.dirty else ""}')
        self.subheader_var.set(f'{src}  |  비교 기준: 표준 {self.doc.template_speed}km/h')
        self._refresh_values()
        self._refresh_sheets()
        self._refresh_checks(problems)
        self.btn_save.state(['disabled'] if self.doc.is_standard or not self.doc.json_path else ['!disabled'])
        self.btn_use.state(['!disabled'] if self.on_use else ['disabled'])

    def _refresh_values(self):
        selected = self._selected_path()
        open_paths = {self._paths[i] for i in self._paths if self.tree.exists(i) and self.tree.item(i, 'open')}
        self.tree.delete(*self.tree.get_children())
        self._paths = {}
        changed = self.doc.changed_paths()

        def insert(parent, node, prefix):
            for key, value in node.items():
                path = prefix + (key,)
                iid = path_text(path)
                self._paths[iid] = path
                label = f'{key} ({KEY_TEXT[key]})' if not prefix and key in KEY_TEXT else str(key)
                problems = [p for w, ps in self._problems.items() for p in ps if w == iid or w.startswith(iid + '.')]
                level = 'error' if any(p.level == 'error' for p in problems) else (
                    'warning' if problems else None)
                if isinstance(value, dict):
                    status = {'error': '하위에 오류', 'warning': '하위에 경고'}.get(level, '')
                    self.tree.insert(parent, "end", iid=iid, text=label, open=path in open_paths,
                                     values=('', '', status), tags=(level,) if level else ())
                    insert(iid, value, path)
                else:
                    tval, has = self.doc.template_value(path)
                    status = level and problems[0].message or ('변경됨' if path in changed else '')
                    tag = level or ('changed' if path in changed else '')
                    self.tree.insert(parent, "end", iid=iid, text=label, tags=(tag,) if tag else (),
                                     values=(_fmt(value), _fmt(tval) if has else '(표준에 없음)', status))

        insert("", self.doc.data, ())
        if selected and self.tree.exists(path_text(selected)):
            self.tree.selection_set(path_text(selected))
            self.tree.see(path_text(selected))
        else:
            self._on_value_selected()

    def _refresh_checks(self, problems):
        self.check_tree.delete(*self.check_tree.get_children())
        for n, p in enumerate(problems):
            self.check_tree.insert("", "end", iid=f'p{n}', tags=(p.level,), values=(
                '오류' if p.level == 'error' else '경고', p.where, p.message))
        n_err = sum(p.level == 'error' for p in problems)
        n_warn = len(problems) - n_err
        self.notebook.tab(self.check_tab, text=f'검사 (오류 {n_err}, 경고 {n_warn})' if problems else '검사 (문제 없음)')

    def _selected_path(self):
        sel = self.tree.selection()
        return self._paths.get(sel[0]) if sel else None

    def _on_value_selected(self, _event=None):
        path = self._selected_path()
        is_leaf = path is not None and not isinstance(self.doc.get(path), dict)
        self.path_var.set(path_text(path) if path else '항목을 선택하세요')
        self.value_var.set(_fmt(self.doc.get(path)) if is_leaf else '')
        self.btn_apply.state(['!disabled'] if is_leaf else ['disabled'])
        self.btn_template.state(['!disabled'] if is_leaf and self.doc.template_value(path)[1] else ['disabled'])
        self.btn_add_key.state(['!disabled'] if path is not None and not is_leaf else ['disabled'])
        self.btn_remove_key.state(['!disabled'] if path is not None and not self.doc.template_value(path)[1]
                                  and not _in_template(self.doc, path) else ['disabled'])

    def _goto_problem(self, _event=None):
        sel = self.check_tree.selection()
        if not sel:
            return
        where = self.check_tree.item(sel[0], 'values')[1]
        if where.startswith('경간표:'):
            self.notebook.select(1)
            sheet = where.split(':', 1)[1]
            if sheet in self.doc.spans:
                self.sheet_var.set(sheet)
                self._refresh_span_table()
            return
        parts = where.split('.')
        for n in range(len(parts), 0, -1):  # 가장 가까운 존재하는 항목으로 이동
            iid = '.'.join(parts[:n])
            if self.tree.exists(iid):
                self.notebook.select(0)
                parent = self.tree.parent(iid)
                while parent:
                    self.tree.item(parent, open=True)
                    parent = self.tree.parent(parent)
                self.tree.selection_set(iid)
                self.tree.see(iid)
                return

    # 경간표
    def _refresh_sheets(self):
        sheets = list(self.doc.spans)
        self.sheet_combo.config(values=sheets)
        if self.sheet_var.get() not in sheets:
            self.sheet_var.set(sheets[0] if sheets else '')
        self._refresh_span_table()

    def _refresh_span_table(self):
        sheet = self.sheet_var.get()
        self.span_tree.delete(*self.span_tree.get_children())
        for child in self.span_form.winfo_children():
            child.destroy()
        self.span_vars = {}
        self._span_row = None
        if not sheet:
            return
        df = self.doc.spans[sheet]
        cols = list(df.columns)
        self.span_tree.config(columns=cols)
        for c in cols:
            self.span_tree.heading(c, text=c)
            self.span_tree.column(c, width=110, anchor="center")
        for i, row in df.iterrows():
            self.span_tree.insert("", "end", iid=str(i), values=[_fmt(v) for v in row.tolist()])
        for n, c in enumerate(cols):
            ttk.Label(self.span_form, text=c).grid(row=0, column=n, padx=4)
            var = tk.StringVar()
            ttk.Entry(self.span_form, textvariable=var, width=12).grid(row=1, column=n, padx=4, pady=3)
            self.span_vars[c] = var

    def _on_span_selected(self, _event=None):
        sel = self.span_tree.selection()
        self._span_row = int(sel[0]) if sel else None
        if self._span_row is None:
            return
        df = self.doc.spans[self.sheet_var.get()]
        for c, var in self.span_vars.items():
            var.set(_fmt(df.at[self._span_row, c]))

    # ── 편집 동작 ───────────────────────────────────
    def _run(self, action, message):
        try:
            action()
        except (ValueError, KeyError) as e:
            messagebox.showerror('데이터셋 편집', str(e).strip("'"), parent=self)
            return False
        self.message_var.set(message)
        self.refresh_all()
        return True

    def apply_value(self):
        path = self._selected_path()
        if path is not None:
            self._run(lambda: self.doc.set(path, self.value_var.get()), f'{path_text(path)} 수정')

    def reset_value(self):
        path = self._selected_path()
        if path is not None:
            self._run(lambda: self.doc.reset_to_template(path), f'{path_text(path)} 표준값으로')

    def add_key(self):
        path = self._selected_path()
        if path is not None:
            name = self.new_key_var.get().strip()
            self._run(lambda: self.doc.add_key(path, name, self.new_value_var.get()), f'{path_text(path)}.{name} 추가')

    def remove_key(self):
        path = self._selected_path()
        if path is not None:
            self._run(lambda: self.doc.remove_key(path), f'{path_text(path)} 삭제')

    def apply_span_row(self):
        sheet, row = self.sheet_var.get(), self._span_row
        if row is None:
            return

        def action():
            for c, var in self.span_vars.items():
                self.doc.set_span_cell(sheet, row, c, var.get())
        if self._run(action, f'경간표 {sheet} {row + 1}행 수정'):
            self._select_span_row(sheet, row)

    def add_span_row(self):
        sheet = self.sheet_var.get()
        if not sheet:
            return
        holder = {}
        if self._run(lambda: holder.update(row=self.doc.add_span_row(sheet)), f'경간표 {sheet} 행 추가'):
            self._select_span_row(sheet, holder['row'])

    def remove_span_row(self):
        sheet, row = self.sheet_var.get(), self._span_row
        if row is not None:
            self._run(lambda: self.doc.remove_span_row(sheet, row), f'경간표 {sheet} {row + 1}행 삭제')
            self.sheet_var.set(sheet)

    def _select_span_row(self, sheet, row):
        self.notebook.select(1)
        self.sheet_var.set(sheet)
        self._refresh_span_table()
        if self.span_tree.exists(str(row)):
            self.span_tree.selection_set(str(row))
            self.span_tree.see(str(row))
            self._on_span_selected()

    # ── 저장 ───────────────────────────────────────
    def _save(self, json_path=None, xlsx_path=None):
        try:
            paths = self.doc.save(json_path, xlsx_path)
        except ValueError as e:
            messagebox.showerror('데이터셋 저장', str(e), parent=self)
            self.notebook.select(2)
            self.refresh_all()
            return None
        self.message_var.set(f'저장: {paths[0]}')
        self.refresh_all()
        return paths

    def _ask_paths(self):
        speed = self.doc.data.get('design', {}).get('speed', '')
        json_path = asksaveasfilename(parent=self, title='커스텀 데이터셋 JSON 저장', defaultextension='.json',
                                      initialfile=f'custom_{speed}.json',
                                      filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not json_path:
            return None
        stem = os.path.splitext(os.path.basename(json_path))[0]
        xlsx_path = asksaveasfilename(parent=self, title='커스텀 경간표(spandata) 저장', defaultextension='.xlsx',
                                      initialdir=os.path.dirname(json_path), initialfile=f'{stem}_spandata.xlsx',
                                      filetypes=[("XLSX files", "*.xlsx")])
        if not xlsx_path:
            return None
        return json_path, xlsx_path

    def save(self):
        if self.doc.is_standard or not self.doc.json_path:
            return self.save_as()
        return self._save()

    def save_as(self):
        paths = self._ask_paths()
        return self._save(*paths) if paths else None

    def save_and_use(self):
        paths = self.save() if not self.doc.is_standard and self.doc.json_path else self.save_as()
        if paths and self.on_use:
            self.on_use(*paths)
            self.message_var.set(f'커스텀 데이터셋으로 사용: {paths[0]}')

    def close(self):
        if self.doc.dirty and not messagebox.askyesno('데이터셋 편집', '저장하지 않은 변경이 있습니다. 닫을까요?', parent=self):
            return
        self.destroy()


def _in_template(doc, path):
    """경로나 그 하위가 표준 데이터셋에 있으면 삭제 불가"""
    node = doc.template
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


DataSetEditor = DatasetEditor  # 이전 이름 호환
