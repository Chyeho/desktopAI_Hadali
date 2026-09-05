"""
Live2D 表情 / 动作 调试台（独立运行）

用途：单独跑这个脚本，可拖动滑条实时调整 hiyori 的表情参数、播放动作、
     把满意的一组参数保存为"神态预设"以便后续接入 chatbotUI。

运行：
    python expression_tester.py

不依赖 API Key / chatbot 模块，仅依赖 live2d-py + PySide6（已在 .venv 中）。
"""
import json
import os

import numpy as np                # 读像素计算模型包围盒（自适应缩放居中）
import OpenGL.GL as gl
import live2d.v3 as live2d
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget, QMessageBox,
)

# 模型路径（与 chatbotUI.MODEL_PATH 保持一致）
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Resources", "v3", "hiyori", "hiyori_free_t08.model3.json",
)

# 预设保存文件（项目根目录）
PRESETS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "expression_presets.json"
)

# 面部表情参数（id, 中文标签）
FACE_PARAMS = [
    ("ParamAngleX",     "脸 左右"),
    ("ParamAngleY",     "脸 上下"),
    ("ParamAngleZ",     "头 歪斜"),
    ("ParamEyeLOpen",   "左眼 开"),
    ("ParamEyeROpen",   "右眼 开"),
    ("ParamEyeLSmile",  "左 笑眼"),
    ("ParamEyeRSmile",  "右 笑眼"),
    ("ParamEyeBallX",   "眼珠 X"),
    ("ParamEyeBallY",   "眼珠 Y"),
    ("ParamBrowLForm",  "左眉 形"),
    ("ParamBrowRForm",  "右眉 形"),
    ("ParamMouthForm",  "嘴 形"),
    ("ParamMouthOpenY", "嘴 开"),
    ("ParamCheek",      "脸红"),
]

# 身体/肢体参数（手臂 + 身体旋转）
BODY_PARAMS = [
    ("ParamArmLA",      "左臂 抬"),
    ("ParamArmRA",      "右臂 抬"),
    ("ParamBodyAngleX", "身体 左右"),
    ("ParamBodyAngleY", "身体 上下"),
    ("ParamBodyAngleZ", "身体 歪斜"),
]

# 一键肢体姿态：只设置手臂/身体参数，方便与面部表情叠加（负值 = 手臂上抬）
BODY_PRESETS = [
    ("双手举起", {"ParamArmLA": -10, "ParamArmRA": -10}),
    ("右手举起", {"ParamArmLA": 0,   "ParamArmRA": -10}),
    ("左手举起", {"ParamArmLA": -10, "ParamArmRA": 0}),
    ("双臂放下", {"ParamArmLA": 0,   "ParamArmRA": 0}),
    ("身体左倾", {"ParamBodyAngleX": -10}),
    ("身体右倾", {"ParamBodyAngleX": 10}),
    ("身体前倾", {"ParamBodyAngleY": -10}),
    ("歪头卖萌", {"ParamAngleZ": -20, "ParamBodyAngleZ": -8}),
    ("站姿归位", {"ParamArmLA": 0, "ParamArmRA": 0,
                   "ParamBodyAngleX": 0, "ParamBodyAngleY": 0, "ParamBodyAngleZ": 0}),
]

# hiyori model3.json 中实际定义的动作组
MOTION_GROUPS = ["Idle", "Flick", "FlickDown", "Tap", "Tap@Body", "Flick@Body"]

