"""
pemfc_gui.py
PEMFC CFD Controller - PyQt5 독립 실행 GUI
"""

import sys
import json
import os
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QRadioButton,
    QTextEdit, QScrollArea, QFrame, QFileDialog, QMessageBox,
    QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


# ════════════════════════════════════════════════════════════════
#  질량분율 계산 유틸
# ════════════════════════════════════════════════════════════════
def _sat_pressure(T_C: float) -> float:
    """포화수증기압 [Pa] — Antoine Equation"""
    log_P = 8.10765 - 1750.286 / (235.0 + T_C)
    return (10 ** log_P) * 133.322


def calc_mass_fractions(T_an, RH_an, P_an, T_ca, RH_ca, P_ca):
    M_H2, M_O2, M_N2, M_H2O = 2.016, 32.000, 28.014, 18.015

    # Anode: H2 + H2O
    P_H2O_an = (RH_an / 100) * _sat_pressure(T_an)
    x_H2     = (P_an - P_H2O_an) / P_an
    x_H2O_an = P_H2O_an / P_an
    M_an     = x_H2 * M_H2 + x_H2O_an * M_H2O
    Y_h2     = x_H2 * M_H2 / M_an
    Y_h2o_an = x_H2O_an * M_H2O / M_an

    # Cathode: O2 + N2 + H2O
    P_H2O_ca = (RH_ca / 100) * _sat_pressure(T_ca)
    P_dry    = P_ca - P_H2O_ca
    x_O2     = 0.21 * P_dry / P_ca
    x_N2     = 0.79 * P_dry / P_ca
    x_H2O_ca = P_H2O_ca / P_ca
    M_ca     = x_O2 * M_O2 + x_N2 * M_N2 + x_H2O_ca * M_H2O
    Y_o2     = x_O2 * M_O2 / M_ca
    Y_h2o_ca = x_H2O_ca * M_H2O / M_ca

    return Y_h2, Y_h2o_an, Y_o2, Y_h2o_ca


# ════════════════════════════════════════════════════════════════
#  확인 다이얼로그
# ════════════════════════════════════════════════════════════════
class ConfirmDialog(QDialog):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl = QLabel(content)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet("font-size: 11pt; line-height: 1.6;")
        layout.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("  취소  ")
        confirm_btn = QPushButton("  ✔ 확인  ")
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet(
            "background-color:#1565C0; color:white;"
            "border-radius:4px; padding:4px 12px; font-weight:bold;"
        )
        cancel_btn.clicked.connect(self.reject)
        confirm_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)


# ════════════════════════════════════════════════════════════════
#  Fluent 실행 설정 다이얼로그
# ════════════════════════════════════════════════════════════════
class FluentLaunchDialog(QDialog):
    """Fluent 연결/시작 전 실행 옵션을 입력받는 다이얼로그"""

    def __init__(self, defaults: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔌 Fluent 실행 설정")
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 16, 18, 14)

        hint = QLabel("Fluent를 시작하기 전에 실행 옵션을 확인하세요.")
        hint.setStyleSheet("color:#555; font-size:10pt;")
        layout.addWidget(hint)

        sep0 = QFrame(); sep0.setFrameShape(QFrame.HLine); sep0.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep0)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Precision
        prec_row = QHBoxLayout()
        prec_row.setSpacing(16)
        self.radio_single = QRadioButton("single")
        self.radio_double = QRadioButton("double")
        if defaults.get("precision", "double") == "single":
            self.radio_single.setChecked(True)
        else:
            self.radio_double.setChecked(True)
        prec_row.addWidget(self.radio_single)
        prec_row.addWidget(self.radio_double)
        prec_row.addStretch()
        prec_w = QWidget(); prec_w.setLayout(prec_row)
        form.addRow("Precision", prec_w)

        # Processor Count
        self.e_proc = QLineEdit(defaults.get("proc_count", "8"))
        self.e_proc.setFixedWidth(70)
        self.e_proc.setPlaceholderText("예: 8")
        form.addRow("Processor Count", self.e_proc)

        # Product Version
        self.e_ver = QLineEdit(defaults.get("product_ver", "25.2.0"))
        self.e_ver.setFixedWidth(100)
        self.e_ver.setPlaceholderText("예: 25.2.0")
        form.addRow("Product Version", self.e_ver)

        # Working Directory
        wd_row = QHBoxLayout()
        wd_row.setSpacing(4)
        self.e_wd = QLineEdit(defaults.get("working_dir", ""))
        self.e_wd.setPlaceholderText("Fluent 작업 폴더 (비우면 현재 디렉터리)")
        browse_btn = QPushButton("📂"); browse_btn.setFixedWidth(30)
        browse_btn.setToolTip("폴더 선택")
        browse_btn.clicked.connect(self._pick_wd)
        wd_row.addWidget(self.e_wd); wd_row.addWidget(browse_btn)
        wd_w = QWidget(); wd_w.setLayout(wd_row)
        form.addRow("Working Dir", wd_w)

        layout.addLayout(form)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine); sep1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("  취소  ")
        run_btn    = QPushButton("  🚀 Fluent 시작  ")
        run_btn.setDefault(True)
        run_btn.setStyleSheet(
            "background-color:#37474F; color:white;"
            "border-radius:4px; padding:5px 14px; font-weight:bold; font-size:11pt;"
        )
        cancel_btn.clicked.connect(self.reject)
        run_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(run_btn)
        layout.addLayout(btn_row)

    def _pick_wd(self):
        p = QFileDialog.getExistingDirectory(self, "Working Directory 선택",
                                             self.e_wd.text() or "")
        if p:
            self.e_wd.setText(p)

    def precision(self) -> str:
        return "double" if self.radio_double.isChecked() else "single"

    def proc_count(self) -> int:
        try:    return int(self.e_proc.text())
        except: return 8

    def product_ver(self) -> str:
        return self.e_ver.text().strip() or "25.2.0"

    def working_dir(self) -> str:
        return self.e_wd.text().strip()


