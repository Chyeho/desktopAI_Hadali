'''Live2D 渲染部件：固定神态 + 情感动作播放

线程约定（与 P3 前一致，未改变）：
- `Model.*` 只在 Qt 主线程执行（timerEvent / paintGL / 主线程槽）
- 其它线程（传输线程、TTS 线程）只能通过 `request_play_motion` 信号请求播放动作
'''
import time

import numpy as np            # 数值计算：把 glReadPixels 读回的字节流转成数组分析像素
import OpenGL.GL as gl        # OpenGL 底层 API：读像素（包围盒检测、拖拽判定）
import live2d.v3 as live2d    # live2d-py 第三方封装（v3 版 Cubism SDK）
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from client.live2d_behavior import (
    denormalize_cursor,
    normalize_cursor,
    smooth_toward,
)
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

# Live2D 模型路径（按项目根定位，保证拆分到 client/ui/ 后仍能找到资源）
MODEL_PATH = get_abs_path("Resources/v3/hiyori/hiyori_free_t08.model3.json")

# 表情动作播放结束后，参数平滑过渡回常态的时长（秒）
NEUTRAL_RETURN_DURATION = 1.5

# 鼠标跟随的逐帧平滑系数（0~1，越大越跟手；120fps 下 0.25 约 90ms 收敛）
CURSOR_SMOOTH_FACTOR = 0.25


