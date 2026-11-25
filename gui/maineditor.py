import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import askopenfilename

from core.pole.manual_pole_processor import ManualPoleProcessor
from core.structure.define_structure import isbridge_tunnel
from core.model_rebuilder import alignment_for, rebuild
from core.pole import pole_edit
from event.events import MODEL_CHANGED, POLE_SELECTED, POLES_SELECTED, WIRE_SELECTED
from gui.pole_add_ui import PoleADDUI
from gui.pole_assembler import PoleEditor
from gui.section_editor import SectionEditor
from gui.wireeditor import WireEditor
from vms.editable_pole import EditablePole
from vms.editable_wires import EditableWire
from enums.section_type import SectionType


class AutoPoleEditor(tk.Frame):
    def __init__(self, runner, events=None, master=None):
        super().__init__(master)
        self.original_pos = None
        self.selected_wire = None
        self.runner = runner
        self.events = events

        self.editable_poles = {"main": [], "sub": []}
        self.editable_wires = {"main": [], "sub": []}
        # 이벤트 바인딩
        self.selected_pole = None
        if self.events:
            self.events.bind(MODEL_CHANGED, self.on_model_changed)

        # Notebook 생성 (본선/상선 탭)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # 본선 탭
        frame_main = tk.Frame(self.notebook)
        self.notebook.add(frame_main, text="본선")
        self.tree_main = ttk.Treeview(
            frame_main,
            columns=("전주번호", "측점", '경간', "건식게이지", "구조물", "구간",
                     "기본 타입", '곡선반경', '구배', '캔트', '계획고'),
            show="headings"
        )
        self.tree_main.pack(fill="both", expand=True)
        for col in ("전주번호", "측점", '경간', "건식게이지", "구조물", "구간",
                    "기본 타입", '곡선반경', '구배', '캔트', '계획고'):
            self.tree_main.heading(col, text=col)
            self.tree_main.column(col, width=100, anchor="center")

        # 상선 탭
        frame_sub = tk.Frame(self.notebook)
        self.notebook.add(frame_sub, text="상선")
        self.tree_sub = ttk.Treeview(
            frame_sub,
            columns=("전주번호", "측점", '경간', "건식게이지", "구조물", "구간",
                     "기본 타입", '곡선반경', '구배', '캔트', '계획고'),
            show="headings"
        )
        self.tree_sub.pack(fill="both", expand=True)
        for col in ("전주번호", "측점", '경간', "건식게이지", "구조물", "구간",
                    "기본 타입", '곡선반경', '구배', '캔트', '계획고'):
            self.tree_sub.heading(col, text=col)
            self.tree_sub.column(col, width=100, anchor="center")

        self.tree_main.bind("<Double-1>", lambda e: self.edit_tree_cell(e, "main"))
        self.tree_sub.bind("<Double-1>", lambda e: self.edit_tree_cell(e, "sub"))

        # 트리뷰 생성 후 바인딩
        self.tree_main.bind("<ButtonRelease-1>", lambda e: self.on_tree_click(e, "main"))
        self.tree_sub.bind("<ButtonRelease-1>", lambda e: self.on_tree_click(e, "sub"))

        # 데이터 로딩
        self.load_data()

        # Entry + 버튼 영역 (공통)
        frame_controls = tk.Frame(self)
        frame_controls.pack(fill="x", pady=5)
        #tk변수
        self.entry_post_number_var = tk.StringVar()
        self.entry_pos_var = tk.DoubleVar()
        self.entry_gauge_var = tk.DoubleVar()
        self.entry_structure_var = tk.StringVar()
        self.entry_section_var = tk.StringVar()
        self.entry_base_type_var = tk.StringVar()

        tk.Label(frame_controls, text="전주번호").pack(side="left")
        self.entry_post_number = ttk.Entry(frame_controls, width=10, state="readonly", style="Readonly.TEntry", textvariable=self.entry_post_number_var)
        self.entry_post_number.pack(side="left")

        tk.Label(frame_controls, text="측점").pack(side="left")
        self.entry_pos = ttk.Entry(frame_controls, width=10, state="readonly", style="Readonly.TEntry", textvariable=self.entry_pos_var)
        self.entry_pos.pack(side="left")

        tk.Label(frame_controls, text="건식게이지").pack(side="left")
        self.entry_gauge = ttk.Entry(frame_controls, width=10, state="readonly", style="Readonly.TEntry", textvariable=self.entry_gauge_var)
        self.entry_gauge.pack(side="left")

        tk.Label(frame_controls, text="구조물").pack(side="left")
        self.entry_structure = ttk.Entry(frame_controls, width=10, state="readonly", style="Readonly.TEntry", textvariable=self.entry_structure_var)
        self.entry_structure.pack(side="left")

        tk.Label(frame_controls, text="구간").pack(side="left")
        self.entry_section = ttk.Entry(frame_controls, width=10, state="readonly", style="Readonly.TEntry", textvariable=self.entry_section_var)
        self.entry_section.pack(side="left")

        tk.Label(frame_controls, text="기본 타입").pack(side="left")
        self.entry_base_type = ttk.Entry(frame_controls, width=10, state="readonly", style="Readonly.TEntry", textvariable=self.entry_base_type_var)
        self.entry_base_type.pack(side="left")

        # 버튼
        tk.Button(self, text="전주 상세 편집", command=self.open_equipment_editor).pack(side="left")
        tk.Button(self, text="전선 상세 편집", command=self.open_wire_editor).pack(side="left")
        tk.Button(self, text="전주 추가", command=self.add_pole).pack(side="left")
        tk.Button(self, text="전주 삭제", command=self.delete_pole).pack(side="left")
        tk.Button(self, text="파일에서 전주 추가", command=self.add_pole_with_file).pack(side="left")
        tk.Button(self, text="구간 편집 (에어조인트·에어섹션·흐름방지)", command=self.open_section_editor).pack(side="left")

    def on_tree_click(self, event, track):
        tree = self.tree_main if track == "main" else self.tree_sub
        selected_item = tree.selection()
        if not selected_item:
            return


        # load_selected 호출
        self.load_selected()

    def load_data(self):
        if not self.runner:
            print("runner가 아직 초기화되지 않았습니다.")
            return

        if not self.runner.poledata:
            print("poledata가 아직 초기화되지 않았습니다.")
            return

        # 본선 데이터 로딩

        for pole in self.runner.poledata.get("main", []):
            self.tree_main.insert("", "end", values=(
                pole.post_number, pole.pos, pole.span, pole.gauge,
                pole.structure, self._section_cell(pole), pole.base_type,
                pole.radius, pole.pitch, pole.cant, pole.z
            ))

        # 상선 데이터 로딩
        for pole in self.runner.poledata.get("sub", []):
            self.tree_sub.insert("", "end", values=(
                pole.post_number, pole.pos, pole.span, pole.gauge,
                pole.structure, self._section_cell(pole), pole.base_type,
                pole.radius, pole.pitch, pole.cant, pole.z
            ))


    @staticmethod
    def _section_cell(pole):
        """테이블 '구간' 열: 에어조인트/에어섹션 구간, 흐름방지 위치, 일반개소는 None"""
        if pole.section:
            return pole.section
        return getattr(pole, 'flowstop', None)

    # ── 데이터 변경 공통 처리 ─────────────────────────
    def _current_track(self):
        return 'main' if self.notebook.tab(self.notebook.select(), "text") == "본선" else 'sub'

    def commit_change(self, message=None):
        """runner.poledata 를 고친 뒤 호출: 파생 데이터 재계산 → MODEL_CHANGED 로 모든 화면 갱신"""
        rebuild(self.runner)
        if message:
            self.runner.log(message)
        self.notify_model_changed()

    def notify_model_changed(self):
        if self.events:
            self.events.emit(MODEL_CHANGED)
        else:
            self.on_model_changed()

    def on_model_changed(self):
        """편집용 래퍼(EditablePole/Wire) 재생성, 테이블 갱신, 선택 전주 유지"""
        selected = self.selected_pole.pole if self.selected_pole is not None else None
        selected_wire = ((self.selected_wire.wire.track_name, self.selected_wire.wire.pos)
                         if self.selected_wire is not None else None)
        self.create_epoles()
        self.create_ewires()
        self.refresh_tree()
        self.selected_pole = None
        self.selected_wire = None
        if selected_wire is not None:
            track, pos = selected_wire
            self.selected_wire = next((w for w in self.editable_wires.get(track, []) if w.wire.pos == pos), None)
            if self.selected_wire is not None and self.events:
                self.events.emit(WIRE_SELECTED, self.selected_wire)  # 전선 편집기도 새 값으로
        if selected is not None:
            for epoles in self.editable_poles.values():
                found = next((e for e in epoles if e.pole is selected), None)
                if found:
                    self.selected_pole = found
                    if self.events:
                        self.events.emit(POLE_SELECTED, found)  # 다른 화면도 새 래퍼로 갱신
                    break

    def refresh_tree(self):
        if not self.runner.poledata:
            return

        # 본선 트리 초기화
        for row in self.tree_main.get_children():
            self.tree_main.delete(row)
        for pole in self.runner.poledata.get("main", []):
            self.tree_main.insert("", "end", values=(
                pole.post_number, pole.pos, pole.span, pole.gauge,
                pole.structure, self._section_cell(pole), pole.base_type,
                pole.radius, pole.pitch, pole.cant, pole.z
            ))

        # 상선 트리 초기화
        for row in self.tree_sub.get_children():
            self.tree_sub.delete(row)
        for pole in self.runner.poledata.get("sub", []):
            self.tree_sub.insert("", "end", values=(
                pole.post_number, pole.pos, pole.span, pole.gauge,
                pole.structure, self._section_cell(pole), pole.base_type,
                pole.radius, pole.pitch, pole.cant, pole.z
            ))

    def load_selected(self):
        selected_epoles = []
        selected_ewires = []

        # 현재 탭 확인
        current_tab = self.notebook.select()
        tab_text = self.notebook.tab(current_tab, "text")

        if tab_text == "본선":
            for sel in self.tree_main.selection():
                item = self.tree_main.item(sel)
                epole, ewire = self._handle_selection(item, track="main")
                if epole:
                    self.selected_pole = epole
                    selected_epoles.append(epole)
                    # 같은 pos의 상선 전주도 찾기
                    sub_epole = next((e for e in self.editable_poles.get("sub", []) if e.pole.pos == epole.pole.pos),
                                     None)
                    if sub_epole:
                        selected_epoles.append(sub_epole)
                if ewire:
                    self.selected_wire = ewire
                    selected_ewires.append(ewire)

        elif tab_text == "상선":
            for sel in self.tree_sub.selection():
                item = self.tree_sub.item(sel)
                epole, ewire = self._handle_selection(item, track="sub")
                if epole:
                    self.selected_pole = epole
                    selected_epoles.append(epole)
                    # 같은 pos의 본선 전주도 찾기
                    main_epole = next((e for e in self.editable_poles.get("main", []) if e.pole.pos == epole.pole.pos),
                                      None)
                    if main_epole:
                        selected_epoles.append(main_epole)
                if ewire:
                    self.selected_wire = ewire
                    selected_ewires.append(ewire)

        # 이벤트 발행
        if self.events and selected_epoles:
            # 1. 단일 전주 이벤트 (현재 탭에서 선택된 epole)
            self.events.emit(POLE_SELECTED, self.selected_pole)
            # 2. 복수 전주 이벤트 (본선+상선 두 개 epole)
            self.events.emit(POLES_SELECTED, selected_epoles)
            #전선 선택 이벤트
            self.events.emit(WIRE_SELECTED, self.selected_wire)


    def _handle_selection(self, item, track, fill_entry=True):
        post_number, pos, span, gauge, structure, section, base_type, radius, pitch, cant, z = item["values"]

        epole = next((e for e in self.editable_poles.get(track, []) if e.pole.pos == pos), None)
        ewire = next((w for w in self.editable_wires.get(track, []) if w.wire.pos == pos), None)

        if fill_entry and epole:
            self.original_pos = pos
            self.entry_post_number_var.set(post_number)
            self.entry_pos_var.set(pos)
            self.entry_gauge_var.set(gauge)
            self.entry_structure_var.set(structure)
            self.entry_section_var.set(section)
            self.entry_base_type_var.set(base_type)

        return epole, ewire

    def create_epoles(self):
        # EditablePole 리스트 생성
        self.editable_poles = {"main": [], "sub": []}
        if not self.runner.poledata:
            print('poledata is empty')
            return

        for track_name, poles in self.runner.poledata.items():
            prev_epole = None
            for pole in poles:
                epole = EditablePole(
                    pole,
                    self.runner.structure_list,
                    self.runner.curvelist,
                    self.runner.pitchlist,
                    alignment_for(self.runner, track_name),
                    prev_pole=prev_epole
                )
                self.editable_poles[track_name].append(epole)
                if prev_epole:
                    prev_epole.next_pole = epole
                prev_epole = epole

    def create_ewires(self):
        # EditableWire 리스트 생성
        self.editable_wires = {"main": [], "sub": []}
        if not self.runner.wire_data:
            print('wire_data is empty')
            return
        for track_name, wires in self.runner.wire_data.items():
            prev_ewire = None
            for wire in wires:
                ewire = EditableWire(
                    wire,
                    self.runner.structure_list,
                    self.runner.curvelist,
                    self.runner.pitchlist,
                    alignment_for(self.runner, track_name),
                    prev_wire=prev_ewire
                )
                self.editable_wires[track_name].append(ewire)
                if prev_ewire:
                    prev_ewire.next_wire = ewire
                prev_ewire = ewire

    def apply_cell_edit(self, pole, col_index, text):
        """표 셀 편집 반영: 0 전주번호, 1 측점, 3 건식게이지, 6 기본 타입. 반환: 안내 문구 목록"""
        alignment = alignment_for(self.runner, pole.track)
        notices = []
        if col_index == 0:
            pole_edit.rename(self.runner, pole, text)
        elif col_index == 1:
            notices = pole_edit.move_pole(self.runner, pole, float(text), alignment)
        elif col_index == 3:
            _, notices = pole_edit.set_gauge(self.runner, pole, float(text), alignment)
        elif col_index == 6:
            notices = pole_edit.set_base_type(self.runner, pole, text, alignment)
        else:
            raise ValueError('이 열은 편집할 수 없습니다.')
        self.commit_change()
        return notices

    def open_equipment_editor(self):
        """선택한 전주로 전주 상세 편집기 열기 (이후 편집기 선택을 따라감)"""
        return PoleEditor(self.runner, self.events, selection=self.selected_pole)

    def open_section_editor(self):
        """구간 편집기 열기 (선택한 전주 = 추가할 구간의 시작 전주, 이후 편집기 선택을 따라감)"""
        return SectionEditor(self.runner, self.events, selection=self.selected_pole, focus_callback=self.focus_pole)

    def focus_pole(self, track, pos):
        """테이블에서 해당 전주를 선택하고 다른 화면에도 선택을 알림"""
        tree = self.tree_main if track == 'main' else self.tree_sub
        self.notebook.select(0 if track == 'main' else 1)
        for item in tree.get_children():
            if float(tree.item(item, 'values')[1]) == float(pos):
                tree.selection_set(item)
                tree.see(item)
                self.load_selected()
                return True
        return False

    def open_wire_editor(self):
        """선택한 경간으로 전선 상세 편집기 열기 (이후 편집기 선택을 따라감)"""
        return WireEditor(self.runner, self.events, selection=self.selected_wire)

    def add_pole(self):
        track = self._current_track()
        poles = self.runner.poledata[track]
        al = alignment_for(self.runner, track)

        #UI열기
        addui = PoleADDUI()
        self.wait_window(addui)  # 입력창 닫힐 때까지 대기
        values = addui.comfirm()

        if not values:  # 취소 시
            return

        poledict = addui.comfirm()
        side = -1 if poledict['gauge'] < 0 else 1
        # PoleDATA 객체 생성 (필수 속성만, 나머지는 기본값)
        new_pole = ManualPoleProcessor.create_pole(
            al,self.runner.dataprocessor,self.runner.idxlib, self.runner.curvelist, self.runner.pitchlist,self.runner.structure_list,
            int(poledict['pos']), poledict['post_number'], poledict['gauge'], poledict['section'], poledict['base_type'], track, side)

        # pos 기준으로 삽입 위치 찾기
        insert_idx = len(poles)
        for i, p in enumerate(poles):
            if p.pos > new_pole.pos:
                insert_idx = i
                break

        poles.insert(insert_idx, new_pole)
        self.commit_change(f'전주 추가 성공 {new_pole.post_number} at {new_pole.pos}')

    def delete_pole(self):
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if current_tab == "본선":
            tree = self.tree_main
            poles = self.runner.poledata["main"]
        else:
            tree = self.tree_sub
            poles = self.runner.poledata["sub"]

        selected_item = tree.selection()
        if selected_item:
            values = tree.item(selected_item[0], "values")
            post_number = values[0]

            pole = next((p for p in poles if p.post_number == post_number), None)
            if pole is None:
                return
            try:
                notices = pole_edit.delete_pole(self.runner, pole)
            except ValueError as e:
                messagebox.showerror('전주 삭제 불가', str(e))
                return
            if self.selected_pole is not None and not any(p is self.selected_pole.pole for p in poles):
                self.selected_pole = None
            self.commit_change(f'전주 삭제 {post_number}')
            if notices:
                messagebox.showwarning('전주 삭제', '\n'.join(notices))


    def edit_tree_cell(self, event, track):
        tree = self.tree_main if track == "main" else self.tree_sub
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        # 편집 불가능한 열 제한
        # 수정 불가 열: 경간, 구조물, 구간(구간 편집기에서만), 곡선반경, 구배, 캔트, 계획고
        non_editable_cols = [2, 4, 5, 7, 8, 9, 10]
        col_index = int(col_id.replace("#", "")) - 1
        if col_index in non_editable_cols:
            return

        item = tree.item(row_id)
        old_value = item["values"][col_index]

        # 구간(에어조인트·에어섹션) 전주는 표에서 다시 만들면 일반개소 구성품으로 바뀌므로 막음
        pos = float(item["values"][1])
        pole = next((p for p in self.runner.poledata.get(track, []) if float(p.pos) == pos), None)
        if pole is not None and pole.section is not None:
            messagebox.showinfo('전주 편집', f'{pole.post_number} 은(는) {pole.section} 전주입니다.\n'
                                           "구간 전주는 '구간 편집'에서 구간을 삭제한 뒤 편집하세요.")
            return

        # 원래 값 저장
        self._editing_info = {
            "tree": tree,
            "row_id": row_id,
            "col_index": col_index,
            "old_value": old_value
        }

        # 셀 위치 계산
        x, y, width, height = tree.bbox(row_id, col_id)
        #콤보박스 리스트
        base_type_list = ['I', 'O', 'F']

        # 임시 Entry 생성
        col_index_dict = {
            0: tk.StringVar(value=old_value),
            1: tk.StringVar(value=old_value),
            3: tk.StringVar(value=old_value),
            5:tk.StringVar(value=old_value),
            6:tk.StringVar(value=old_value)
        }
        edit_var = col_index_dict.get(col_index)
        entry_dict = {
            0: ttk.Entry(tree, textvariable=edit_var),
            1: ttk.Entry(tree, textvariable=edit_var),
            3: ttk.Entry(tree, textvariable=edit_var),
            6: ttk.Combobox(tree, textvariable=edit_var,values=base_type_list)
        }


        entry = entry_dict.get(col_index)
        entry.place(x=x, y=y, width=width, height=height)

        def save_and_validate(event=None):
            """바뀐 항목만 반영 (전주를 새로 만들지 않아 구성품·전선 편집 유지)"""
            new_value = str(edit_var.get()).strip()
            names = {0: '전주번호', 1: '측점', 3: '건식게이지', 6: '기본 타입'}
            try:
                notices = self.apply_cell_edit(pole, col_index, new_value)
                self.runner.log(f'전주 편집: {pole.post_number} {names[col_index]} → {new_value}')
                if notices:
                    messagebox.showinfo('전주 편집', '\n'.join(notices))
            except (ValueError, tk.TclError) as e:
                messagebox.showerror('전주 편집 실패', str(e))
            entry.destroy()
            self.refresh_tree()
        entry.bind("<Return>", save_and_validate)
        #entry.bind("<FocusOut>", save_and_validate)
        entry.focus()

    def add_pole_with_file(self):
        xlsxname = askopenfilename()
        import pandas as pd
        sheets = pd.read_excel(xlsxname, sheet_name=None)

        for sheet_name, df in sheets.items():
            poles = []  # 시트별 리스트 초기화
            for _, row in df.iterrows():
                post_number = row['전주번호']
                pos = int(row['측점'])
                base_type = row['기본타입']
                section = SectionType.parse(row['구간'])

                current_structure = isbridge_tunnel(pos, self.runner.structure_list)
                gauge = self.runner.dataprocessor.get_pole_gauge(current_structure)
                if self.runner.track_direction[sheet_name] == -1:
                    side = -1
                else:
                    side = 1
                gauge *= side
                new_pole = ManualPoleProcessor.create_pole(
                    self.runner.alignment_by_track[sheet_name],
                    self.runner.dataprocessor,
                    self.runner.idxlib,
                    self.runner.curvelist,
                    self.runner.pitchlist,
                    self.runner.structure_list,
                    pos, post_number, gauge, section, base_type, sheet_name, side
                )

                poles.append(new_pole)

            # 시트별 저장 (연결·전선·흐름방지는 아래에서 한 번에 재계산)
            self.runner.poledata[sheet_name] = poles
        self.selected_pole = None
        self.commit_change(f"엑셀 전주데이터가 로드되었습니다. 계:{len(self.runner.poledata['main'])}")
