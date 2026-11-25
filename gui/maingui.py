"""
AutoPOLE - 전차선로 설계시스템 개선된 메인 UI
원본 코드의 로직은 그대로 유지하면서 UI/UX를 대폭 개선합니다.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import asksaveasfilename, askdirectory, askopenfilename

import pandas as pd

# ──────────────────────────────────────────────
#  아래 import들은 원본 프로젝트 구조에 맞게 유지
# ──────────────────────────────────────────────
from bve.bvecsv import BVECSV
from core.manual_pole_runner import ManualRunner
from core.runner import AutoRunner
from dataset.dataset_getter import DatasetGetter
from dataset.dataset_manager import load_dataset
from event.event_controller import EventController
from event.events import MODEL_CHANGED
from core.model_rebuilder import normalize
from file_io.filemanager import write_to_file, save_runner, load_runner
from core.dataset_edit import DatasetDocument
from gui.dataset_gui import DatasetEditor
from gui.maineditor import AutoPoleEditor
from gui.pole_plotter import PlotPoleMap
from xref_module.index_libmgr import IndexLibrary


# ══════════════════════════════════════════════
#  색상 팔레트 & 스타일 상수
# ══════════════════════════════════════════════
PALETTE = {
    "bg":         "#0f1117",   # 최외곽 배경 (거의 검정)
    "surface":    "#1a1d27",   # 패널 배경
    "surface2":   "#22263a",   # 카드 / 프레임
    "border":     "#2e3347",   # 테두리
    "accent":     "#3b82f6",   # 파랑 강조
    "accent2":    "#60a5fa",   # 밝은 파랑
    "success":    "#22c55e",   # 초록
    "warning":    "#f59e0b",   # 주황
    "danger":     "#ef4444",   # 빨강
    "text":       "#e2e8f0",   # 기본 텍스트
    "text_dim":   "#64748b",   # 흐린 텍스트
    "text_label": "#94a3b8",   # 라벨 텍스트
    "log_bg":     "#0a0d13",   # 로그 배경
    "log_fg":     "#4ade80",   # 로그 텍스트 (터미널 녹색)
}

FONT_MONO  = ("Consolas", 9)
FONT_LABEL = ("맑은 고딕", 9)
FONT_BOLD  = ("맑은 고딕", 9, "bold")
FONT_TITLE = ("맑은 고딕", 11, "bold")
FONT_SMALL = ("맑은 고딕", 8)


# ══════════════════════════════════════════════
#  공통 위젯 헬퍼
# ══════════════════════════════════════════════

def styled_frame(parent, **kw):
    kw.setdefault("bg", PALETTE["surface"])
    kw.setdefault("bd", 0)
    return tk.Frame(parent, **kw)


def section_label(parent, text):
    """섹션 구분 헤더 레이블"""
    f = tk.Frame(parent, bg=PALETTE["surface"])
    tk.Label(
        f, text=text, font=FONT_BOLD,
        fg=PALETTE["accent2"], bg=PALETTE["surface"],
        padx=4, pady=2
    ).pack(side="left")
    tk.Frame(f, bg=PALETTE["border"], height=1).pack(
        side="left", fill="x", expand=True, padx=(6, 0)
    )
    return f


def make_entry(parent, label_text, variable, width=9):
    """라벨 + Entry 쌍"""
    f = tk.Frame(parent, bg=PALETTE["surface2"])
    tk.Label(
        f, text=label_text, font=FONT_LABEL,
        fg=PALETTE["text_label"], bg=PALETTE["surface2"],
        padx=4
    ).pack(side="top", anchor="w")
    e = tk.Entry(
        f, textvariable=variable, width=width,
        font=FONT_MONO,
        fg=PALETTE["text"], bg=PALETTE["bg"],
        insertbackground=PALETTE["accent"],
        relief="flat", bd=0,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
    )
    e.pack(side="top", fill="x", padx=4, pady=(0, 4))
    return f


def make_button(parent, text, command, style="normal", **kw):
    """스타일드 버튼"""
    color_map = {
        "normal":  (PALETTE["surface2"],  PALETTE["text"],    PALETTE["border"]),
        "primary": (PALETTE["accent"],    "#ffffff",          PALETTE["accent"]),
        "success": (PALETTE["success"],   "#ffffff",          PALETTE["success"]),
        "danger":  (PALETTE["danger"],    "#ffffff",          PALETTE["danger"]),
        "warning": (PALETTE["warning"],   "#000000",          PALETTE["warning"]),
    }
    bg, fg, hl = color_map.get(style, color_map["normal"])
    btn = tk.Button(
        parent, text=text, command=command,
        font=FONT_LABEL, fg=fg, bg=bg,
        activeforeground=fg,
        activebackground=PALETTE["accent2"] if style == "primary" else bg,
        relief="flat", bd=0, cursor="hand2",
        padx=10, pady=5,
        highlightthickness=1,
        highlightbackground=hl,
        **kw
    )
    # 호버 효과
    def on_enter(e, b=btn, c=PALETTE["accent2"] if style == "primary" else PALETTE["border"]):
        b.config(highlightbackground=c)
    def on_leave(e, b=btn, c=hl):
        b.config(highlightbackground=c)
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def make_radio(parent, text, variable, value):
    return tk.Radiobutton(
        parent, text=text, variable=variable, value=value,
        font=FONT_LABEL,
        fg=PALETTE["text"], bg=PALETTE["surface2"],
        selectcolor=PALETTE["accent"],
        activebackground=PALETTE["surface2"],
        activeforeground=PALETTE["accent2"],
        relief="flat", bd=0, cursor="hand2",
    )


def make_check(parent, text, variable):
    return tk.Checkbutton(
        parent, text=text, variable=variable,
        font=FONT_LABEL,
        fg=PALETTE["text"], bg=PALETTE["surface2"],
        selectcolor=PALETTE["bg"],
        activebackground=PALETTE["surface2"],
        activeforeground=PALETTE["accent2"],
        relief="flat", bd=0, cursor="hand2",
    )


def card(parent, title_text=None, padx=8, pady=6):
    """둥근 테두리 카드 프레임"""
    outer = tk.Frame(parent, bg=PALETTE["border"], bd=0)
    inner = tk.Frame(outer, bg=PALETTE["surface2"], bd=0)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    if title_text:
        hdr = tk.Frame(inner, bg=PALETTE["surface2"])
        hdr.pack(fill="x", padx=padx, pady=(pady, 2))
        tk.Label(
            hdr, text=title_text, font=FONT_BOLD,
            fg=PALETTE["accent2"], bg=PALETTE["surface2"]
        ).pack(side="left")
        tk.Frame(hdr, bg=PALETTE["border"], height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0)
        )
    body = tk.Frame(inner, bg=PALETTE["surface2"])
    body.pack(fill="both", expand=True, padx=padx, pady=(2, pady))
    return outer, body


# ══════════════════════════════════════════════
#  메인 앱
# ══════════════════════════════════════════════

class AutoPoleApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # ── 상태 변수 ──────────────────────────
        self.tunnel_direction = {'main': None, 'sub': None}
        self.db = None
        self.dataset = None
        # 커스텀 모드 전용 데이터셋 경로 (표준 데이터셋은 항상 소스 폴더 config/ 사용)
        self.custom_dataset_json = None
        self.custom_spandata = None
        self.idxlib = None
        self.runner = None   # BaseRunner | None

        # ── 윈도우 기본 설정 ───────────────────
        self.title("AutoPOLE  ─  전차선로 설계시스템")
        self.configure(bg=PALETTE["bg"])
        self.minsize(1100, 720)

        # 원본 객체들 (실제 사용 시 주석 해제)
        self.events = EventController()

        self._apply_ttk_style()
        self._build_ui()

    # ────────────────────────────────────────
    #  ttk 스타일
    # ────────────────────────────────────────
    def _apply_ttk_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Dark.TPanedwindow",
            background=PALETTE["bg"],
            sashrelief="flat",
            sashwidth=4,
        )

    # ────────────────────────────────────────
    #  전체 UI 구성
    # ────────────────────────────────────────
    def _build_ui(self):
        # ① 최상단 타이틀 바
        self._build_titlebar()
        # ② 좌측 사이드바 (설정 패널) + 우측 메인 콘텐츠
        body = tk.Frame(self, bg=PALETTE["bg"])
        body.pack(fill="both", expand=True)

        sidebar = self._build_sidebar(body)
        sidebar.pack(side="left", fill="y", padx=(8, 4), pady=(0, 8))

        self._build_content(body)

        # ③ 하단 로그 패널
        self._build_logpanel()

    # ────────────────────────────────────────
    #  ① 타이틀 바
    # ────────────────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self, bg=PALETTE["surface"], height=48)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # 로고 / 제목
        tk.Label(
            bar, text="⚡ AutoPOLE",
            font=("맑은 고딕", 14, "bold"),
            fg=PALETTE["accent2"], bg=PALETTE["surface"], padx=16
        ).pack(side="left", fill="y")

        tk.Label(
            bar, text="전차선로 설계시스템",
            font=FONT_LABEL, fg=PALETTE["text_dim"], bg=PALETTE["surface"]
        ).pack(side="left", fill="y")

        # 구분선
        tk.Frame(bar, bg=PALETTE["border"], width=1).pack(
            side="left", fill="y", padx=12, pady=8
        )

        # 빠른 액션 버튼들 (타이틀 바 우측)
        btn_configs = [
            ("새로 만들기",   self.run_and_open_editor, "primary"),
            ("CSV 저장",      self.save,                "success"),
            ("데이터 저장",   self.save_pickle,         "normal"),
            ("데이터 로드",   self.load_pickle,         "normal"),
            ("종료",          self.exit_app,            "danger"),
        ]
        for txt, cmd, sty in btn_configs:
            make_button(bar, txt, cmd, style=sty).pack(
                side="left", padx=4, pady=8
            )

    # ────────────────────────────────────────
    #  ② 사이드바 (설정 모음)
    # ────────────────────────────────────────
    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=PALETTE["surface"], width=260)
        sidebar.pack_propagate(False)

        # ── 기본 파라미터 ──
        c_outer, c_body = card(sidebar, "📐 설계 파라미터")
        c_outer.pack(fill="x", pady=(8, 4))

        self.entry_speed_var       = tk.IntVar(value=150)
        self.entry_start_sta_var   = tk.DoubleVar(value=0.0)
        self.entry_end_sta_var     = tk.DoubleVar(value=0.0)
        self.entry_brokenchain_var = tk.DoubleVar(value=0.0)

        for lbl, var in [
            ("설계속도 (km/h)",  self.entry_speed_var),
            ("시작 측점",        self.entry_start_sta_var),
            ("끝 측점",          self.entry_end_sta_var),
            ("파정 (m)",         self.entry_brokenchain_var),
        ]:
            make_entry(c_body, lbl, var).pack(fill="x", pady=2)

        # ── 생성 모드 ──
        c_outer2, c_body2 = card(sidebar, "⚙️ 생성 모드")
        c_outer2.pack(fill="x", pady=4)

        self.gen_mode = tk.StringVar(value="auto")
        self.is_custom_mode = tk.BooleanVar(value=False)
        self.is_create_dxf  = tk.BooleanVar(value=False)

        row1 = tk.Frame(c_body2, bg=PALETTE["surface2"])
        row1.pack(fill="x", pady=2)
        make_radio(row1, "자동 생성", self.gen_mode, "auto").pack(side="left", padx=(0, 8))
        make_radio(row1, "수동 생성", self.gen_mode, "manual").pack(side="left")

        row2 = tk.Frame(c_body2, bg=PALETTE["surface2"])
        row2.pack(fill="x", pady=2)
        make_check(row2, "커스텀 모드", self.is_custom_mode).pack(side="left", padx=(0, 8))
        make_check(row2, "도면 작성 (DXF)", self.is_create_dxf).pack(side="left")
        make_button(c_body2, "커스텀 데이터셋 지정", self.select_custom_dataset).pack(fill="x", pady=(4, 0))

        # ── 트랙 설정 ──
        c_outer3, c_body3 = card(sidebar, "🛤️ 트랙 설정")
        c_outer3.pack(fill="x", pady=4)

        self.track_mode = tk.StringVar(value="single")
        row_tm = tk.Frame(c_body3, bg=PALETTE["surface2"])
        row_tm.pack(fill="x", pady=(0, 6))
        make_radio(row_tm, "단선", self.track_mode, "single").pack(side="left", padx=(0, 8))
        make_radio(row_tm, "복선", self.track_mode, "double").pack(side="left")

        # 단선 방향
        tk.Label(c_body3, text="본선 방향", font=FONT_SMALL,
                 fg=PALETTE["text_dim"], bg=PALETTE["surface2"]).pack(anchor="w")
        self.single_direction = tk.StringVar(value="L")
        row_sd = tk.Frame(c_body3, bg=PALETTE["surface2"])
        row_sd.pack(fill="x", pady=(0, 4))
        make_radio(row_sd, "좌측", self.single_direction, "L").pack(side="left", padx=(0, 8))
        make_radio(row_sd, "우측", self.single_direction, "R").pack(side="left")

        # 터널 방향 (단선)
        self.tunnel_direction['main'] = tk.StringVar(value="R")
        tk.Label(c_body3, text="터널 전주 설치", font=FONT_SMALL,
                 fg=PALETTE["text_dim"], bg=PALETTE["surface2"]).pack(anchor="w")
        row_td = tk.Frame(c_body3, bg=PALETTE["surface2"])
        row_td.pack(fill="x", pady=(0, 6))
        make_radio(row_td, "좌측", self.tunnel_direction['main'], "L").pack(side="left", padx=(0, 8))
        make_radio(row_td, "우측", self.tunnel_direction['main'], "R").pack(side="left")

        # 복선 방향
        self.double_direction = tk.StringVar(value="mainL_subR")
        tk.Label(c_body3, text="복선 배치", font=FONT_SMALL,
                 fg=PALETTE["text_dim"], bg=PALETTE["surface2"]).pack(anchor="w")
        make_radio(c_body3, "본선 L / 상선 R",
                   self.double_direction, "mainL_subR").pack(anchor="w")
        make_radio(c_body3, "본선 R / 상선 L",
                   self.double_direction, "mainR_subL").pack(anchor="w")

        # 선로 중심 간격
        self.track_distance = tk.DoubleVar(value=4.3)
        make_entry(c_body3, "선로중심간격 (m)", self.track_distance, width=8).pack(
            fill="x", pady=(6, 0)
        )

        # 상선 레일번호: 비우면 선로중심간격으로 일정 오프셋, 입력하면 rail_info.txt 의 실제 레일 좌표 사용
        self.sub_rail_key = tk.StringVar(value="")
        make_entry(c_body3, "상선 레일번호 (rail_info)", self.sub_rail_key, width=8).pack(
            fill="x", pady=(6, 0)
        )

        # ── 유틸리티 버튼 ──
        c_outer4, c_body4 = card(sidebar, "🔧 유틸리티")
        c_outer4.pack(fill="x", pady=4)

        util_buttons = [
            ("러너 갱신",        self.update_runner_tracks, "normal"),
            ("라이브러리 갱신",  self.refresh_library,      "normal"),
            ("데이터셋 불러오기", self.on_load_dataset,      "normal"),
            ("데이터셋 편집",    self.edit_dataset,          "normal"),
            ("로그 클리어",      self.clear_log,             "warning"),
        ]
        for txt, cmd, sty, *enabled in util_buttons:
            state = "normal" if (enabled[0] if enabled else True) else "disabled"
            make_button(c_body4, txt, cmd, style=sty, state=state).pack(
                fill="x", pady=2
            )

        # ── 상태 표시 ──
        c_outer5, c_body5 = card(sidebar, "📊 상태")
        c_outer5.pack(fill="x", pady=4)

        self.status_var = tk.StringVar(value="대기 중")
        self.status_lbl = tk.Label(
            c_body5, textvariable=self.status_var,
            font=FONT_MONO, fg=PALETTE["success"], bg=PALETTE["surface2"],
            anchor="w"
        )
        self.status_lbl.pack(fill="x")

        return sidebar

    # ────────────────────────────────────────
    #  ③ 메인 콘텐츠 (에디터 + 플로터)
    # ────────────────────────────────────────
    def _build_content(self, parent):
        content = tk.Frame(parent, bg=PALETTE["bg"])
        content.pack(side="left", fill="both", expand=True)  # ← 반드시 pack 해야 보임
        paned = ttk.PanedWindow(content, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # 좌측 에디터
        editor_wrapper = tk.Frame(paned, bg=PALETTE["surface"], bd=0)
        tk.Label(
            editor_wrapper, text="전주 에디터",
            font=FONT_TITLE, fg=PALETTE["text"], bg=PALETTE["surface"],
            padx=8, pady=6
        ).pack(fill="x")
        tk.Frame(editor_wrapper, bg=PALETTE["border"], height=1).pack(fill="x")

        self.editor_frame = tk.Frame(editor_wrapper, bg=PALETTE["surface"])
        self.editor_frame.pack(fill="both", expand=True)
        # 실제 사용 시:
        self.editor = AutoPoleEditor(self.runner, self.events, master=self.editor_frame)
        self.editor.pack(fill="both", expand=True)

        paned.add(editor_wrapper, weight=1)

        # 우측 플로터
        plotter_wrapper = tk.Frame(paned, bg=PALETTE["surface"], bd=0)
        tk.Label(
            plotter_wrapper, text="배치도",
            font=FONT_TITLE, fg=PALETTE["text"], bg=PALETTE["surface"],
            padx=8, pady=6
        ).pack(fill="x")
        tk.Frame(plotter_wrapper, bg=PALETTE["border"], height=1).pack(fill="x")

        self.plotter_frame = tk.Frame(plotter_wrapper, bg=PALETTE["surface"])
        self.plotter_frame.pack(fill="both", expand=True)
        # 실제 사용 시:
        self.plotter = PlotPoleMap(self.runner, self.events, master=self.plotter_frame)
        self.plotter.pack(fill="both", expand=True)

        paned.add(plotter_wrapper, weight=1)

    # ────────────────────────────────────────
    #  ④ 하단 로그 패널
    # ────────────────────────────────────────
    def _build_logpanel(self):
        log_outer = tk.Frame(self, bg=PALETTE["border"], height=160)
        log_outer.pack(fill="x", side="bottom", padx=8, pady=(0, 8))
        log_outer.pack_propagate(False)

        log_inner = tk.Frame(log_outer, bg=PALETTE["log_bg"])
        log_inner.pack(fill="both", expand=True, padx=1, pady=1)

        # 로그 헤더
        hdr = tk.Frame(log_inner, bg=PALETTE["surface"], height=26)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="▶ 시스템 로그",
            font=FONT_BOLD, fg=PALETTE["accent2"], bg=PALETTE["surface"],
            padx=10
        ).pack(side="left", fill="y")

        # 로그 텍스트
        log_body = tk.Frame(log_inner, bg=PALETTE["log_bg"])
        log_body.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(log_body, bg=PALETTE["surface"],
                                 troughcolor=PALETTE["log_bg"],
                                 width=10, relief="flat", bd=0)
        scrollbar.pack(side="right", fill="y")

        self.log_box = tk.Text(
            log_body,
            font=FONT_MONO,
            fg=PALETTE["log_fg"],
            bg=PALETTE["log_bg"],
            insertbackground=PALETTE["log_fg"],
            relief="flat", bd=0,
            padx=10, pady=6,
            yscrollcommand=scrollbar.set,
            state="normal",
        )
        self.log_box.pack(fill="both", expand=True)
        scrollbar.config(command=self.log_box.yview)

        # 태그 (로그 레벨별 색상)
        self.log_box.tag_config("INFO",    foreground=PALETTE["log_fg"])
        self.log_box.tag_config("WARN",    foreground=PALETTE["warning"])
        self.log_box.tag_config("ERROR",   foreground=PALETTE["danger"])
        self.log_box.tag_config("SUCCESS", foreground="#86efac")

    # ════════════════════════════════════════
    #  원본 로직 메서드 (변경 없음)
    # ════════════════════════════════════════

    def _set_status(self, text, color="success"):
        c = {"success": PALETTE["success"],
             "warning": PALETTE["warning"],
             "error":   PALETTE["danger"],
             "idle":    PALETTE["text_dim"]}.get(color, PALETTE["text"])
        self.status_var.set(text)
        self.status_lbl.config(fg=c)

    def refresh_library(self):
        SHEET_ID   = "1z0aUcuZCxOQp2St3icbQMbOkrSPfJK_8iZ2JKFDbW8c"
        SHEET_NAME = "freeobj"
        URL = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
               f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}")
        self.idxlib = IndexLibrary(pd.read_csv(URL))
        if self.runner:
             self.runner.idxlib = self.idxlib
        self._set_status("라이브러리 갱신 완료")
        self.log_append("라이브러리 갱신 완료", "SUCCESS")

    def exit_app(self):
        self.quit()
        self.destroy()

    def clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)

    def log_append(self, message: str, level: str = "INFO"):
        """로그 박스에 메시지 추가 (레벨별 색상)"""
        self.log_box.config(state="normal")
        self.log_box.insert(tk.END, message + "\n", level)
        self.log_box.see(tk.END)

    def update_inputs(self):
        try:
            if self.gen_mode.get() == 'auto':
                self.runner = AutoRunner()
                self.runner.log_widget = self.log_box
                self.runner.log("현재 모드: 자동 배치모드")
            else:
                self.runner = ManualRunner()
                self.runner.log_widget = self.log_box
                self.runner.log("현재 모드: 수동 배치모드")
            self.runner.designspeed = int(self.entry_speed_var.get())
            self.runner.iscustommode = int(self.is_custom_mode.get())
            self.runner.custom_dataset_json = self.custom_dataset_json
            self.runner.custom_spandata = self.custom_spandata
            self.runner.is_create_dxf = int(self.is_create_dxf.get())
            self.runner.idxlib = self.idxlib
            self.runner.track_mode = self.track_mode.get()
            self.runner.start_station = self.entry_start_sta_var.get()
            self.runner.end_station = self.entry_end_sta_var.get()
            self.runner.brokenchain = self.entry_brokenchain_var.get()
            self._set_status("입력 갱신 완료")
            self.log_append("입력값 갱신됨", "INFO")
            if not self.filepath_getter():
                self.log_append("⚠️ info 파일 경로가 지정되지 않았습니다.", "WARN")
                self._set_status("입력 오류", "error")
                return False
            self._apply_track_settings()
            return True
        except (ValueError, tk.TclError):
            # tk.IntVar/DoubleVar.get() 은 잘못된 숫자에 TclError 를 던진다
            self.log_append("⚠️ 숫자를 입력하세요", "WARN")
            self._set_status("입력 오류", "error")
            return False

    def filepath_getter(self):
        folder      = askdirectory(title='info 파일 경로 지정')
        if not folder:
            return False
        # BVEParser 출력: bve_alignment.txt(좌표·곡선·구배 한 파일) 우선, 없으면 기존 3개 파일
        alignment_path = os.path.join(folder, 'bve_alignment.txt')
        coord_path  = os.path.join(folder, 'bve_coordinates.txt')
        curve_path  = os.path.join(folder, 'curve_info.txt')
        pitch_path  = os.path.join(folder, 'pitch_info.txt')
        rail_info_path = os.path.join(folder, 'rail_info.txt')
        structue_path = askopenfilename(
            title='구조물 파일 열기',
            defaultextension=".xlsx",
            filetypes=[("XLSX files", "*.xlsx")],
        )
        if self.runner:
            self.runner.alignment_file_path = alignment_path if os.path.isfile(alignment_path) else None
            self.runner.coord_file_path     = coord_path
            self.runner.curve_file_path     = curve_path
            self.runner.pitch_file_path     = pitch_path
            self.runner.structure_file_path = structue_path
            self.runner.rail_info_file_path = rail_info_path if os.path.exists(rail_info_path) else None
        return True

    def _apply_track_settings(self):
        """UI의 트랙 방향/간격 설정을 runner에 반영"""
        if self.runner.track_mode == "single":
            self.runner.track_direction['main'] = -1 if self.single_direction.get() == 'L' else 1
            self.runner.track_distance = 0.0
            self.runner.tunnel_direction['main'] = -1 if self.tunnel_direction['main'].get() == 'L' else 1
            self.runner.log(f"현재 모드: 단일 트랙 (본선 {self.runner.track_direction})")
        else:
            if self.double_direction.get() == 'mainL_subR':
                self.runner.track_direction['main'] = -1
                self.runner.track_direction['sub'] = 1
            else:
                self.runner.track_direction['main'] = 1
                self.runner.track_direction['sub'] = -1

            self.runner.track_distance = self.track_distance.get()
            key = self.sub_rail_key.get().strip()
            self.runner.sub_rail_key = int(key) if key else None  # 숫자가 아니면 ValueError
            # 복선 터널은 방향 반전
            self.runner.tunnel_direction['main'] = self.runner.track_direction['main'] * -1
            self.runner.tunnel_direction['sub'] = self.runner.track_direction['sub'] * -1
            self.runner.log(f"현재 모드: 이중 트랙 ({self.runner.track_direction})")

    def update_runner_tracks(self):
        """실행 중 runner의 트랙 관련 속성만 갱신"""
        if not self.runner:
            self.log_append("⚠️ 러너가 없습니다. 먼저 새로 만들기를 실행하세요.", "WARN")
            return
        try:
            self._apply_track_settings()
        except (ValueError, tk.TclError):
            self.log_append("⚠️ 숫자를 입력하세요", "WARN")
            self._set_status("입력 오류", "error")
            return
        self.log_append("트랙 속성 갱신 완료", "SUCCESS")
        self._set_status("트랙 갱신 완료")

    def run_and_open_editor(self):
        try:
            if not self.update_inputs():
                return
            self.refresh_library()
            self.load_dataset()
            self.runner.run()
            self._show_new_runner()
            self._set_status("생성 완료", "success")
            self.log_append("✅ 전주 배치 완료", "SUCCESS")
        except Exception as e:
            messagebox.showerror('에러', f'러너 실행중 오류가 발생했습니다.\n{e}')
            self._set_status("실행 오류", "error")
            self.log_append(f"❌ {e}", "ERROR")

    def _show_new_runner(self):
        """새 runner(실행/로드 결과)를 편집기·배치도에 연결하고 MODEL_CHANGED 로 갱신"""
        self.editor.runner = self.runner
        self.plotter.runner = self.runner
        self.editor.selected_pole = None
        self.plotter.selected_epole = None
        self.plotter.selected_pole = None
        self.events.emit(MODEL_CHANGED)

    def save(self):
        if not self.runner or not self.runner.poledata:
            messagebox.showwarning('저장 오류', '저장할 데이터가 없습니다. 먼저 실행하세요.')
            return
        try:
            # 원본 save 로직 동일
            self.runner.polesaver_main = BVECSV(self.runner.poledata['main'], self.runner.wire_data['main'],
                                                track_index=0)
            t = self.runner.polesaver_main.create_pole_csv()  # 본선 저장
            t2 = self.runner.polesaver_main.create_wire_csv()
            main_path = askdirectory(title='저장 경로 선택')
            if main_path:
                # 선택한 폴더 기준으로 파일명 지정 (이전 저장 경로가 고정되지 않도록 매번 갱신)
                self.runner.pole_path_main = os.path.join(main_path, '전주.txt')
                self.runner.wire_path_main = os.path.join(main_path, '전차선.txt')
                write_to_file(self.runner.pole_path_main, t)
                write_to_file(self.runner.wire_path_main, t2)
                if self.runner.track_mode == "double":
                    self.runner.polesaver_sub = BVECSV(self.runner.poledata['sub'], self.runner.wire_data['sub'],
                                                       track_index=1)
                    s = self.runner.polesaver_sub.create_pole_csv()  # 상선 저장
                    s2 = self.runner.polesaver_sub.create_wire_csv()
                    self.runner.pole_path_sub = os.path.join(main_path, '상선전주.txt')
                    self.runner.wire_path_sub = os.path.join(main_path, '상선전차선.txt')

                    write_to_file(self.runner.pole_path_sub, s)
                    write_to_file(self.runner.wire_path_sub, s2)
                self.runner.log("txt 저장 성공!")
                self._set_status("CSV 저장 완료", "success")
                self.log_append(f"✅ CSV 저장 완료 → {main_path}", "SUCCESS")
            else:
                messagebox.showerror('저장 오류', '경로가 지정되지 않았습니다.')
        except Exception as e:
            messagebox.showerror('치명적 에러', f'저장 중 오류: {e}')
            self.log_append(f"❌ {e}", "ERROR")

    PICKLE_DEFAULT_PATH = 'c:/temp/decatsbve.dat'
    PICKLE_FILETYPES = [("DeCATSBVE data", "*.dat"), ("All files", "*.*")]

    def save_pickle(self):
        if not self.runner:
            messagebox.showwarning('저장 오류', '저장할 데이터가 없습니다. 먼저 실행하세요.')
            return
        path = asksaveasfilename(
            title='데이터 저장',
            initialfile=os.path.basename(self.PICKLE_DEFAULT_PATH),
            defaultextension=".dat",
            filetypes=self.PICKLE_FILETYPES,
        )
        if not path:
            return
        try:
            save_runner(self.runner, path)
        except Exception as e:
            messagebox.showerror('저장 오류', f'데이터 저장 중 오류: {e}')
            self.log_append(f"❌ {e}", "ERROR")
            return
        messagebox.showinfo('정보', '데이터 저장이 완료됐습니다.')
        self.log_append(f"💾 데이터 저장 완료 → {path}", "SUCCESS")
        self._set_status("저장 완료")

    def load_pickle(self):
        path = askopenfilename(title='데이터 로드', filetypes=self.PICKLE_FILETYPES)
        if not path:
            return
        try:
            runner = load_runner(path)
            runner.log_widget = self.log_box
            normalize(runner)  # 구버전 .dat 보정 (전주 uid, 흐름방지 위치 분리, 구간 enum)
            self.runner = runner
            # 저장 당시 설정으로 UI를 맞춘 뒤 라이브러리/데이터셋 재로드
            if int(self.entry_speed_var.get()) != runner.designspeed or bool(self.is_custom_mode.get()) != bool(runner.iscustommode):
                self.log_append(f"저장된 설정으로 변경: 설계속도 {runner.designspeed}, "
                                f"사용자정의 모드 {'ON' if runner.iscustommode else 'OFF'}", "WARN")
            self.entry_speed_var.set(runner.designspeed)
            self.is_custom_mode.set(bool(runner.iscustommode))
            # 저장 당시 커스텀 데이터셋 경로 복원 (구버전 .dat 에는 없음)
            self.custom_dataset_json = getattr(runner, 'custom_dataset_json', None) or self.custom_dataset_json
            self.custom_spandata = getattr(runner, 'custom_spandata', None) or self.custom_spandata
            self.refresh_library()
            self.load_dataset()
            self.runner.polesaver_main = BVECSV(self.runner.poledata["main"], self.runner.wire_data["main"], 0)
            if self.runner.track_mode == "double":
                self.runner.polesaver_sub = BVECSV(self.runner.poledata["sub"], self.runner.wire_data["sub"], 1)

            self._show_new_runner()
        except Exception as e:
            messagebox.showerror('로드 오류', f'데이터 로드 중 오류: {e}')
            self._set_status("로드 오류", "error")
            self.log_append(f"❌ {e}", "ERROR")
            return
        messagebox.showinfo('정보', '데이터 로드가 완료됐습니다.')
        self.log_append("📂 데이터 로드 완료", "SUCCESS")
        self._set_status("로드 완료")

    def select_custom_dataset(self):
        """커스텀 모드용 데이터셋 JSON / spandata xlsx 지정. 둘 다 선택해야 반영"""
        json_path = askopenfilename(title='커스텀 데이터셋 JSON 선택',
                                    filetypes=[("JSON files", "*.json *.JSON"), ("All files", "*.*")])
        if not json_path:
            return False
        xlsx_path = askopenfilename(title='커스텀 경간(spandata) xlsx 선택',
                                    filetypes=[("XLSX files", "*.xlsx"), ("All files", "*.*")])
        if not xlsx_path:
            return False
        self.custom_dataset_json, self.custom_spandata = json_path, xlsx_path
        if self.runner:
            self.runner.custom_dataset_json, self.runner.custom_spandata = json_path, xlsx_path
        self.log_append(f"커스텀 데이터셋 지정: {json_path} / {xlsx_path}", "INFO")
        return True

    def load_dataset(self):
        """데이터셋 로드. 표준: 소스 폴더 config/, 커스텀: 사용자가 지정한 경로. 실패 시 예외"""
        custom = bool(self.is_custom_mode.get())
        if custom and not (self.custom_dataset_json and self.custom_spandata):
            if not self.select_custom_dataset():
                raise ValueError('커스텀 모드입니다. 커스텀 데이터셋 JSON 과 spandata xlsx 를 지정하세요.')
        self.dataset = load_dataset(int(self.entry_speed_var.get()), custom,
                                    self.custom_dataset_json, self.custom_spandata)
        self.db = DatasetGetter(self.dataset)
        if self.runner:
            self.runner.dataprocessor = self.db
        mode = '커스텀' if custom else '표준'
        self.log_append(f"데이터셋 로드됨({mode}): {self.dataset['_source']['json']}", "INFO")

    def on_load_dataset(self):
        """'데이터셋 불러오기' 버튼"""
        try:
            self.load_dataset()
            self._set_status("데이터셋 로드 완료")
        except Exception as e:
            messagebox.showerror('데이터셋 오류', str(e))
            self._set_status("데이터셋 오류", "error")
            self.log_append(f"❌ {e}", "ERROR")

    def edit_dataset(self):
        """데이터셋 편집기 열기: 커스텀 모드면 지정한 커스텀 데이터셋, 아니면 현재 설계속도의 표준 데이터셋"""
        try:
            if bool(self.is_custom_mode.get()) and self.custom_dataset_json and self.custom_spandata:
                doc = DatasetDocument.load(self.custom_dataset_json, self.custom_spandata)
            else:
                doc = DatasetDocument.from_standard(int(self.entry_speed_var.get()))
        except Exception as e:
            messagebox.showerror('데이터셋 편집', f'데이터셋을 열 수 없습니다: {e}')
            return None
        return DatasetEditor(doc, on_use=self.use_custom_dataset)

    def use_custom_dataset(self, json_path, xlsx_path):
        """편집기에서 저장한 데이터셋을 커스텀 데이터셋으로 지정하고 다시 읽음 (다음 실행부터 적용)"""
        self.custom_dataset_json, self.custom_spandata = json_path, xlsx_path
        self.is_custom_mode.set(True)
        if self.runner:
            self.runner.iscustommode = 1
            self.runner.custom_dataset_json, self.runner.custom_spandata = json_path, xlsx_path
        self.on_load_dataset()
        self.log_append("커스텀 데이터셋 지정: 다음 실행부터 적용됩니다 (지금 전주는 다시 실행하거나 "
                        "'자동 구성으로 되돌리기'로 반영)", "INFO")