class Live2DWidget(QOpenGLWidget):
    """渲染 Live2D 模型的部件（形象自动适配窗口并居中，随窗口等比缩放）

    核心功能：
    - 自动适配：初始化后读取帧像素，动态调整缩放/偏移，让形象完整居中显示
    - 等比缩放：滚轮只缩放窗口，模型由 resizeGL 跟随，形象始终占窗口固定比例
    - 像素级交互：通过 glReadPixels 判断鼠标是否落在模型上（拖拽/点击）
    """

    # 跨线程请求播放表情动作（传输线程 emit → 主线程槽执行 StartMotion）
    request_play_motion = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.model = None
        self.motion_started = False
        self.scale_factor = 1.0   # 模型缩放倍数（由 do_fit 动态计算）
        self.offset_x = 0.0       # 模型水平偏移（画布单位）
        self.offset_y = 0.0       # 模型垂直偏移（画布单位）
        self.need_fit = True      # 初始化后自动适配窗口
        self.fit_count = 0        # 防止 fit 无限迭代的计数器
        # 拖拽相关
        self.dragging = False
        self.drag_offset = QPoint()
        self.is_in_la = False
        self.setMinimumSize(200, 250)
        self.resize(400, 500)
        # 情感表情动画状态
        self._emotion_motion_playing = False   # 情感动作播放中（播完由 timerEvent 检测）
        self._return_transition = None          # 回常态过渡 {from, to, t, duration}
        self._last_frame_time = time.perf_counter()
        # 鼠标跟随：平滑后的归一化坐标（[-1,1]，中心为 0）
        self._drag_x = 0.0
        self._drag_y = 0.0
        # 允许非按下状态也收到 mouseMoveEvent（跟随仍以每帧读取光标为准）
        self.setMouseTracking(True)
        # 跨线程信号→主线程槽：播放表情动作组（避免子线程操作 OpenGL）
        self.request_play_motion.connect(self._do_play_emotion_motion)

    # ---------- OpenGL 三钩子（Qt 自动按序调用） ----------
    def initializeGL(self) -> None:
        """只调用一次：初始化 GL 环境并加载模型"""
        live2d.glInit()
        self.model = live2d.LAppModel()
        self.model.LoadModelJson(MODEL_PATH)
        self.model.SetScale(self.scale_factor)
        self.model.SetOffset(self.offset_x, self.offset_y)
        try:
            self.model.SetAutoBreathEnable(True)
            self.model.SetAutoBlinkEnable(True)
        except Exception:
            pass
        # 以 fps = 120 的频率进行绘图（每帧触发 timerEvent → update() → paintGL）
        self.startTimer(int(1000 / 120))

    def resizeGL(self, w, h):
        """窗口大小变化时：更新画布，并保持缩放比例与居中偏移"""
        if self.model:
            self.model.Resize(w, h)
            self.model.SetScale(self.scale_factor)
            self.model.SetOffset(self.offset_x, self.offset_y)

    def paintGL(self):
        """每帧绘制：清屏 → 更新模型状态 → 写入回常态过渡参数 → 绘制模型"""
        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        live2d.clearBuffer()
        self.model.Update()
        # 关键：Update 之后、Draw 之前写入过渡参数，否则会被 Update 覆盖
        self._update_return_transition(dt)
        self.model.Draw()
        if self.need_fit:
            self.do_fit()

    # ---------- 形象自动适配窗口 ----------
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
        # glReadPixels 的 y 轴向上，需翻转成 Qt 的左上原点坐标
        y0, y1 = h - y1_gl, h - y0_gl
        return x0, y0, x1, y1

    def do_fit(self):
        """动态调整模型缩放与偏移：让形象完整居中显示在窗口内（占窗口约 88%）"""
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

    # ---------- 动画循环与鼠标检测 ----------
    def timerEvent(self, a0=None) -> None:
        """定时器回调（由 startTimer 驱动，实现动画循环）"""
        if not self.isVisible():
            return
        if not self.motion_started and self.model:
            # 启动时播放一次常态动作（组名必须与模型 motion 组一致）
            try:
                self.model.StartMotion("Idle", 0, live2d.MotionPriority.NORMAL)
            except Exception:
                pass
            self.motion_started = True
        # 情感动作播放结束后，启动平滑过渡回常态
        if (self._emotion_motion_playing and self.model
                and self.model.IsMotionFinished()):
            self._emotion_motion_playing = False
            self._start_return_to_neutral(NEUTRAL_RETURN_DURATION)
        self._update_cursor_drag()
        widget_pos = self.mapFromGlobal(QCursor.pos())
        self.is_in_la = self.is_in_l2d_area(int(widget_pos.x()), int(widget_pos.y()))
        self.update()

    def _update_cursor_drag(self) -> None:
        """每帧让头部/眼睛平滑朝向鼠标（在 Update 前调用）

        情绪动作与回归过渡期间暂停跟随，避免动作角度被 Drag 覆盖；
        过渡结束后从上次的平滑值继续收敛，不会跳变。
        """
        if self.model is None:
            return
        if self._emotion_motion_playing or self._return_transition is not None:
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        pos = self.mapFromGlobal(QCursor.pos())
        target_x, target_y = normalize_cursor(pos.x(), pos.y(), w, h)
        self._drag_x = smooth_toward(self._drag_x, target_x, CURSOR_SMOOTH_FACTOR)
        self._drag_y = smooth_toward(self._drag_y, target_y, CURSOR_SMOOTH_FACTOR)
        # model.Drag 接收与 Resize 一致的部件像素坐标
        px, py = denormalize_cursor(self._drag_x, self._drag_y, w, h)
        try:
            self.model.Drag(px, py)
        except Exception:
            pass

    # ---------- 情感表情动画驱动（主线程槽） ----------
    def _do_play_emotion_motion(self, group: str) -> None:
        """播放指定动作组；动作结束后由 timerEvent 检测并启动回常态过渡"""
        if self.model is None:
            return
        self._return_transition = None
        self._emotion_motion_playing = True
        try:
            self.model.SetAutoBlinkEnable(False)
            self.model.SetAutoBreathEnable(False)
        except Exception:
            pass
        try:
            self.model.StartMotion(group, 0, live2d.MotionPriority.FORCE)
        except Exception as e:
            logger.warning(f"[Live2DWidget]表情动作播放失败 {group}：{e}")
            self._emotion_motion_playing = False
            self._restore_auto_anim()

    def reset_emotion(self) -> None:
        """打断时立刻回到常态：停止当前动作、取消回常态过渡并恢复自动眨眼/呼吸"""
        self._return_transition = None
        self._emotion_motion_playing = False
        if self.model is not None:
            stop_all = getattr(self.model, "StopAllMotions", None)
            if stop_all is not None:
                try:
                    stop_all()
                except Exception:
                    pass
        self._restore_auto_anim()

    def _start_return_to_neutral(self, duration: float) -> None:
        """启动平滑过渡：所有参数从当前值回到 default（常态）"""
        if self.model is None:
            return
        ids = self.model.GetParamIds()
        frm, to = {}, {}
        for i, pid in enumerate(ids):
            try:
                p = self.model.GetParameter(i)
                frm[pid] = p.value
                to[pid] = p.default
            except Exception:
                continue
        self._return_transition = {
            "from": frm, "to": to, "t": 0.0, "duration": max(0.1, duration),
        }

    def _update_return_transition(self, dt: float) -> None:
        """推进回常态过渡：在 paintGL 的 Update 之后、Draw 之前写入插值参数"""
        tr = self._return_transition
        if tr is None or self.model is None:
            return
        tr["t"] += dt
        p = min(1.0, tr["t"] / tr["duration"])
        e = p * p * (3.0 - 2.0 * p)   # smoothstep 缓动
        for pid, frm in tr["from"].items():
            to = tr["to"].get(pid, frm)
            val = frm + (to - frm) * e
            try:
                self.model.SetParameterValue(pid, val, 1.0)
            except Exception:
                pass
        if p >= 1.0:
            self._return_transition = None
            self._restore_auto_anim()

    def _restore_auto_anim(self) -> None:
        """恢复自动眨眼/呼吸（常态待机需要）"""
        if self.model is None:
            return
        try:
            self.model.SetAutoBlinkEnable(True)
            self.model.SetAutoBreathEnable(True)
        except Exception:
            pass

    def is_in_l2d_area(self, click_x, click_y) -> bool:
        """判断点击位置是否落在 Live2D 模型的非透明像素上"""
        if click_x < 0 or click_y < 0 or click_x >= self.width() or click_y >= self.height():
            return False
        scale = self.devicePixelRatioF()
        h = self.height()
        try:
            alpha = gl.glReadPixels(
                int(click_x * scale), int((h - click_y) * scale), 1, 1,
                gl.GL_RGBA, gl.GL_UNSIGNED_BYTE,
            )[3]
            return alpha > 0
        except Exception:
            return False

    # ---------- 拖拽移动窗口 / 右键菜单 ----------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标按下：右键弹菜单；左键落在模型上时记录拖拽起点"""
        if event.button() == Qt.MouseButton.RightButton:
            win = self.window()
            if hasattr(win, 'show_context_menu'):
                win.show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.is_in_la:
            self.dragging = True
            self.drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动：拖拽状态下移动整个窗口"""
        if self.dragging:
            self.window().move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放：结束拖拽"""
        self.dragging = False

    # ---------- 滚轮缩放（窗口与形象同步等比缩放） ----------
    def wheelEvent(self, event) -> None:
        """滚轮：等比缩放窗口；模型由 resizeGL 的 Resize 跟随缩放"""
        delta = event.angleDelta().y()
        zoom = 1.1 if delta > 0 else 0.9
        win = self.window()
        new_w = int(win.width() * zoom)
        new_h = int(win.height() * zoom)
        if 300 <= new_w <= 1500 and 400 <= new_h <= 2000:
            win.resize(new_w, new_h)
            if hasattr(win, 'ensure_on_screen'):
                win.ensure_on_screen()
        event.accept()
