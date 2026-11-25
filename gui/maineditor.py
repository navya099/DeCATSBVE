import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import askopenfilename

from core.airjoint.airjoint_processor import AirJointProcessor
from core.airsection.airsection_processor import AirSectionProcessor
from core.pole.manual_pole_processor import ManualPoleProcessor
from core.pole.normal_section_processor import NormalSectionProcessor
from core.pole.tunnel_section_processor import TunnelSectionProcessor
from core.structure.define_structure import isbridge_tunnel
from core.model_rebuilder import alignment_for, rebuild
from event.events import MODEL_CHANGED, POLE_SELECTED, POLES_SELECTED, WIRE_SELECTED
from gui.pole_add_ui import PoleADDUI
from gui.pole_assembler import PoleAssemblerApp
from gui.tkdialog import TkDialogService
from gui.wireeditor import WireEditor
from vms.editable_pole import EditablePole
from vms.editable_wires import EditableWire
from vms.eidtable_bracket import BracketEditor
from xref_module.transaction import Transaction
from enums.section_type import FlowStop, SectionType


class AutoPoleEditor(tk.Frame):
    def __init__(self, runner, objlib, events=None, master=None):
        super().__init__(master)
        self.original_pos = None
        self.selected_wire = None
        self.runner = runner
        self.events = events

        self.editable_poles = {"main": [], "sub": []}
        self.editable_wires = {"main": [], "sub": []}
        self.objlib = objlib
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
        tk.Button(self, text="에어조인트 추가", command=self.add_airjoint).pack(side="left")
        tk.Button(self, text="에어조인트 삭제", command=self.remove_airjoint).pack(side="left")
        tk.Button(self, text="흐름방지장치 추가", command=self.add_antidevice).pack(side="left")
        tk.Button(self, text="흐름방지장치 삭제", command=self.remove_antidevice).pack(side="left")
        tk.Button(self, text="에어섹션 추가", command=self.add_airsection).pack(side="left")
        tk.Button(self, text="에어섹션 제거", command=self.remove_airsection).pack(side="left")

    def on_tree_click(self, event, track):
        tree = self.tree_main if track == "main" else self.tree_sub
        selected_item = tree.selection()
        if not selected_item:
            return

        # 선택된 행의 values 가져오기
        item = tree.item(selected_item[0])
        values = item["values"]

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

    def save_edit(self, post_number, pos, gauge, section, base_type, side):
        track = self._current_track()
        poles = self.runner.poledata[track]
        al = alignment_for(self.runner, track)

        new_post_number = post_number
        new_pos = pos
        new_gauge = gauge
        new_section = section
        new_base_type = base_type
        new_side = side

        # PoleDATA 객체 생성 (필수 속성만, 나머지는 기본값)
        new_pole = ManualPoleProcessor.create_pole(
            al, self.runner.dataprocessor, self.runner.idxlib, self.runner.curvelist, self.runner.pitchlist,
            self.runner.structure_list,
            new_pos, new_post_number, new_gauge, new_section,
            new_base_type, track, new_side)

        # pos 기준으로 교체할 위치 찾기
        replace_idx = None
        for i, p in enumerate(poles):
            if p.pos == self.original_pos:  # 기존 pos와 동일한 전주 찾기
                replace_idx = i
                break

        if replace_idx is not None:
            new_pole.uid = poles[replace_idx].uid  # 같은 전주 → 경간 키(전선 편집 내용) 유지
            poles[replace_idx] = new_pole  # 기존 전주 대체
            if self.selected_pole is not None and self.selected_pole.pole.pos == self.original_pos:
                self.selected_pole.pole = new_pole  # 선택 유지

        self.commit_change()
        return True
    def open_equipment_editor(self):
        asemlbapp = PoleAssemblerApp(self.runner, self.objlib ,self.events)
        asemlbapp.bind_events()

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

            # 삭제 후 앞뒤 전주가 이어지는 경간이 전선 경간표에 있는지 확인 (없으면 그 경간 전선이 생성되지 않음)
            idx = next((i for i, p in enumerate(poles) if p.post_number == post_number), None)
            if idx is not None and 0 < idx < len(poles) - 1:
                prev_pole, next_pole = poles[idx - 1], poles[idx + 1]
                new_span = next_pole.pos - prev_pole.pos
                try:
                    self.runner.dataprocessor.get_contact_wire_span(new_span, prev_pole.structure)
                except ValueError:
                    messagebox.showerror('전주 삭제 불가',
                                         f'{post_number}: 삭제하면 {prev_pole.post_number}~{next_pole.post_number} '
                                         f'경간이 {new_span}m 가 되어 경간표에 없습니다.')
                    return

            # runner.poledata에서 제거
            poles[:] = [p for p in poles if p.post_number != post_number]
            if self.selected_pole is not None and not any(p is self.selected_pole.pole for p in poles):
                self.selected_pole = None
            self.commit_change(f'전주 삭제 {post_number}')


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
        non_editable_cols = [2,4, 7,8,9,10]  # 전주번호, 측점은 수정 불가
        col_index = int(col_id.replace("#", "")) - 1
        if col_index in non_editable_cols:
            return

        item = tree.item(row_id)
        old_value = item["values"][col_index]

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
        section_list = ['일반개소', SectionType.AJ_START, SectionType.AJ_2, SectionType.AJ_MIDDLE, SectionType.AJ_4, SectionType.AJ_END]
        base_type_list = ['I', 'O', 'F']

        # 임시 Entry 생성
        col_index_dict = {
            0: tk.StringVar(value=old_value),
            1: tk.IntVar(value=old_value),
            3: tk.DoubleVar(value=old_value),
            5:tk.StringVar(value=old_value),
            6:tk.StringVar(value=old_value)
        }
        edit_var = col_index_dict.get(col_index)
        entry_dict = {
            0: ttk.Entry(tree, textvariable=edit_var),
            1: ttk.Entry(tree, textvariable=edit_var),
            3: ttk.Entry(tree, textvariable=edit_var),
            5: ttk.Combobox(tree, textvariable=edit_var,values=section_list),
            6: ttk.Combobox(tree, textvariable=edit_var,values=base_type_list)
        }


        entry = entry_dict.get(col_index)
        entry.place(x=x, y=y, width=width, height=height)

        def save_and_validate(event=None):
            new_value = edit_var.get()
            values = list(item["values"])
            values[col_index] = new_value
            tree.item(row_id, values=values)
            col_map = {
                0: "post_number",
                1: "pos",
                3: "gauge",
                5: "section",
                6: "base_type"
            }
            try:
                # Treeview 전체 값에서 필요한 인자 추출
                post_number = values[0]
                pos = int(values[1])
                gauge = float(values[3])
                section = SectionType.parse(values[5])  # 일반개소/'None'/흐름방지 위치 → None
                base_type = values[6]
                side = -1 if gauge < 0 else 1
                # 검증 로직 호출
                self.save_edit(post_number, pos, gauge, section, base_type, side)
                self.runner.log(f'전주 편집 성공! {col_map[col_index]}가 {new_value}로 변경되었습니다.')
            except Exception as e:
                code = str(e)
                # 에러코드별 메시지 분기
                if code == "NOT_NORMAL_SECTION":
                    messagebox.showerror("전주 업데이트 실패", "지정한 위치는 일반 개소가 아닙니다.")
                elif code == "SPAN_OUT_OF_RANGE":
                    messagebox.showerror("전주 업데이트 실패", "경간이 지정된 spanlist에 없습니다.")
                else:
                    messagebox.showerror("전주 업데이트 실패", f"다음과 같은 오류가 발생했습니다: {code}")
                # 원래 값 복원
                info = self._editing_info
                values = list(info["tree"].item(info["row_id"], "values"))
                values[info["col_index"]] = info["old_value"]
                info["tree"].item(info["row_id"], values=values)

            # Entry는 임시 객체 → 그냥 날려버림
            entry.destroy()
            self.refresh_tree()
        entry.bind("<Return>", save_and_validate)
        #entry.bind("<FocusOut>", save_and_validate)
        entry.focus()

    def add_airjoint(self):
        self.load_selected()
        mid_epole = self.selected_pole  # EditablePole 유지

        # 5개 전주 확보
        start = mid_epole.prev_pole.prev_pole.pole
        mid_prev = mid_epole.prev_pole.pole
        mid = mid_epole.pole
        mid_next = mid_epole.next_pole.pole
        end = mid_epole.next_pole.next_pole.pole

        if mid.section is not None:
            messagebox.showerror('에러', '지정한 전주는 일반 개소가 아닙니다.')
            return
        # 섹션 변경
        start.section = SectionType.AJ_START
        mid_prev.section = SectionType.AJ_2
        mid.section = SectionType.AJ_MIDDLE
        mid_next.section = SectionType.AJ_4
        end.section = SectionType.AJ_END

        # 처리
        for pole in [start, mid_prev, mid, mid_next, end]:
            AirJointProcessor.process(
                pole,
                alignment_for(self.runner, pole.track),
                self.runner.dataprocessor,
                self.runner.idxlib
            )
        self.commit_change(f'에어조인트가 설치되었습니다. pos:{mid.pos}')

    def remove_airjoint(self):
        self.load_selected()
        mid_epole = self.selected_pole  # EditablePole 유지

        # 5개 전주 확보
        start = mid_epole.prev_pole.prev_pole.pole
        mid_prev = mid_epole.prev_pole.pole
        mid = mid_epole.pole
        mid_next = mid_epole.next_pole.pole
        end = mid_epole.next_pole.next_pole.pole

        if mid.section not in [SectionType.AJ_MIDDLE]:
            messagebox.showerror('에러', '지정한 전주는 에어조인트 설치 개소가 아닙니다.')
            return

        # 섹션 변경
        start.section = None
        mid_prev.section = None
        mid.section = None
        mid_next.section = None
        end.section = None

        # 처리
        for pole in [start, mid_prev, mid, mid_next, end]:
            #기본값으로 되돌리게 리셋
            pole.brackets = []
            pole.mast = None
            pole.equipments = []
            if pole.structure == '터널':
                TunnelSectionProcessor.process(pole, self.runner.dataprocessor, self.runner.idxlib)
            else:
                NormalSectionProcessor.process(pole, self.runner.dataprocessor, self.runner.idxlib)
        self.commit_change(f'에어조인트가 제거되었습니다. pos:{mid.pos}')

    def add_antidevice(self):
        self.load_selected()
        start_pos = self.selected_pole.prev_pole.pole.pos
        mid_pos = self.selected_pole.pole.pos
        end_pos = self.selected_pole.next_pole.pole.pos
        if self.selected_pole.pole.section is not None:
            messagebox.showerror('에러', '지정한 전주는 일반 개소가 아닙니다.')
            return

        for track in self.runner.poledata.keys():
            self.runner.anticreeping_pr.add_manual_section(track, start_pos, end_pos, mid_pos)
        self.runner.log(f'흐름방지 장치가 설치되었습니다. pos:{mid_pos}')
        self.notify_model_changed()
    def remove_antidevice(self):
        self.load_selected()

        start_pos = self.selected_pole.prev_pole.pole.pos
        mid_pos = self.selected_pole.pole.pos
        end_pos = self.selected_pole.next_pole.pole.pos

        if getattr(self.selected_pole.pole, 'flowstop', None) != FlowStop.MIDDLE:
            messagebox.showerror('에러', '지정한 전주는 흐름방지장치 설치 개소가 아닙니다.')
            return
        for track in self.runner.poledata.keys():
            self.runner.anticreeping_pr.remove_manual_section(track, start_pos, end_pos, mid_pos)
        self.runner.log(f'흐름방지 장치가 제거되었습니다. pos:{mid_pos}')
        self.notify_model_changed()

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

    def add_airsection(self):
        app = TkDialogService(self)
        result = app.select_option_list(['에어섹션', '이중에어섹션'])
        self.load_selected()
        start_epole = self.selected_pole  # 시작 전주
        poles = []

        # 시작 전주 포함
        poles.append(start_epole.pole)

        # 이후 7개 확보 (총 8개)
        epole = start_epole
        count = 0
        mode = 'single' if result == '에어섹션' else 'double'
        if mode == 'single':
            count = 4
        elif mode == 'double':
            count = 7

        for _ in range(count):
            if epole.next_pole:
                epole = epole.next_pole
                poles.append(epole.pole)
            else:
                messagebox.showerror('에러', '에어섹션을 구성할 전주가 부족합니다.')
                return

        # 섹션 지정
        poles[0].section = SectionType.AS1_1
        poles[1].section = SectionType.AS1_2
        poles[2].section = SectionType.AS1_3
        poles[3].section = SectionType.AS1_4_D if mode == 'double' else SectionType.AS1_4_S
        poles[4].section = SectionType.AS2_1 if mode == 'double' else SectionType.AS1_5
        if mode == 'double':
            poles[5].section = SectionType.AS2_2
            poles[6].section = SectionType.AS2_3
            poles[7].section = SectionType.AS2_4

        # 처리
        for pole in poles:
            AirSectionProcessor.process(
                pole,
                alignment_for(self.runner, pole.track),
                self.runner.dataprocessor,
                self.runner.idxlib,
                mode=mode
            )
        self.commit_change(f'{result}이 설치되었습니다. 시작 pos:{start_epole.pole.pos}')

    def remove_airsection(self):
        self.load_selected()
        start_epole = self.selected_pole  # 시작 전주
        poles = []

        # 시작 전주 포함
        poles.append(start_epole.pole)

        # 이후 7개 확보 (총 8개)
        epole = start_epole
        count = 0
        mode = "double" if any("에어섹션2구간" in p.section for p in poles) else "single"
        if mode == 'single':
            count = 4
        elif mode == 'double':
            count = 7
        for _ in range(count):
            if epole.next_pole:
                epole = epole.next_pole
                poles.append(epole.pole)
            else:
                messagebox.showerror('에러', '에어섹션을 구성할 전주가 부족합니다.')
                return
        if poles[0].section not in [SectionType.AS1_1]:
            messagebox.showerror('에러', '지정한 전주는 에어섹션 시작 전주가 아닙니다.')
            return
        # 처리
        for pole in poles:
            #기본값으로 되돌리게 리셋
            pole.section = None
            pole.brackets = []
            pole.mast = None
            pole.equipments = []
            if pole.structure == '터널':
                TunnelSectionProcessor.process(pole, self.runner.dataprocessor, self.runner.idxlib)
            else:
                NormalSectionProcessor.process(pole, self.runner.dataprocessor, self.runner.idxlib)
        self.commit_change(f'에어섹션이 제거되었습니다. pos:{start_epole.pole.pos}')
        self.runner.log(f'에어섹션이 제거되었습니다. pos:{start_epole.pole.pos}')