# ════════════════════════════════════════════════════════════════
#  Fluent 작업 스레드 (GUI 프리징 방지)
# ════════════════════════════════════════════════════════════════
class FluentWorker(QThread):
    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    done_signal     = pyqtSignal(bool, str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func   = func
        self.args   = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.func(*self.args, **self.kwargs)
            self.done_signal.emit(True, "완료")
        except Exception as e:
            self.done_signal.emit(False, str(e))


# ════════════════════════════════════════════════════════════════
#  메인 윈도우
# ════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):

    # ── 초기화 ──────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔬 PEMFC CFD Controller")
        self.setMinimumSize(980, 760)
        self.solver     = None
        self._worker    = None
        self._fluent_wd = ""   # Fluent 연결 시 확정된 working directory
        self._config = self._load_config()
        self._build_ui()
        self._restore_values()
        self._update_mode()

    # ── UI 구성 ─────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setSpacing(6)
        root_layout.setContentsMargins(8, 8, 8, 4)

        # 상단: 파라미터(좌) + 버튼(우)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self._make_params_panel(), stretch=3)
        top.addWidget(self._make_buttons_panel(), stretch=2)
        root_layout.addLayout(top)

        # 하단: 로그
        root_layout.addWidget(self._make_log_panel())

        # 상태바
        self._status_lbl  = QLabel("⚪ Fluent 미연결  │  대기 중")
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        credit = QLabel("Made by Han @ ESL")
        credit.setStyleSheet("color: #9E9E9E; font-size: 9pt; padding-right: 6px;")

        self.statusBar().addWidget(self._status_lbl, 1)
        self.statusBar().addPermanentWidget(self._progress_bar)
        self.statusBar().addPermanentWidget(credit)

    # ── 파라미터 패널 ───────────────────────────────────────────
    def _make_params_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)
        lay.addWidget(self._grp_files())
        lay.addWidget(self._grp_conditions())
        lay.addWidget(self._grp_voltage())
        lay.addStretch()

        scroll.setWidget(w)
        return scroll

    def _grp_files(self):
        g = QGroupBox("📁 파일 경로")
        form = QFormLayout(g)
        form.setSpacing(6)

        self.e_case_file = self._file_field(form, "Case File",
                                             "Case 파일 (*.cas.h5 *.cas)")
        self.e_save_dir = self._dir_field(form, "Save Dir")
        self.e_mesh_file  = self._file_field(form, "Mesh File",
                                              "Mesh 파일 (*.msh *.cas)")
        return g

    def _grp_conditions(self):
        g = QGroupBox("⚡ 운전 조건")
        lay = QVBoxLayout(g)
        lay.setSpacing(6)

        # ── 입력 방식 토글 ──
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(16)
        self.radio_cond_calc   = QRadioButton("조건 계산")
        self.radio_cond_direct = QRadioButton("직접 입력")
        self.radio_cond_calc.setChecked(True)
        self.radio_cond_calc.toggled.connect(self._update_cond_mode)
        toggle_row.addWidget(self.radio_cond_calc)
        toggle_row.addWidget(self.radio_cond_direct)
        toggle_row.addStretch()
        lay.addLayout(toggle_row)

        # ── 조건 계산 패널 (T / RH / P) ──
        self._cond_calc_w = QWidget()
        grid = QGridLayout(self._cond_calc_w)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        grid.addWidget(QLabel("<b>Anode</b>"),   0, 1, Qt.AlignCenter)
        grid.addWidget(QLabel("<b>Cathode</b>"), 0, 2, Qt.AlignCenter)

        rows   = [("온도 (°C)", "T"), ("상대습도 (%)", "RH"), ("압력 (Pa)", "P")]
        an_def = ["80", "100", "101325"]
        ca_def = ["80", "100", "101325"]

        self.an = {}
        self.ca = {}
        for i, ((lbl, key), a, c) in enumerate(zip(rows, an_def, ca_def)):
            grid.addWidget(QLabel(lbl), i + 1, 0)
            ea = QLineEdit(a); ea.setFixedWidth(90)
            ec = QLineEdit(c); ec.setFixedWidth(90)
            grid.addWidget(ea, i + 1, 1, Qt.AlignCenter)
            grid.addWidget(ec, i + 1, 2, Qt.AlignCenter)
            self.an[key] = ea
            self.ca[key] = ec
        lay.addWidget(self._cond_calc_w)

        # ── 직접 입력 패널 (Y 값) ──
        self._cond_direct_w = QWidget()
        dgrid = QGridLayout(self._cond_direct_w)
        dgrid.setSpacing(6)
        dgrid.setContentsMargins(0, 0, 0, 0)

        dgrid.addWidget(QLabel("<b>Anode</b>"),   0, 1, Qt.AlignCenter)
        dgrid.addWidget(QLabel("<b>Cathode</b>"), 0, 2, Qt.AlignCenter)

        patch_rows = [
            ("Y_H2",       "Y_h2",    True,  False),
            ("Y_H2O",      "Y_h2o",   True,  True ),
            ("Y_O2",       "Y_o2",    False, True ),
        ]
        self.patch = {}
        for i, (lbl, key, has_an, has_ca) in enumerate(patch_rows):
            dgrid.addWidget(QLabel(lbl), i + 1, 0)
            if has_an:
                e = QLineEdit(); e.setFixedWidth(90); e.setPlaceholderText("0.0000")
                dgrid.addWidget(e, i + 1, 1, Qt.AlignCenter)
                self.patch[f"an_{key}"] = e
            if has_ca:
                e = QLineEdit(); e.setFixedWidth(90); e.setPlaceholderText("0.0000")
                dgrid.addWidget(e, i + 1, 2, Qt.AlignCenter)
                self.patch[f"ca_{key}"] = e

        self._cond_direct_w.setVisible(False)
        lay.addWidget(self._cond_direct_w)

        # ── Water Content (공통 — 항상 표시) ──
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        wlam_row = QHBoxLayout()
        wlam_row.addWidget(QLabel("Water Content  λ"))
        self.e_w_lam = QLineEdit("14")
        self.e_w_lam.setFixedWidth(70)
        self.e_w_lam.setToolTip("uds-3 patch 값 (막 내 함수 물 함량)")
        wlam_row.addWidget(self.e_w_lam)
        wlam_row.addStretch()
        lay.addLayout(wlam_row)

        return g

    def _update_cond_mode(self):
        calc = self.radio_cond_calc.isChecked()
        self._cond_calc_w.setVisible(calc)
        self._cond_direct_w.setVisible(not calc)

    def _grp_voltage(self):
        g = QGroupBox("🔋 전압 설정")
        lay = QVBoxLayout(g)
        lay.setSpacing(6)

        # ── Single Run 전압 ──
        form_single = QFormLayout()
        form_single.setSpacing(6)
        self.e_oper_volt = QLineEdit("0.60")
        form_single.addRow("Oper. Volt (V)", self.e_oper_volt)
        lay.addLayout(form_single)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        # ── IV 입력 방식 토글 ──
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(16)
        self.radio_iv_range  = QRadioButton("범위 입력")
        self.radio_iv_custom = QRadioButton("직접 입력")
        self.radio_iv_range.setChecked(True)
        self.radio_iv_range.toggled.connect(self._update_iv_mode)
        toggle_row.addWidget(self.radio_iv_range)
        toggle_row.addWidget(self.radio_iv_custom)
        toggle_row.addStretch()
        lay.addLayout(toggle_row)

        # ── 범위 입력 위젯 ──
        self._iv_range_w = QWidget()
        form_range = QFormLayout(self._iv_range_w)
        form_range.setSpacing(6)
        form_range.setContentsMargins(0, 0, 0, 0)
        self.e_iv_start = QLineEdit("0.45")
        self.e_iv_end   = QLineEdit("0.90")
        self.e_iv_step  = QLineEdit("0.05")
        for w in (self.e_iv_start, self.e_iv_end, self.e_iv_step):
            w.textChanged.connect(self._refresh_iv_preview)
        form_range.addRow("IV Start (V)", self.e_iv_start)
        form_range.addRow("IV End   (V)", self.e_iv_end)
        form_range.addRow("IV Step  (V)", self.e_iv_step)
        lay.addWidget(self._iv_range_w)

        # ── 직접 입력 위젯 ──
        self._iv_custom_w = QWidget()
        form_custom = QFormLayout(self._iv_custom_w)
        form_custom.setSpacing(6)
        form_custom.setContentsMargins(0, 0, 0, 0)
        self.e_iv_custom = QLineEdit()
        self.e_iv_custom.setPlaceholderText("예: 0.4, 0.55, 0.7, 0.8")
        self.e_iv_custom.textChanged.connect(self._refresh_iv_preview)
        form_custom.addRow("전압 목록 (V)", self.e_iv_custom)
        self._iv_custom_w.setVisible(False)
        lay.addWidget(self._iv_custom_w)

        # ── 미리보기 라벨 ──
        self._iv_preview = QLabel()
        self._iv_preview.setStyleSheet(
            "color:#1565C0; font-size:9pt; padding:2px 4px;"
            "background:#E3F2FD; border-radius:3px;"
        )
        self._iv_preview.setWordWrap(True)
        lay.addWidget(self._iv_preview)
        self._refresh_iv_preview()

        return g

    # ── 버튼 패널 ───────────────────────────────────────────────
    def _make_buttons_panel(self):
        g = QGroupBox("🎮 기능 실행")
        lay = QVBoxLayout(g)
        lay.setSpacing(10)

        # ① Fluent 연결
        self.btn_connect = QPushButton("🔌  Fluent 연결 / 시작")
        self.btn_connect.setFixedHeight(44)
        self.btn_connect.setStyleSheet(self._style("#37474F"))
        self.btn_connect.clicked.connect(self._on_connect)
        lay.addWidget(self.btn_connect)

        lay.addWidget(self._hline())

        # ② Case File Reader
        btn_case = QPushButton("📂  Case File Reader")
        btn_case.setFixedHeight(48)
        btn_case.setStyleSheet(self._style("#1565C0"))
        btn_case.clicked.connect(self._on_case_reader)
        lay.addWidget(btn_case)

        # ③ Run Calculator (Single / Study)
        run_box = QGroupBox("⚡ Run Calculator")
        run_lay = QVBoxLayout(run_box)
        run_lay.setSpacing(4)

        self.radio_single = QRadioButton("Single Run")
        self.radio_study  = QRadioButton("Parameter Study")
        self.radio_single.setChecked(True)
        self.radio_single.toggled.connect(self._update_mode)

        run_lay.addWidget(self.radio_single)
        run_lay.addWidget(self.radio_study)

        btn_run = QPushButton("실행 →")
        btn_run.setFixedHeight(36)
        btn_run.setStyleSheet(self._style("#2E7D32"))
        btn_run.clicked.connect(self._on_run_calculator)
        run_lay.addWidget(btn_run)
        lay.addWidget(run_box)

        # ④ Mesh Replacer
        btn_mesh = QPushButton("🔧  Mesh Replacer")
        btn_mesh.setFixedHeight(48)
        btn_mesh.setStyleSheet(self._style("#6A1B9A"))
        btn_mesh.clicked.connect(self._on_mesh_replacer)
        lay.addWidget(btn_mesh)

        lay.addStretch()
        return g

    # ── 로그 패널 ───────────────────────────────────────────────
    def _make_log_panel(self):
        g = QGroupBox("📋 로그")
        g.setMaximumHeight(160)
        lay = QHBoxLayout(g)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        lay.addWidget(self.log_box)

        btns = QVBoxLayout()
        for icon, slot in [("💾", self._save_log), ("🗑", self.log_box.clear)]:
            b = QPushButton(icon)
            b.setFixedSize(30, 30)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch()
        lay.addLayout(btns)
        return g

    # ── 헬퍼 위젯 ───────────────────────────────────────────────
    def _file_field(self, form, label, filt):
        row = QHBoxLayout()
        edit = QLineEdit()
        btn  = QPushButton("📂"); btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._pick_file(edit, filt))
        row.addWidget(edit); row.addWidget(btn)
        w = QWidget(); w.setLayout(row)
        form.addRow(label, w)
        return edit

    def _dir_field(self, form, label):
        row = QHBoxLayout()
        edit = QLineEdit()
        btn  = QPushButton("📂"); btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._pick_dir(edit))
        row.addWidget(edit); row.addWidget(btn)
        w = QWidget(); w.setLayout(row)
        form.addRow(label, w)
        return edit

    def _hline(self):
        f = QFrame(); f.setFrameShape(QFrame.HLine); f.setFrameShadow(QFrame.Sunken)
        return f

    def _style(self, color):
        return (f"QPushButton{{background-color:{color};color:white;"
                f"border-radius:5px;font-size:12px;font-weight:bold;}}"
                f"QPushButton:hover{{background-color:{color}CC;}}"
                f"QPushButton:pressed{{background-color:{color}99;}}"
                f"QPushButton:disabled{{background-color:#aaa;}}")

    def _start_dir(self, edit: QLineEdit) -> str:
        """파일/폴더 다이얼로그 시작 경로 결정.
        우선순위: ① Fluent 연결 working_dir → ② 필드에 이미 입력된 경로 → ③ 빈 문자열"""
        if self._fluent_wd and os.path.isdir(self._fluent_wd):
            return self._fluent_wd
        current = edit.text().strip()
        if current:
            return os.path.dirname(current) if os.path.isfile(current) else current
        return ""

    def _pick_file(self, edit, filt):
        p, _ = QFileDialog.getOpenFileName(self, "파일 선택", self._start_dir(edit), filt)
        if p: edit.setText(p)

    def _pick_dir(self, edit):
        p = QFileDialog.getExistingDirectory(self, "폴더 선택", self._start_dir(edit))
        if p: edit.setText(p)

    # ── 모드 전환 (Single ↔ Study) ───────────────────────────────
    def _update_mode(self):
        study = self.radio_study.isChecked()
        self.e_oper_volt.setEnabled(not study)
        self.radio_iv_range.setEnabled(study)
        self.radio_iv_custom.setEnabled(study)
        self._iv_range_w.setEnabled(study)
        self._iv_custom_w.setEnabled(study)
        self._iv_preview.setVisible(study)

    # ── IV 입력 방식 전환 (범위 ↔ 직접) ────────────────────────────
    def _update_iv_mode(self):
        is_range = self.radio_iv_range.isChecked()
        self._iv_range_w.setVisible(is_range)
        self._iv_custom_w.setVisible(not is_range)
        self._refresh_iv_preview()

    # ── IV 미리보기 갱신 ────────────────────────────────────────
    def _refresh_iv_preview(self):
        try:
            v_list = self._voltage_list()
            if len(v_list) == 0:
                raise ValueError("빈 목록")
            preview = "  →  " + ",  ".join(f"{v:.2f}" for v in v_list)
            preview += f"    ({len(v_list)} pts)"
            self._iv_preview.setText(preview)
            self._iv_preview.setStyleSheet(
                "color:#1565C0; font-size:9pt; padding:2px 4px;"
                "background:#E3F2FD; border-radius:3px;"
            )
        except Exception:
            self._iv_preview.setText("  ⚠  유효한 전압 값을 입력하세요")
            self._iv_preview.setStyleSheet(
                "color:#B71C1C; font-size:9pt; padding:2px 4px;"
                "background:#FFEBEE; border-radius:3px;"
            )

    # ── 로그 ────────────────────────────────────────────────────
    def _log(self, msg: str):
        t = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{t}] {msg}")

    def _save_log(self):
        p, _ = QFileDialog.getSaveFileName(self, "로그 저장", "pemfc_log.txt",
                                           "텍스트 파일 (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.log_box.toPlainText())

    # ── 공통 값 수집 ─────────────────────────────────────────────
    def _mass_fractions(self):
        """(yh2, yh2o_a, yo2, yh2o_c) 반환"""
        if self.radio_cond_direct.isChecked():
            return (
                float(self.patch["an_Y_h2"].text()),
                float(self.patch["an_Y_h2o"].text()),
                float(self.patch["ca_Y_o2"].text()),
                float(self.patch["ca_Y_h2o"].text()),
            )
        return calc_mass_fractions(
            float(self.an["T"].text()),  float(self.an["RH"].text()),
            float(self.an["P"].text()),
            float(self.ca["T"].text()),  float(self.ca["RH"].text()),
            float(self.ca["P"].text()),
        )

    def _w_lam(self) -> float:
        return float(self.e_w_lam.text())

    def _voltage_list(self):
        if self.radio_iv_custom.isChecked():
            # 직접 입력: 쉼표/공백/세미콜론 구분, 중복 제거 없이 순서 유지
            raw = self.e_iv_custom.text().replace(";", ",").replace(" ", ",")
            tokens = [t.strip() for t in raw.split(",") if t.strip()]
            return [round(float(t), 4) for t in tokens]
        else:
            # 범위 입력
            start = float(self.e_iv_start.text())
            end   = float(self.e_iv_end.text())
            step  = float(self.e_iv_step.text())
            n = round((end - start) / step) + 1
            return [round(start + i * step, 4) for i in range(n)]

    def _conditions_html(self, yh2, yh2o_a, yo2, yh2o_c):
        w_lam = self._w_lam()
        if self.radio_cond_direct.isChecked():
            return (
                f"<b>Patch 값 (직접 입력)</b><br>"
                f"<table cellspacing='4'>"
                f"<tr><td width='160'>anode &nbsp; Y_H2 &nbsp;</td>"
                f"<td>{yh2:.4f}</td></tr>"
                f"<tr><td>anode &nbsp; Y_H2O</td>"
                f"<td>{yh2o_a:.4f}</td></tr>"
                f"<tr><td>cathode Y_O2 &nbsp;</td>"
                f"<td>{yo2:.4f}</td></tr>"
                f"<tr><td>cathode Y_H2O</td>"
                f"<td>{yh2o_c:.4f}</td></tr>"
                f"<tr><td>Water Content λ</td>"
                f"<td>{w_lam:.4g}</td></tr>"
                f"</table><br>"
            )
        T_an  = self.an["T"].text();  RH_an = self.an["RH"].text()
        P_an  = self.an["P"].text()
        T_ca  = self.ca["T"].text();  RH_ca = self.ca["RH"].text()
        P_ca  = self.ca["P"].text()
        return (
            f"<b>운전 조건</b><br>"
            f"<table cellspacing='4'>"
            f"<tr><td width='130'><b>Anode</b></td><td><b>Cathode</b></td></tr>"
            f"<tr><td>T &nbsp;: {T_an} °C</td><td>T &nbsp;: {T_ca} °C</td></tr>"
            f"<tr><td>RH : {RH_an} %</td><td>RH : {RH_ca} %</td></tr>"
            f"<tr><td>P &nbsp;: {P_an} Pa</td><td>P &nbsp;: {P_ca} Pa</td></tr>"
            f"</table><br>"
            f"<b>계산된 질량분율</b><br>"
            f"&nbsp;&nbsp;anode_Y_h2&nbsp;&nbsp; = {yh2:.4f}&nbsp;&nbsp;&nbsp;"
            f"Y_h2o = {yh2o_a:.4f}<br>"
            f"&nbsp;&nbsp;cathode_Y_o2 = {yo2:.4f}&nbsp;&nbsp;"
            f"Y_h2o = {yh2o_c:.4f}<br>"
            f"&nbsp;&nbsp;Water Content λ = {w_lam:.4g}<br><br>"
        )

    # ════════════════════════════════════════════════════════════
    #  버튼 핸들러
    # ════════════════════════════════════════════════════════════

    # ① Fluent 연결
    def _on_connect(self):
        if self.solver is not None:
            QMessageBox.information(self, "알림", "이미 Fluent에 연결되어 있습니다.")
            return

        dlg = FluentLaunchDialog(self._config, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        precision   = dlg.precision()
        proc_count  = dlg.proc_count()
        product_ver = dlg.product_ver()
        working_dir = dlg.working_dir()
        self._config.update({
            "precision":   precision,
            "proc_count":  str(proc_count),
            "product_ver": product_ver,
            "working_dir": working_dir,
        })

        wd_label = working_dir if working_dir else "(현재 디렉터리)"
        self._log(f"Fluent 시작 중  │  {precision} / {proc_count}core / v{product_ver}")
        self._log(f"  Working Dir : {wd_label}")
        self._status_lbl.setText("⏳ Fluent 시작 중...")

        def _launch():
            import ansys.fluent.core as pyfluent
            kwargs = dict(
                precision=precision,
                processor_count=proc_count,
                product_version=product_ver,
                mode="solver",
                ui_mode="gui",
                cleanup_on_exit=False,
            )
            if working_dir:
                kwargs["cwd"] = working_dir
            self.solver = pyfluent.launch_fluent(**kwargs)

        def _on_launch_done(ok, msg):
            if ok:
                try:
                    actual_wd = self.solver.connection_properties.cortex_pwd
                except Exception:
                    actual_wd = working_dir
                self._fluent_wd = actual_wd or working_dir
                if self._fluent_wd:
                    self.e_save_dir.setText(self._fluent_wd)
                self._log("✅ Fluent 연결 완료")
                self._log(f"  Working Dir : {self._fluent_wd or '(기본값)'}")
                self._status_lbl.setText("🟢 Fluent 연결됨  │  대기 중")
            else:
                self._log(f"❌ 연결 실패: {msg}")
                self._status_lbl.setText("🔴 연결 실패")

        self._run_worker(_launch, on_done=_on_launch_done)

    # ② Case File Reader
    def _on_case_reader(self):
        if not self._check_solver(): return
        case_file = self.e_case_file.text().strip()
        if not case_file:
            QMessageBox.warning(self, "경고", "Case File 경로를 입력하세요.")
            return

        content = (
            f"<b>다음 설정으로 실행합니다:</b><br><br>"
            f"<b>Case File</b><br>"
            f"&nbsp;&nbsp;└─ {case_file}<br><br>"
            f"<b>UDF 처리 순서</b><br>"
            f"&nbsp;&nbsp;1. libudf unload<br>"
            f"&nbsp;&nbsp;2. libudf load<br>"
            f"&nbsp;&nbsp;3. rename_UDvars::libudf 실행<br>"
            f"&nbsp;&nbsp;4. Case 재로드"
        )
        dlg = ConfirmDialog("📂 Case File Reader  실행 확인", content, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        self._log("📂 Case File Reader 시작...")
        from pemfc_runner import case_file_reader
        self._run_worker(lambda: case_file_reader(self.solver, case_file),
                         ok_msg="✅ Case File Reader 완료")

    # ③ Run Calculator
    def _on_run_calculator(self):
        if not self._check_solver(): return
        yh2, yh2o_a, yo2, yh2o_c = self._mass_fractions()
        w_lam     = self._w_lam()
        iter_init = 100   # 단순 유동 고정값
        cond_html = self._conditions_html(yh2, yh2o_a, yo2, yh2o_c)
        start_dir = self.e_save_dir.text().strip() or self._fluent_wd or ""

        # ── Single Run ──────────────────────────────────────────
        if self.radio_single.isChecked():
            oper_volt = float(self.e_oper_volt.text())
            content = (
                cond_html +
                f"<b>단순 유동 반복</b> : {iter_init} iter<br>"
                f"<b>전기화학 반응</b> : 수렴 시 자동 종료<br>"
                f"<b>운전 전압</b> : {oper_volt} V"
            )
            dlg = ConfirmDialog("⚡ Run Calculator (Single Run)  실행 확인", content, self)
            if dlg.exec_() != QDialog.Accepted:
                return

            # 저장 파일 선택
            save_path, _ = QFileDialog.getSaveFileName(
                self, "결과 파일 저장", start_dir,
                "Case Data (*.cas.h5);;All Files (*)"
            )
            if not save_path:
                return
            # 확장자 자동 보정
            if not save_path.endswith(".cas.h5"):
                save_path += ".cas.h5"

            self._log(f"⚡ Single Run 시작...  →  {save_path}")
            from pemfc_runner import run_calculator
            self._run_worker(
                lambda: run_calculator(self.solver, yh2, yh2o_a, yo2, yh2o_c,
                                       w_lam, iter_init, oper_volt, save_path),
                ok_msg="✅ Single Run 완료"
            )

        # ── Parameter Study ─────────────────────────────────────
        else:
            v_list = self._voltage_list()
            v_str  = " → ".join(str(v) for v in v_list)
            content = (
                cond_html +
                f"<b>단순 유동 반복</b> : {iter_init} iter  (첫 번째 전압에서만)<br>"
                f"<b>전기화학 반응</b> : 수렴 시 자동 종료<br>"
                f"<b>IV 전압 목록</b> : {v_str} &nbsp;({len(v_list)} pts)"
            )
            dlg = ConfirmDialog("⚡ Run Calculator (Parameter Study)  실행 확인",
                                content, self)
            if dlg.exec_() != QDialog.Accepted:
                return

            # 저장 기본 파일명 선택
            # 예: C:\results\run01  →  run01_70V.cas.h5, run01_85V.cas.h5, ...
            v_labels = "  /  ".join(
                f"{int(round(v*100))}V" for v in v_list
            )
            save_base, _ = QFileDialog.getSaveFileName(
                self, f"저장 기본 파일명 선택  (자동 추가: _{v_labels}.cas.h5)",
                start_dir, "Base Name (*)"
            )
            if not save_base:
                return
            # 사용자가 확장자를 붙였으면 제거
            for ext in (".cas.h5", ".cas", ".h5"):
                if save_base.endswith(ext):
                    save_base = save_base[: -len(ext)]
                    break

            # 미리보기 로그
            self._log(f"⚡ Parameter Study 시작...  기본 파일명: {save_base}")
            for v in v_list:
                self._log(f"  저장 예정: {save_base}_{int(round(v*100))}V.cas.h5")

            from pemfc_runner import parameter_study
            self._run_worker(
                lambda: parameter_study(self.solver, yh2, yh2o_a, yo2, yh2o_c,
                                        w_lam, iter_init, v_list, save_base),
                ok_msg="✅ Parameter Study 완료"
            )

    # ④ Mesh Replacer
    def _on_mesh_replacer(self):
        if not self._check_solver(): return
        mesh_file = self.e_mesh_file.text().strip()
        if not mesh_file:
            QMessageBox.warning(self, "경고", "Mesh File 경로를 입력하세요.")
            return

        content = (
            f"<b>다음 설정으로 실행합니다:</b><br><br>"
            f"<b>Mesh File</b><br>"
            f"&nbsp;&nbsp;└─ {mesh_file}"
        )
        dlg = ConfirmDialog("🔧 Mesh Replacer  실행 확인", content, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        self._log("🔧 Mesh Replacer 시작...")
        from pemfc_runner import mesh_replacer
        self._run_worker(
            lambda: mesh_replacer(self.solver, mesh_file),
            ok_msg="✅ Mesh Replacer 완료"
        )

    # ════════════════════════════════════════════════════════════
    #  워커 실행 공통 로직
    # ════════════════════════════════════════════════════════════
    def _run_worker(self, func, ok_msg: str = "완료", on_done=None):
        self._progress_bar.setRange(0, 0)   # 인디케이터 모드
        self._status_lbl.setText("⏳ 실행 중...")
        self._worker = FluentWorker(func)

        def _finished(ok, msg):
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(100 if ok else 0)
            if on_done:
                on_done(ok, msg)
            elif ok:
                self._log(ok_msg)
                self._status_lbl.setText("🟢 Fluent 연결됨  │  대기 중")
            else:
                self._log(f"❌ 오류: {msg}")
                self._status_lbl.setText("🔴 오류 발생  │  대기 중")

        self._worker.done_signal.connect(_finished)
        self._worker.start()

    def _check_solver(self) -> bool:
        if self.solver is None:
            QMessageBox.warning(self, "경고",
                                "Fluent에 연결되지 않았습니다.\n"
                                "'Fluent 연결 / 시작' 버튼을 먼저 누르세요.")
            return False
        return True

    # ════════════════════════════════════════════════════════════
    #  Config 저장 / 복원
    # ════════════════════════════════════════════════════════════
    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self):
        cfg = {
            "precision":   self._config.get("precision",   "double"),
            "proc_count":  self._config.get("proc_count",  "8"),
            "product_ver": self._config.get("product_ver", "25.2.0"),
            "working_dir": self._config.get("working_dir", ""),
            "case_file":  self.e_case_file.text(),
            "save_dir": self.e_save_dir.text(),
            "mesh_file":  self.e_mesh_file.text(),
            "cond_mode": "direct" if self.radio_cond_direct.isChecked() else "calc",
            "T_an":  self.an["T"].text(),  "RH_an": self.an["RH"].text(),
            "P_an":  self.an["P"].text(),
            "T_ca":  self.ca["T"].text(),  "RH_ca": self.ca["RH"].text(),
            "P_ca":  self.ca["P"].text(),
            "patch_an_Y_h2":  self.patch["an_Y_h2"].text(),
            "patch_an_Y_h2o": self.patch["an_Y_h2o"].text(),
            "patch_ca_Y_o2":  self.patch["ca_Y_o2"].text(),
            "patch_ca_Y_h2o": self.patch["ca_Y_h2o"].text(),
            "w_lam": self.e_w_lam.text(),
            "oper_volt": self.e_oper_volt.text(),
            "iv_mode":   "custom" if self.radio_iv_custom.isChecked() else "range",
            "iv_start":  self.e_iv_start.text(),
            "iv_end":    self.e_iv_end.text(),
            "iv_step":   self.e_iv_step.text(),
            "iv_custom": self.e_iv_custom.text(),
            "mode": "study" if self.radio_study.isChecked() else "single",
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _restore_values(self):
        c = self._config

        for attr, key in [
            ("e_case_file",  "case_file"),  ("e_save_dir", "save_dir"),
            ("e_mesh_file",  "mesh_file"),
            ("e_oper_volt",  "oper_volt"),  ("e_iv_start",   "iv_start"),
            ("e_iv_end",     "iv_end"),     ("e_iv_step",    "iv_step"),
            ("e_iv_custom",  "iv_custom"),
            ("e_w_lam",      "w_lam"),
        ]:
            if key in c:
                getattr(self, attr).setText(c[key])

        for key in ("T", "RH", "P"):
            if f"{key.lower()}_an" in c: self.an[key].setText(c[f"{key.lower()}_an"])
            if f"{key.lower()}_ca" in c: self.ca[key].setText(c[f"{key.lower()}_ca"])

        for attr, key in [
            ("patch_an_Y_h2",  "patch_an_Y_h2"),
            ("patch_an_Y_h2o", "patch_an_Y_h2o"),
            ("patch_ca_Y_o2",  "patch_ca_Y_o2"),
            ("patch_ca_Y_h2o", "patch_ca_Y_h2o"),
        ]:
            if key in c:
                self.patch[attr.replace("patch_", "")].setText(c[key])

        if c.get("mode") == "study":
            self.radio_study.setChecked(True)
        if c.get("iv_mode") == "custom":
            self.radio_iv_custom.setChecked(True)
        if c.get("cond_mode") == "direct":
            self.radio_cond_direct.setChecked(True)

    def closeEvent(self, event):
        self._save_config()
        event.accept()


# ════════════════════════════════════════════════════════════════
#  진입점
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = app.palette()
    palette.setColor(palette.Window, QColor("#F5F5F5"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
