import tkinter as tk

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.backends._backend_tk import NavigationToolbar2Tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import messagebox

from matplotlib.collections import LineCollection

from core.model_rebuilder import alignment_for, rebuild
from event.events import MODEL_CHANGED, POLE_SELECTED, POLES_SELECTED
from core.pole import pole_edit
from xref_module.dxf_controller.dxf_controller import DXFController
from xref_module.preview.preview_sevice import PreviewService
from xref_module.preview.preview_viewer import PreviewViewer


class PlotPoleMap(tk.Frame):
    def __init__(self, runner, events=None, master=None):
        super().__init__(master)
        self.selected_epole = None
        self.selected_pole_scatter = None
        self.sel_xy = None
        self.selected_pole = None
        self.runner = runner
        self.events = events
        if self.events:
            self.events.bind(POLE_SELECTED, self.on_pole_selected)
            self.events.bind(POLES_SELECTED, self.on_poles_selected)
            self.events.bind(MODEL_CHANGED, self.on_model_changed)

        # Matplotlib Figure/Axes 생성
        plt.rcParams['font.family'] = 'Malgun Gothic'
        plt.rcParams['axes.unicode_minus'] = False

        self.fig, self.ax = plt.subplots(figsize=(8,8))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # 툴바 추가
        toolbar = NavigationToolbar2Tk(self.canvas, self)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")

        # 이동 버튼 등록
        btn_left = tk.Button(self, text="-1m", command=self.move_left)
        btn_right = tk.Button(self, text="+1m", command=self.move_right)
        btn_left.pack(side="left")
        btn_right.pack(side="right")
        btn_preview = tk.Button(self, text="전주 미리보기", command=self.show_preview)
        btn_preview.pack(side="bottom")
        btn_savedxf = tk.Button(self, text="도면 저장", command=self.save_dxf)
        btn_savedxf.pack(side="bottom")

        # ✅ 미리보기 뷰어를 한 번만 생성
        self.viewer = PreviewViewer()
        self.viewer.set_projection('front')

        self.service = PreviewService()

    def show_preview(self):
        self.viewer.objects.clear()
        missing_all = []
        # 오프셋 적용
        if self.runner.track_direction['main'] == -1:
            direction = 1
        else:
            direction = -1

        for i, lis in enumerate(self.selected_epoles):
            result = self.service.build(lis.pole, i, self.runner.track_distance, direction, mode=self.runner.track_mode)
            for obj in result.objects:
                self.viewer.add_object(obj)
            missing_all.extend(result.missing)
        if missing_all:
            messagebox.showwarning(
                '일부 파일 누락',
                '다음 파일을 찾을 수 없습니다:\n\n' + '\n'.join(missing_all)
            )
        self.viewer.draw()

    def save_dxf(self):
        try:
            self.viewer.objects.clear()
            missing_all = []
            # 오프셋 적용
            if self.runner.track_direction['main'] == -1:
                direction = 1
            else:
                direction = -1

            for i, lis in enumerate(self.selected_epoles):
                result = self.service.build(lis.pole, i, self.runner.track_distance, direction, mode=self.runner.track_mode)
                for obj in result.objects:
                    self.viewer.add_object(obj)
                missing_all.extend(result.missing)
            if missing_all:
                messagebox.showwarning(
                    '일부 파일 누락',
                    '다음 파일을 찾을 수 없습니다:\n\n' + '\n'.join(missing_all)
                )
        except Exception as e:
            messagebox.showwarning(
                '예외 발생',
                f'save_dxf 처리중 예외가 발생했습니다. {e}'
            )
            return

        try:
            filename = f'c:/temp/{self.selected_epoles[0].pole.post_number}.dxf'

            dxfmgr = DXFController()
            dxfmgr.export_dxf(self.viewer.objects, filename, option='2d')
            messagebox.showinfo("도면 저장 완료", f"DXF 저장 완료: {filename}")
        except Exception as e:
            messagebox.showerror("저장 실패", f"DXF 저장 중 오류 발생:\n{e}")


    def draw_alignment(self):
        # 본선 선형
        if self.runner.polyline_with_sta:
            # (x, y) 좌표 쌍을 라인 세그먼트로 변환
            points = [(x, y) for _, x, y, _ in self.runner.polyline_with_sta]
            segments = [(points[i], points[i + 1]) for i in range(len(points) - 1)]
            lc = LineCollection(segments, colors="gray", linewidths=1, label="본선 선형")
            self.ax.add_collection(lc)

        # 상선 선형
        if self.runner.track_mode == "double" and self.runner.offset_line_with_25:
            points_sub = [(p[1], p[2]) for p in self.runner.offset_line_with_25]
            segments_sub = [(points_sub[i], points_sub[i + 1]) for i in range(len(points_sub) - 1)]
            lc_sub = LineCollection(segments_sub, colors="blue", linewidths=1, linestyles="--", label="상선 선형")
            self.ax.add_collection(lc_sub)

        self.ax.autoscale()  # 좌표 범위 자동 조정
        self.ax.legend()
        self.canvas.draw_idle()

    def draw_poles(self):
        # 본선 전주 좌표 배열
        if not self.runner.poledata:
            return
        main_coords = np.array([pole.coord for pole in self.runner.poledata.get("main", [])])
        if len(main_coords) > 0:
            self.ax.scatter(
                main_coords[:, 0], main_coords[:, 1],
                c="blue", marker="o", label="본선 전주"
            )

        # 상선 전주 좌표 배열
        sub_coords = np.array([pole.coord for pole in self.runner.poledata.get("sub", [])])
        if len(sub_coords) > 0:
            self.ax.scatter(
                sub_coords[:, 0], sub_coords[:, 1],
                c="green", marker="^", label="상선 전주"
            )

        self.ax.legend()
        self.canvas.draw_idle()

    def update_plot(self):
        self.ax.clear()
        self.ax.set_title("전주 위치 맵")
        self.ax.set_xlabel("X좌표")
        self.ax.set_ylabel("Y좌표")

        self.draw_alignment()
        self.draw_poles()
        self.canvas.draw_idle()

    def on_model_changed(self):
        """데이터 변경 시 배치도 다시 그리기 (선택 전주 강조 유지)"""
        if not self.runner:
            return
        self.update_plot()
        # ax.clear() 로 기존 강조 표시가 지워졌으므로 새로 만든다
        self.selected_pole_scatter = None
        self.selected_pole_text = None
        if self.selected_pole is not None:
            self.highlight_pole(self.selected_pole.pos)

    def highlight_pole(self, pos):
        # 선택된 전주 찾기
        for track_name, poles in self.runner.poledata.items():
            for pole in poles:
                if pole.pos == pos:
                    self.selected_pole = pole
                    self.sel_xy = pole.coord[0], pole.coord[1]

                    if hasattr(self, "selected_pole_scatter") and self.selected_pole_scatter:
                        # ✅ 기존 scatter 좌표 갱신
                        self.selected_pole_scatter.set_offsets([self.sel_xy])
                    else:
                        # 처음 선택 시 scatter 생성
                        self.selected_pole_scatter = self.ax.scatter(
                            self.sel_xy[0], self.sel_xy[1],
                            c="red", s=100, zorder=5
                        )

                    # 텍스트도 갱신하거나 새로 추가
                    if hasattr(self, "selected_pole_text") and self.selected_pole_text:
                        self.selected_pole_text.set_position(self.sel_xy)
                        self.selected_pole_text.set_text(f'{pole.post_number}')
                    else:
                        self.selected_pole_text = self.ax.text(
                            self.sel_xy[0], self.sel_xy[1], f'{pole.post_number}'
                        )

                    # 뷰포트 이동
                    self.ax.set_xlim(self.sel_xy[0] - 50, self.sel_xy[0] + 50)
                    self.ax.set_ylim(self.sel_xy[1] - 50, self.sel_xy[1] + 50)
                    break

        self.canvas.draw_idle()

    def on_pole_selected(self, epole):
        self.selected_epole = epole
        self.highlight_pole(epole.pole.pos)

    def on_poles_selected(self, epoles):
        self.selected_epoles = epoles

    def move_left(self):
        self._move_pole(-1)

    def move_right(self):
        self._move_pole(+1)

    def _move_pole(self, delta):
        """선택 전주를 delta(m) 만큼 이동 (검증 후에만 반영, 구성품·전선 편집 유지)"""
        if not self.selected_epole:
            return
        pole = self.selected_epole.pole
        try:
            notices = pole_edit.move_pole(self.runner, pole, pole.pos + delta, alignment_for(self.runner, pole.track))
        except ValueError as e:
            messagebox.showerror('전주 이동', f'{pole.post_number}: {e}')
            return
        self.selected_pole = pole
        rebuild(self.runner)
        self.runner.log(f"전주 {pole.post_number} 이동 완료: {pole.pos}")
        for notice in notices:
            self.runner.log(notice)
        if self.events:
            self.events.emit(MODEL_CHANGED)
        else:
            self.on_model_changed()