class Live2DTestWidget(QOpenGLWidget):
    """渲染 hiyori 模型；每帧 Update 后写入滑条参数再 Draw"""

    model_ready = Signal()          # 模型加载完成，通知主窗口构建滑条
    transition_finished = Signal()  # 一次姿态过渡播放完成（动画序列靠它推进下一帧）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.target_params = {}      # {paramId: value} 每帧写入模型
        self.manual_control = True   # 是否每帧写入滑条值
        self.scale_factor = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.need_fit = True         # 渲染前先读像素做一次精确适配
        self.fit_count = 0
        self.motion_playing = False  # 动作播放中（手动控制被临时关闭）
        self.transition = None       # 姿态过渡动画：{"from":{}, "to":{}, "t":0.0, "duration":1.0}
        self.setMinimumSize(360, 480)
        self.resize(420, 560)

    def initializeGL(self) -> None:
        live2d.glInit()
        self.model = live2d.LAppModel()
        self.model.LoadModelJson(MODEL_PATH)
        self.model.Resize(self.width(), self.height())
        self.model.SetScale(self.scale_factor)
        self.model.SetOffset(0, 0)
        # 调试台默认关闭自动眨眼/呼吸，避免与手动滑条冲突
        self.model.SetAutoBreathEnable(False)
        self.model.SetAutoBlinkEnable(False)
        self.startTimer(int(1000 / 60))
        self.model_ready.emit()

    def resizeGL(self, w, h):
        if self.model:
            self.model.Resize(w, h)
            self.model.SetScale(self.scale_factor)
            self.model.SetOffset(self.offset_x, self.offset_y)
            self.need_fit = True    # 窗口变化后重新适配居中

    # ---------- 精确适配：读像素求模型包围盒（与 chatbotUI 同思路） ----------
    def compute_model_bbox(self):
        """读取当前帧，返回模型非透明像素在窗口坐标下的包围盒 (x0, y0, x1, y1)"""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0 or self.model is None:
            return None
        ds = self.devicePixelRatioF()
        rw, rh = max(1, int(w * ds)), max(1, int(h * ds))
        try:
            data = gl.glReadPixels(0, 0, rw, rh, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
        except Exception:
            return None
        arr = np.frombuffer(data, dtype=np.uint8).reshape(rh, rw, 4)
        alpha = arr[:, :, 3]
        ys, xs = np.nonzero(alpha > 0)
        if len(xs) == 0:
            return None
        x0, x1 = xs.min() / ds, xs.max() / ds
        y0_gl, y1_gl = ys.min() / ds, ys.max() / ds
        y0, y1 = h - y1_gl, h - y0_gl
        return x0, y0, x1, y1

    def do_fit(self):
        """迭代逼近：让形象完整居中显示，占窗口约 88%"""
        self.fit_count += 1
        if self.fit_count > 8:
            self.need_fit = False
            return
        bbox = self.compute_model_bbox()
        if bbox is None:
            self.need_fit = False
            return
        x0, y0, x1, y1 = bbox
        mw, mh = x1 - x0, y1 - y0
        if mw <= 1 or mh <= 1:
            self.need_fit = False
            return
        s = min((self.width() * 0.88) / mw, (self.height() * 0.88) / mh)
        s = max(0.05, min(s, 20.0))
        canvas_w = self.model.GetCanvasSize()[0] or 1.0
        px_per_unit = (self.width() / canvas_w) * self.scale_factor
        if abs(s - 1.0) > 0.005:
            self.scale_factor *= s
            px_per_unit *= s
            self.model.SetScale(self.scale_factor)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx = (self.width() / 2 - cx) / px_per_unit
        dy = (self.height() / 2 - cy) / px_per_unit
        self.offset_x += dx
        self.offset_y += dy
        self.model.SetOffset(self.offset_x, self.offset_y)
        if abs(s - 1.0) < 0.02 and abs(dx) * px_per_unit < 2 and abs(dy) * px_per_unit < 2:
            self.need_fit = False
        else:
            self.update()

    def paintGL(self):
        live2d.clearBuffer()
        self.model.Update()
        # 关键：Update 之后、Draw 之前写入手动参数，否则会被 Update 覆盖
        if self.manual_control:
            for pid, val in self.target_params.items():
                try:
                    self.model.SetParameterValue(pid, val, 1.0)
                except Exception:
                    pass
        self.model.Draw()
        if self.need_fit:
            self.do_fit()

    def timerEvent(self, _):
        if not self.isVisible():
            return
        # 动作播放结束后恢复手动控制，滑条继续生效
        if self.motion_playing and self.model and self.model.IsMotionFinished():
            self.motion_playing = False
            self.manual_control = True
        # 姿态过渡：每帧推进插值，把中间值写入 target_params（paintGL 会写进模型）
        if self.transition is not None:
            tr = self.transition
            tr["t"] += 1.0 / 60.0
            p = min(1.0, tr["t"] / tr["duration"])
            e = p * p * (3.0 - 2.0 * p)      # smoothstep 缓动，起止平滑
            for pid, frm in tr["from"].items():
                to = tr["to"].get(pid, frm)
                self.target_params[pid] = frm + (to - frm) * e
            if p >= 1.0:
                for pid, to in tr["to"].items():
                    self.target_params[pid] = to
                self.transition = None
                self.transition_finished.emit()
        self.update()

    def set_param(self, pid, value):
        """滑条拖动时调用"""
        self.target_params[pid] = value

    def reset_params(self):
        self.target_params.clear()

    def play_motion(self, group):
        # 播动作时关闭手动控制，否则动作曲线会被滑条覆盖看不到效果
        self.manual_control = False
        self.motion_playing = True
        try:
            self.model.StartMotion(group, 0, live2d.MotionPriority.FORCE)
        except Exception as e:
            print(f"动作播放失败 {group}: {e}")
            self.motion_playing = False
            self.manual_control = True

    def start_transition(self, to_params, duration):
        """从当前姿态平滑过渡到目标参数集（duration 秒），过渡期间可随时被滑条打断"""
        self.cancel_transition()
        frm = {pid: self.target_params.get(pid, 0.0) for pid in to_params}
        self.transition = {"from": frm, "to": dict(to_params),
                           "t": 0.0, "duration": max(0.1, duration)}

    def cancel_transition(self):
        """取消进行中的过渡（用户拖动滑条时调用）"""
        self.transition = None

    def dump_all_params(self):
        """打印全部参数及取值范围到控制台"""
        ids = self.model.GetParamIds()
        print(f"\n===== 共 {len(ids)} 个参数 =====")
        for i, pid in enumerate(ids):
            p = self.model.GetParameter(i)
            print(f"{pid:25s} min={p.min:7.2f} max={p.max:7.2f} "
                  f"default={p.default:7.2f} cur={p.value:7.2f}")

    def get_slider_snapshot(self):
        """返回当前滑条参数的快照 {pid: value}"""
        return dict(self.target_params)

class MainWindow(QWidget):
    """左侧模型 + 右侧控制面板"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live2D 表情调试台 — hiyori")
        self.resize(960, 600)
        self.sliders = {}       # {paramId: QSlider}
        self.value_labels = {}  # {paramId: QLabel}
        self.param_ranges = {}  # {paramId: (min, max, default)}
        # 动画序列播放状态
        self.anim_frames = []   # 当前播放的动画帧 [{preset, duration}]
        self.anim_index = 0
        self.anim_playing = False
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)

        # 左：模型渲染区
        self.gl_widget = Live2DTestWidget()
        self.gl_widget.model_ready.connect(self._populate_sliders)
        self.gl_widget.transition_finished.connect(self._on_transition_finished)
        root.addWidget(self.gl_widget, stretch=3)

        # 右：控制面板（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.addWidget(self._build_motion_group())
        v.addWidget(self._build_control_group())
        v.addWidget(self._build_face_group())
        v.addWidget(self._build_body_group())
        v.addWidget(self._build_preset_group())
        v.addWidget(self._build_anim_group())
        v.addStretch()
        scroll.setWidget(panel)
        root.addWidget(scroll, stretch=2)

    def _build_motion_group(self):
        box = QGroupBox("动作播放（播放时自动关闭手动控制）")
        h = QHBoxLayout(box)
        for g in MOTION_GROUPS:
            btn = QPushButton(g)
            btn.clicked.connect(lambda _, gg=g: self.gl_widget.play_motion(gg))
            h.addWidget(btn)
        btn_fit = QPushButton("重新适配居中")
        btn_fit.clicked.connect(self._refit_model)
        h.addWidget(btn_fit)
        return box

    def _refit_model(self):
        """重新读取像素并适配模型居中（窗口大小或动作导致位置变化时使用）"""
        self.gl_widget.fit_count = 0
        self.gl_widget.need_fit = True
        self.gl_widget.update()

    def _build_control_group(self):
        box = QGroupBox("控制开关")
        form = QFormLayout(box)

        # 顶部控制开关
        self.chk_manual = QCheckBox("手动控制参数（关掉则恢复自动眨眼/呼吸/动作）")
        self.chk_manual.setChecked(True)
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        form.addRow(self.chk_manual)

        self.chk_blink = QCheckBox("自动眨眼")
        self.chk_blink.toggled.connect(self._on_blink_toggled)
        form.addRow(self.chk_blink)

        self.chk_breath = QCheckBox("自动呼吸")
        self.chk_breath.toggled.connect(self._on_breath_toggled)
        form.addRow(self.chk_breath)

        btn_dump = QPushButton("Dump 全部参数到控制台")
        btn_dump.clicked.connect(self.gl_widget.dump_all_params)
        form.addRow(btn_dump)

        btn_reset = QPushButton("重置所有滑条到默认值")
        btn_reset.clicked.connect(self._reset_sliders)
        form.addRow(btn_reset)
        return box

    def _build_face_group(self):
        box = QGroupBox("面部表情参数（拖滑条实时生效）")
        v = QVBoxLayout(box)
        v.addWidget(QLabel("提示：脸红范围 -1~0（越接近 -1 越红）；嘴形范围 -2~1（正为笑，负为撇嘴）"))
        self.face_form = QFormLayout()
        v.addLayout(self.face_form)
        return box

    def _build_body_group(self):
        box = QGroupBox("身体 / 肢体参数（一键姿态 + 拖滑条）")
        v = QVBoxLayout(box)

        # 一键姿态按钮：只动身体/手臂，表情可在此之上继续叠加
        h = QHBoxLayout()
        for name, vals in BODY_PRESETS:
            btn = QPushButton(name)
            btn.clicked.connect(lambda _, vv=vals: self._apply_body_preset(vv))
            h.addWidget(btn)
        v.addLayout(h)
        v.addWidget(QLabel("一键姿态只设置手臂/身体，可与面部表情叠加后一起保存为神态预设："))

        self.body_form = QFormLayout()
        v.addLayout(self.body_form)
        return box

    def _apply_body_preset(self, vals):
        """把一键姿态的肢体值写入滑条（并确保手动控制开启）"""
        self._stop_playback()
        self.chk_manual.setChecked(True)
        for pid, val in vals.items():
            if pid in self.sliders:
                self.sliders[pid].setValue(int(val * 1000))
            else:
                self.gl_widget.set_param(pid, val)

    def _populate_sliders(self):
        """模型加载完成后，按 FACE_PARAMS / BODY_PARAMS 构建两组滑条"""
        ids = set(self.gl_widget.model.GetParamIds())
        for form, params in ((self.face_form, FACE_PARAMS), (self.body_form, BODY_PARAMS)):
            for pid, label in params:
                if pid not in ids:
                    continue
                idx = self.gl_widget.model.GetParamIds().index(pid)
                p = self.gl_widget.model.GetParameter(idx)
                self.param_ranges[pid] = (p.min, p.max, p.default)

                row = QHBoxLayout()
                sld = QSlider(Qt.Horizontal)
                scale = 1000.0
                sld.setMinimum(int(p.min * scale))
                sld.setMaximum(int(p.max * scale))
                sld.setValue(int(p.default * scale))
                lbl = QLabel(f"{p.default:5.2f}")
                lbl.setMinimumWidth(48)
                sld.valueChanged.connect(
                    lambda v, pp=pid, ll=lbl: self._on_slider_changed(pp, v, ll))
                row.addWidget(sld)
                row.addWidget(lbl)
                container = QWidget()
                container.setLayout(row)
                form.addRow(label, container)
                self.sliders[pid] = sld
                self.value_labels[pid] = lbl
                # 初始化 target_params
                self.gl_widget.set_param(pid, p.default)

    def _on_slider_changed(self, pid, intval, label):
        val = intval / 1000.0
        label.setText(f"{val:5.2f}")
        self._stop_playback()            # 手动拖动 → 停止动画播放并打断过渡
        self.gl_widget.set_param(pid, val)

    def _reset_sliders(self):
        for pid, sld in self.sliders.items():
            _, _, default = self.param_ranges[pid]
            sld.setValue(int(default * 1000))
        self.gl_widget.reset_params()
        # 重新写入默认值
        for pid in self.sliders:
            _, _, default = self.param_ranges[pid]
            self.gl_widget.set_param(pid, default)

    def _on_manual_toggled(self, on):
        self.gl_widget.manual_control = on
        if on:
            # 手动控制时关掉自动眨眼呼吸，避免覆盖
            self.chk_blink.setChecked(False)
            self.chk_breath.setChecked(False)

    def _on_blink_toggled(self, on):
        if self.gl_widget.model:
            self.gl_widget.model.SetAutoBlinkEnable(on)

    def _on_breath_toggled(self, on):
        if self.gl_widget.model:
            self.gl_widget.model.SetAutoBreathEnable(on)

    # ---------- 预设保存/读取 ----------
    def _build_preset_group(self):
        box = QGroupBox("神态预设（保存满意的组合）")
        v = QVBoxLayout(box)

        self.cmb_presets = QComboBox()
        self.cmb_presets.currentIndexChanged.connect(self._apply_preset)
        v.addWidget(QLabel("已保存："))
        v.addWidget(self.cmb_presets)

        h = QHBoxLayout()
        btn_save = QPushButton("保存当前为预设")
        btn_save.clicked.connect(self._save_preset)
        btn_del = QPushButton("删除选中")
        btn_del.clicked.connect(self._delete_preset)
        h.addWidget(btn_save)
        h.addWidget(btn_del)
        v.addLayout(h)

        # 姿态平滑过渡：从当前姿态渐变到所选预设
        h2 = QHBoxLayout()
        self.spn_duration = QDoubleSpinBox()
        self.spn_duration.setRange(0.2, 5.0)
        self.spn_duration.setSingleStep(0.1)
        self.spn_duration.setValue(1.0)
        self.spn_duration.setSuffix(" 秒")
        btn_trans = QPushButton("平滑过渡到所选预设")
        btn_trans.clicked.connect(self._transition_to_preset)
        h2.addWidget(QLabel("过渡时长:"))
        h2.addWidget(self.spn_duration)
        h2.addWidget(btn_trans)
        v.addLayout(h2)
        v.addWidget(QLabel("（预设存到 expression_presets.json）"))

        self._reload_preset_list()
        return box

    def _reload_preset_list(self, keep=""):
        self.cmb_presets.blockSignals(True)
        self.cmb_presets.clear()
        data = self._load_presets()
        names = list(data.keys())
        self.cmb_presets.addItems(names)
        if keep in names:
            self.cmb_presets.setCurrentIndex(names.index(keep))
        self.cmb_presets.blockSignals(False)

    def _load_presets(self):
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"预设读取失败: {e}")
        return {}

    def _save_presets(self, data):
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "保存预设", "神态名称：")
        if not (ok and name.strip()):
            return
        name = name.strip()
        snap = self.gl_widget.get_slider_snapshot()
        # 转成可读浮点
        snap = {k: round(float(v), 4) for k, v in snap.items()}
        data = self._load_presets()
        data[name] = snap
        self._save_presets(data)
        self._reload_preset_list(keep=name)

    def _delete_preset(self):
        name = self.cmb_presets.currentText()
        if not name:
            return
        data = self._load_presets()
        if name in data:
            del data[name]
            self._save_presets(data)
            self._reload_preset_list()

    def _apply_preset(self, _idx):
        name = self.cmb_presets.currentText()
        if not name:
            return
        data = self._load_presets()
        preset = data.get(name, {})
        # 应用预设：开启手动控制，关闭自动眨眼/呼吸
        self._stop_playback()
        self.chk_manual.setChecked(True)
        self.gl_widget.target_params.clear()
        for pid, val in preset.items():
            if pid in self.sliders:
                self.sliders[pid].setValue(int(val * 1000))
        # 不在滑条列表里的参数也写入模型
        for pid, val in preset.items():
            if pid not in self.sliders:
                self.gl_widget.set_param(pid, val)

    def _transition_to_preset(self):
        """从当前姿态平滑过渡到所选预设（不打断过渡，滑条仅同步位置）"""
        name = self.cmb_presets.currentText()
        if not name:
            return
        data = self._load_presets()
        preset = data.get(name, {})
        if not preset:
            return
        self._stop_playback()
        self.chk_manual.setChecked(True)
        # 滑条同步到目标值但不触发信号（避免打断过渡），仅更新显示
        for pid, val in preset.items():
            if pid in self.sliders:
                sld = self.sliders[pid]
                sld.blockSignals(True)
                sld.setValue(int(val * 1000))
                sld.blockSignals(False)
                self.value_labels[pid].setText(f"{val:5.2f}")
        # 启动过渡动画：参数从当前值渐变到目标值
        self.gl_widget.start_transition(preset, self.spn_duration.value())

    # ---------- 动画序列 ----------
    def _anim_file(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "expression_animations.json")

    def _load_anims(self):
        fp = self._anim_file()
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"动画读取失败: {e}")
        return {}

    def _save_anims(self, data):
        with open(self._anim_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _reload_anim_list(self, keep=""):
        self.cmb_anims.blockSignals(True)
        self.cmb_anims.clear()
        names = list(self._load_anims().keys())
        self.cmb_anims.addItems(names)
        if keep in names:
            self.cmb_anims.setCurrentIndex(names.index(keep))
        self.cmb_anims.blockSignals(False)

    def _build_anim_group(self):
        box = QGroupBox("动画序列（多个预设串联成动画，一键循环播放）")
        v = QVBoxLayout(box)
        v.addWidget(QLabel("① 选中预设 → 设时长 → 添加为帧，可排序/改时长；② 保存序列；③ 播放"))

        self.lst_anim_frames = QListWidget()
        self.lst_anim_frames.setMaximumHeight(120)
        v.addWidget(self.lst_anim_frames)

        h1 = QHBoxLayout()
        self.spn_frame_dur = QDoubleSpinBox()
        self.spn_frame_dur.setRange(0.2, 5.0)
        self.spn_frame_dur.setSingleStep(0.1)
        self.spn_frame_dur.setValue(1.0)
        self.spn_frame_dur.setSuffix(" 秒")
        btn_add = QPushButton("添加选中预设为帧")
        btn_add.clicked.connect(self._add_anim_frame)
        h1.addWidget(QLabel("帧时长:"))
        h1.addWidget(self.spn_frame_dur)
        h1.addWidget(btn_add)
        v.addLayout(h1)

        h2 = QHBoxLayout()
        btn_upd = QPushButton("改时长")
        btn_upd.clicked.connect(self._update_selected_frame_dur)
        btn_del = QPushButton("删帧")
        btn_del.clicked.connect(self._remove_anim_frame)
        btn_up = QPushButton("上移")
        btn_up.clicked.connect(lambda: self._move_anim_frame(-1))
        btn_down = QPushButton("下移")
        btn_down.clicked.connect(lambda: self._move_anim_frame(1))
        for b in (btn_upd, btn_del, btn_up, btn_down):
            h2.addWidget(b)
        v.addLayout(h2)

        btn_save_seq = QPushButton("保存当前帧序列为动画…")
        btn_save_seq.clicked.connect(self._save_anim_sequence)
        v.addWidget(btn_save_seq)

        h3 = QHBoxLayout()
        self.cmb_anims = QComboBox()
        self.chk_loop = QCheckBox("循环")
        self.chk_loop.setChecked(True)
        btn_play = QPushButton("播放")
        btn_play.clicked.connect(self._start_playback)
        btn_stop = QPushButton("停止")
        btn_stop.clicked.connect(self._stop_playback)
        btn_del_anim = QPushButton("删动画")
        btn_del_anim.clicked.connect(self._delete_anim_sequence)
        h3.addWidget(self.cmb_anims, stretch=1)
        h3.addWidget(self.chk_loop)
        h3.addWidget(btn_play)
        h3.addWidget(btn_stop)
        h3.addWidget(btn_del_anim)
        v.addLayout(h3)
        v.addWidget(QLabel("（动画存到 expression_animations.json，帧引用已保存的神态预设）"))

        self._reload_anim_list()
        return box

    def _add_anim_frame(self):
        name = self.cmb_presets.currentText()
        if not name:
            return
        self.lst_anim_frames.addItem(
            f"{name}  @  {self.spn_frame_dur.value():.1f}s")

    def _current_anim_frames(self):
        """把列表控件内容解析为 [{preset, duration}]"""
        frames = []
        for i in range(self.lst_anim_frames.count()):
            text = self.lst_anim_frames.item(i).text()
            preset, _, dur = text.rpartition("  @  ")
            frames.append({"preset": preset, "duration": float(dur.rstrip("s"))})
        return frames

    def _update_selected_frame_dur(self):
        row = self.lst_anim_frames.currentRow()
        if row < 0:
            return
        frames = self._current_anim_frames()
        frames[row]["duration"] = self.spn_frame_dur.value()
        self.lst_anim_frames.takeItem(row)
        self.lst_anim_frames.insertItem(
            row, f"{frames[row]['preset']}  @  {frames[row]['duration']:.1f}s")
        self.lst_anim_frames.setCurrentRow(row)

    def _remove_anim_frame(self):
        row = self.lst_anim_frames.currentRow()
        if row >= 0:
            self.lst_anim_frames.takeItem(row)

    def _move_anim_frame(self, delta):
        row = self.lst_anim_frames.currentRow()
        new = row + delta
        if row < 0 or new < 0 or new >= self.lst_anim_frames.count():
            return
        item = self.lst_anim_frames.takeItem(row)
        self.lst_anim_frames.insertItem(new, item)
        self.lst_anim_frames.setCurrentRow(new)

    def _save_anim_sequence(self):
        frames = self._current_anim_frames()
        if not frames:
            return
        name, ok = QInputDialog.getText(self, "保存动画", "动画名称：")
        if not (ok and name.strip()):
            return
        name = name.strip()
        data = self._load_anims()
        data[name] = frames
        self._save_anims(data)
        self._reload_anim_list(keep=name)

    def _delete_anim_sequence(self):
        name = self.cmb_anims.currentText()
        if not name:
            return
        data = self._load_anims()
        if name in data:
            del data[name]
            self._save_anims(data)
            self._reload_anim_list()

    def _start_playback(self):
        name = self.cmb_anims.currentText()
        if not name:
            return
        data = self._load_anims()
        self.anim_frames = data.get(name, [])
        if not self.anim_frames:
            return
        self.anim_playing = True
        self.anim_index = 0
        self.chk_manual.setChecked(True)
        self._play_anim_frame(0)

    def _stop_playback(self):
        self.anim_playing = False
        self.gl_widget.cancel_transition()

    def _play_anim_frame(self, i):
        """播放序列第 i 帧（平滑过渡到该帧引用的预设）"""
        if not (0 <= i < len(self.anim_frames)):
            self._stop_playback()
            return
        frame = self.anim_frames[i]
        presets = self._load_presets()
        preset = presets.get(frame["preset"], {})
        if not preset:
            print(f"动画缺预设: {frame['preset']}，已跳过")
            self.anim_index = i
            self._advance_anim()
            return
        self.lst_anim_frames.setCurrentRow(i)
        self.gl_widget.start_transition(preset, frame["duration"])

    def _advance_anim(self):
        """上一帧过渡完成 → 播下一帧（或循环/停止）"""
        if not self.anim_playing:
            return
        self.anim_index += 1
        if self.anim_index >= len(self.anim_frames):
            if self.chk_loop.isChecked():
                self.anim_index = 0
            else:
                self._stop_playback()
                return
        self._play_anim_frame(self.anim_index)

    def _on_transition_finished(self):
        """任何一次过渡完成时触发（仅动画播放中才推进）"""
        if self.anim_playing:
            self._advance_anim()

def main():
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    live2d.init()
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()
    live2d.dispose()

if __name__ == "__main__":
    main()