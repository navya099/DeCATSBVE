import tkinter as tk

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.backends._backend_tk import NavigationToolbar2Tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import filedialog, messagebox

from matplotlib.collections import LineCollection

from core.model_rebuilder import alignment_for, rebuild
from event.events import MODEL_CHANGED, POLE_SELECTED, POLES_SELECTED
from core.pole import pole_edit
from core.pole import pole_units
from xref_module.dxf_controller.dxf_controller import DXFController
from xref_module.preview.preview_sevice import PreviewService
from xref_module.preview.preview_viewer import PreviewViewer


class PlotPoleMap(tk.Frame):
    def __init__(self, runner, events=None, master=None):
        super().__init__(master)
        self.selected_epole = None
        self.selected_epoles = []      # 같은 측점의 본선+상선 (미리보기·도면 저장 대상)
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
        self.toolbar = toolbar

        # 배치도 클릭으로 전주 선택: 가장 가까운 전주(복주는 앞/뒤 각각)를 select_callback(트랙, 행 키) 으로 알림
        # (메인 앱이 편집기 테이블 선택에 연결 → 다른 화면도 그 선택을 따라감)
        self.select_callback = None
        self.pick_tolerance_px = 12
        self.canvas.mpl_connect('button_press_event', self.on_click)

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

    def _require_selection(self, title):
        if not self.selected_epoles:
            messagebox.showwarning(title, '편집기 테이블에서 전주를 먼저 선택하세요.')
            return False
        return True

    def show_preview(self):
        if not self._require_selection('전주 미리보기'):
            return
        self.viewer.objects.clear()
        missing_all = []
        # 오프셋 적용
        if self.runner.track_direction['main'] == -1:
            direction = 1
        else:
            direction = -1

        for i, lis in enumerate(self.selected_epoles):
            result = self.service.build(lis.pole, i, self.runner.track_distance, direction, mode=self.runner.track_mode,
                                            idxlib=self.runner.idxlib)
            for obj in result.objects:
                self.viewer.add_object(obj)
            missing_all.extend(result.missing)
        if missing_all:
            messagebox.showwarning(
                '일부 파일 누락',
                '다음 파일을 찾을 수 없습니다:\n\n' + '\n'.join(missing_all[:15])
                + (f'\n… 외 {len(missing_all) - 15}건' if len(missing_all) > 15 else '')
                + "\n\n(BVE Object 폴더는 '유틸리티 > BVE Object 폴더 지정'에서 바꿀 수 있습니다)"
            )
        self.viewer.draw()

    def save_dxf(self):
        """선택 전주 도면(DXF) 저장 — 저장 위치를 묻는다 (이전: c:/temp 고정, 폴더가 없으면 실패)"""
        if not self._require_selection('도면 저장'):
            return
        first = self.selected_epoles[0]
        default_name = pole_units.unit_label(first.pole, getattr(first, 'which', None))
        filename = filedialog.asksaveasfilename(
            title='도면 저장 (DXF)', defaultextension='.dxf', initialfile=f'{default_name}.dxf',
            filetypes=[('DXF', '*.dxf'), ('모든 파일', '*.*')])
        if not filename:
            return
        try:
            self.viewer.objects.clear()
            missing_all = []
            # 오프셋 적용
            if self.runner.track_direction['main'] == -1:
                direction = 1
            else:
                direction = -1

            for i, lis in enumerate(self.selected_epoles):
                result = self.service.build(lis.pole, i, self.runner.track_distance, direction, mode=self.runner.track_mode,
                                            idxlib=self.runner.idxlib)
                for obj in result.objects:
                    self.viewer.add_object(obj)
                missing_all.extend(result.missing)
            if missing_all:
                messagebox.showwarning(
                    '일부 파일 누락',
                    '다음 파일을 찾을 수 없습니다:\n\n' + '\n'.join(missing_all[:15])
                    + (f'\n… 외 {len(missing_all) - 15}건' if len(missing_all) > 15 else '')
                    + "\n\n(BVE Object 폴더는 '유틸리티 > BVE Object 폴더 지정'에서 바꿀 수 있습니다)"
                )
        except Exception as e:
            messagebox.showwarning(
                '예외 발생',
                f'save_dxf 처리중 예외가 발생했습니다. {e}'
            )
            return

        try:
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
        main_coords = np.array(self.unit_coords("main"))
        if len(main_coords) > 0:
            self.ax.scatter(
                main_coords[:, 0], main_coords[:, 1],
                c="blue", marker="o", label="본선 전주"
            )

        # 상선 전주 좌표 배열
        sub_coords = np.array(self.unit_coords("sub"))
        if len(sub_coords) > 0:
            self.ax.scatter(
                sub_coords[:, 0], sub_coords[:, 1],
                c="green", marker="^", label="상선 전주"
            )

        self.ax.legend()
        self.canvas.draw_idle()

    def unit_coords(self, track):
        """실제 전주 좌표 목록 (복주 지지점은 앞·뒤 전주 2개)"""
        al = alignment_for(self.runner, track)
        return [u.coord(al) for u in pole_units.track_units(self.runner.poledata.get(track, []))]

    def nearest_unit(self, x_px, y_px):
        """화면 좌표(픽셀) → 가장 가까운 전주 단위 (트랙, PoleUnit). 허용 거리 밖이면 None"""
        if not self.runner or not self.runner.poledata:
            return None
        best = None
        to_px = self.ax.transData.transform
        for track, poles in self.runner.poledata.items():
            al = alignment_for(self.runner, track)
            units = pole_units.track_units(poles)
            if not units:
                continue
            coords = np.array([u.coord(al) for u in units], dtype=float)
            px = to_px(coords)
            d = np.hypot(px[:, 0] - x_px, px[:, 1] - y_px)
            i = int(np.argmin(d))
            if d[i] <= self.pick_tolerance_px and (best is None or d[i] < best[0]):
                best = (float(d[i]), track, units[i])
        return None if best is None else (best[1], best[2])

    def on_click(self, event):
        """왼쪽 클릭 → 가까운 전주 선택 (확대/이동 도구를 쓰는 중이면 무시)"""
        if event.button != 1 or event.inaxes is not self.ax or event.dblclick:
            return
        if getattr(self.toolbar, 'mode', ''):
            return
        found = self.nearest_unit(event.x, event.y)
        if found is None or self.select_callback is None:
            return
        track, unit = found
        self.select_callback(track, unit.key)

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
            self.highlight_pole(self.selected_pole.pos, getattr(self.selected_epole, 'which', None),
                                pole=self.selected_pole)

    def highlight_pole(self, pos, which=None, pole=None):
        """선택 전주 강조. 복주면 which(0 앞 / 1 뒤) 전주 위치에, 전주번호도 '-F' / '-B'"""
        if pole is None:
            pole = next((p for poles in self.runner.poledata.values() for p in poles if p.pos == pos), None)
        if pole is None:
            self.canvas.draw_idle()
            return
        self.selected_pole = pole
        unit = pole_units.PoleUnit(pole, which if getattr(pole, 'twin', None) is not None else None)
        self.sel_xy = unit.coord(alignment_for(self.runner, pole.track))
        label = unit.label

        if self.selected_pole_scatter:
            self.selected_pole_scatter.set_offsets([self.sel_xy])  # 기존 강조 위치 갱신
        else:
            self.selected_pole_scatter = self.ax.scatter(self.sel_xy[0], self.sel_xy[1], c="red", s=100, zorder=5)
        if getattr(self, "selected_pole_text", None):
            self.selected_pole_text.set_position(self.sel_xy)
            self.selected_pole_text.set_text(label)
        else:
            self.selected_pole_text = self.ax.text(self.sel_xy[0], self.sel_xy[1], label)

        # 뷰포트: 선택 전주가 이미 화면 안이면 확대 상태 유지 (배치도 클릭 선택), 밖이면 ±50m 로 이동
        (x0, x1), (y0, y1) = sorted(self.ax.get_xlim()), sorted(self.ax.get_ylim())
        visible = x0 <= self.sel_xy[0] <= x1 and y0 <= self.sel_xy[1] <= y1 and (x1 - x0) <= 400
        if not visible:
            self.ax.set_xlim(self.sel_xy[0] - 50, self.sel_xy[0] + 50)
            self.ax.set_ylim(self.sel_xy[1] - 50, self.sel_xy[1] + 50)
        self.canvas.draw_idle()

    def on_pole_selected(self, epole):
        self.selected_epole = epole
        self.highlight_pole(epole.pole.pos, getattr(epole, 'which', None), pole=epole.pole)

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