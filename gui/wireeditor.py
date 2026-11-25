
import tkinter as tk
from tkinter import ttk, messagebox

from core.model_rebuilder import rebuild
from core.wire import wire_overrides
from event.events import MODEL_CHANGED, POLE_SELECTED, WIRE_SELECTED

class WireEditor(tk.Toplevel):
    def __init__(self, runner, event=None):
        super().__init__()
        self.title("전선 편집기")
        self.geometry("600x800")
        self.runner = runner
        self.event = event

        self.current_pole_var = tk.StringVar(value='현재 전주 없음')
        self.epole = None
        self.ewire = None
        # Notebook (탭) 생성
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # 전선 엔트리 리스트
        self.wire_entries = []

        ttk.Label(self, text="현재 전주:").pack(side="top", pady=5)
        ttk.Entry(self, textvariable=self.current_pole_var, state='readonly').pack(side="top", pady=5)


        # +전선 버튼
        tk.Button(self, text="+전선", command=lambda: self.add_wire_tab("새 전선")).pack(side="top", pady=5)
        tk.Button(self, text="-전선", command=self.remove_wire_tab).pack(side="top", pady=5)
        # 적용/닫기 버튼
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="bottom", pady=10)
        tk.Button(btn_frame, text="적용", command=self.commit).pack(side="left", padx=5)
        tk.Button(btn_frame, text="자동값으로 되돌리기", command=self.reset_to_auto).pack(side="left", padx=5)
        tk.Button(btn_frame, text="닫기", command=self.exit_windows).pack(side="left", padx=5)
        self.protocol("WM_DELETE_WINDOW", self.exit_windows)

    def remove_wire_tab(self, index=None):
        # 현재 선택된 탭 인덱스 가져오기
        if index is None:
            index = self.notebook.index(self.notebook.select())

        # Notebook에서 탭 제거
        self.notebook.forget(index)

        # wire_entries에서도 해당 엔트리 제거
        if 0 <= index < len(self.wire_entries):
            self.wire_entries.pop(index)

    def add_wire_tab(self, wire_name="전선", offset=(0, 0), plan_angle=0.0, topdown_angle=0.0,
                     next_offset=None, next_plan_angle=None, next_topdown_angle=None):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=wire_name)
        row = 0

        # 전선 종류
        ttk.Label(frame, text="전선 종류:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        wire_type_var = tk.StringVar()
        ttk.Combobox(frame, textvariable=wire_type_var,
                     values=["급전선", "보호선", '부급전선'], state="readonly").grid(row=row, column=1)

        row += 1
        # 시작점 높이 (읽기전용)
        ttk.Label(frame, text="시작점 높이:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        height_var = tk.DoubleVar(value=offset[1])
        ttk.Entry(frame, textvariable=height_var, state="readonly", style="Readonly.TEntry").grid(row=row, column=1)

        row += 1
        # 시작점 이격거리 (읽기전용)
        ttk.Label(frame, text="시작점 이격거리:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        xoffset_var = tk.DoubleVar(value=offset[0])
        ttk.Entry(frame, textvariable=xoffset_var, state="readonly", style="Readonly.TEntry").grid(row=row, column=1)

        row += 1
        # 끝점 높이 (수정 가능)
        ttk.Label(frame, text="끝점 높이:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        next_height_var = tk.DoubleVar(value=next_offset[1] if next_offset else 0.0)
        ttk.Entry(frame, textvariable=next_height_var).grid(row=row, column=1)

        row += 1
        # 끝점 이격거리 (수정 가능)
        ttk.Label(frame, text="끝점 이격거리:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        next_xoffset_var = tk.DoubleVar(value=next_offset[0] if next_offset else 0.0)
        ttk.Entry(frame, textvariable=next_xoffset_var).grid(row=row, column=1)

        row += 1
        # 평면 각도 (읽기전용)
        ttk.Label(frame, text="평면 각도:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        plan_angle_var = tk.DoubleVar(value=plan_angle)
        ttk.Entry(frame, textvariable=plan_angle_var, state="readonly", style="Readonly.TEntry").grid(row=row, column=1)

        row += 1
        # 종단 각도 (읽기전용)
        ttk.Label(frame, text="종단 각도:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        slope_angle_var = tk.DoubleVar(value=topdown_angle)
        ttk.Entry(frame, textvariable=slope_angle_var, state="readonly", style="Readonly.TEntry").grid(row=row,
                                                                                                       column=1)

        # 저장 구조에 추가
        self.wire_entries.append({
            "frame": frame,
            "wire_type": wire_type_var,
            "wire_name": wire_name,
            "height": height_var,
            "xoffset": xoffset_var,
            "next_height": next_height_var,
            "next_xoffset": next_xoffset_var,
            "plan_angle": plan_angle_var,
            "slope_angle": slope_angle_var
        })

    def exit_windows(self):
        if self.event:  # 닫힌 창이 계속 이벤트를 받지 않도록
            self.event.unbind(POLE_SELECTED, self.on_pole_selected)
            self.event.unbind(WIRE_SELECTED, self.on_wire_selected)
        self.destroy()

    def _span_positions(self):
        """편집이 영향을 주는 경간(앞 전주 pos): 현재 + 앞뒤 (끝점·시작점이 서로 맞춰지므로)"""
        positions = [self.ewire.wire.pos]
        if self.ewire.prev_wire:
            positions.append(self.ewire.prev_wire.wire.pos)
        if self.ewire.next_wire:
            positions.append(self.ewire.next_wire.wire.pos)
        return positions

    def _rebuild_and_notify(self):
        """전선 편집 내용(경간 단위)을 반영해 재계산하고 모든 화면 갱신"""
        rebuild(self.runner)
        if self.event:
            self.event.emit(MODEL_CHANGED)

    def reset_to_auto(self):
        if not self.ewire:
            messagebox.showerror('에러', '전선이 선택되지 않았습니다.')
            return
        track = self.ewire.wire.track_name
        n = wire_overrides.clear(self.runner, track, self._span_positions())
        self.runner.log(f'전선 편집 초기화: 경간 {n}개를 자동 계산값으로 되돌림')
        self._rebuild_and_notify()

    # 초기화 이후에도 호출 가능
    def bind_events(self):
        self.event.bind(POLE_SELECTED, self.on_pole_selected)
        self.event.bind(WIRE_SELECTED, self.on_wire_selected)

    def on_pole_selected(self, epole):
        if not self.winfo_exists():
            return

        self.epole = epole
        if self.epole is not None:
            self.current_pole_var.set(str(self.epole.pole.post_number))

    def clear_wire_tabs(self):
        # Notebook의 모든 탭 제거
        for i in range(len(self.notebook.tabs())):
            self.notebook.forget(0)
        # wire_entries도 초기화
        self.wire_entries.clear()

    def on_wire_selected(self, ewire):
        if not self.winfo_exists():
            return
        self.clear_wire_tabs()
        self.ewire = ewire
        if self.ewire is not None:
            print(f'[디버그]: ewire 수신됨 {ewire}')

            # 현재 wire들 순회
            for i, wire in enumerate(self.ewire.wire.wires):
                next_offset = None
                next_plan_angle = None
                next_topdown_angle = None

                # 다음 wire가 있으면 같은 인덱스 기준으로 매칭
                if self.ewire.next_wire and i < len(self.ewire.next_wire.wire.wires):
                    next_wire = self.ewire.next_wire.wire.wires[i]
                    next_offset = next_wire.offset
                    next_plan_angle = next_wire.adjusted_angle
                    next_topdown_angle = next_wire.topdown_angle

                # 현재 wire + 다음 wire 속성 반영
                self.add_wire_tab(
                    wire_name=wire.label,
                    offset=wire.offset,
                    plan_angle=wire.adjusted_angle,
                    topdown_angle=wire.topdown_angle,
                    next_offset=next_offset,
                    next_plan_angle=next_plan_angle,
                    next_topdown_angle=next_topdown_angle
                )

    def commit(self):
        if not self.ewire:
            messagebox.showerror('에러', '전선이 선택되지 않았습니다.')
            return
        track = self.ewire.wire.track_name
        before = wire_overrides.snapshot(self.runner, track, self._span_positions())
        try:
            for i, entry in enumerate(self.wire_entries):
                if entry:
                    # 현재 wire의 데이터
                    wire_data = {
                        "label": entry["wire_name"],
                        "offset": (entry["xoffset"].get(), entry["height"].get()),  # 시작점
                        "end_point": (entry["next_xoffset"].get(), entry["next_height"].get())  # 끝점
                    }

                    if self.ewire:
                        self.ewire.update(index=i, **wire_data)

                        # --- 인접 wire 자동 갱신 ---
                        # 다음 wire의 시작점(offset)을 현재 wire의 끝점으로 맞춤
                        if self.ewire.next_wire and i < len(self.ewire.next_wire.wire.wires):
                            self.ewire.next_wire.wire.wires[i].offset = wire_data["end_point"]

                        # 이전 wire의 끝점(end_point)을 현재 wire의 시작점으로 맞춤
                        if self.ewire.prev_wire and i < len(self.ewire.prev_wire.wire.wires):
                            self.ewire.prev_wire.wire.wires[i].end_point = wire_data["offset"]

            # 바뀐 지지점을 경간 단위로 보관 → 이후 다른 편집으로 재계산돼도 유지
            n = wire_overrides.record_changes(self.runner, track, before)
            self.runner.log(f'전선 편집 성공! (전선 {n}개 지지점 저장)')
        except Exception as e:
            messagebox.showerror('에러', f'전선 커밋 작업에 실패했습니다. {e}')
            return
        self._rebuild_and_notify()  # 앞뒤 경간 각도까지 다시 계산