"""
Live2D 桌宠 AI 聊天界面
基于 SSS_AI 的桌面 UI 修改：将静态图片桌宠替换为 Live2D 形象（固定神态动作）
聊天交互为单轮对话框模式：你：输入 → 哈达莉思考中...... → 哈达莉：流式回复 → 点击恢复输入
"""
import os

import numpy as np
import OpenGL.GL as gl
import live2d.v3 as live2d
from PySide6.QtCore import QPoint, Qt, QThread, QTimerEvent, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFontMetrics, QIcon, QKeyEvent, QMouseEvent,
    QPainter, QPixmap, QTextBlockFormat, QTextCursor,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QApplication, QMenu, QSystemTrayIcon, QTextEdit,
    QVBoxLayout, QWidget,
)

import chatbot

# Live2D 模型路径（相对本文件所在目录）
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Resources", "v3", "hiyori", "hiyori_free_t08.model3.json",
)


class AIWorker(QThread):
    """处理大模型请求的工作线程（支持流式回传）"""

    chunk_received = Signal(str)   # 流式生成的一块内容
    response_ready = Signal(str)   # 完整回复（结束）

    def __init__(self, user_input):
        super().__init__()
        self.user_input = user_input
        self.full_reply = ""

    def run(self):
        """在单独线程中调用大模型API，逐块回传生成内容"""
        def on_chunk(content):
            self.full_reply += content
            self.chunk_received.emit(content)

        try:
            chatbot.chat_with_model(self.user_input, on_chunk=on_chunk)
            self.response_ready.emit(self.full_reply)
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 流式调用中途出错时，chatbot 模块可能已收集部分回复，优先返回已生成内容
            partial = getattr(chatbot, 'last_partial_reply', '')
            if partial:
                self.response_ready.emit(partial)
            else:
                self.response_ready.emit(f"错误: {str(e)}")


class ChatBox(QTextEdit):
    """单轮对话聊天框：等待输入 / 思考中 / 回复 三态切换"""

    submit = Signal(str)  # 用户输入内容
    PREFIX = "你："        # 输入态前缀（由 paintEvent 绘制，不可编辑删除）

    def __init__(self, parent=None):
        super().__init__(parent)
        # 半透明样式（由 ImageWindow 浮动定位，盖在形象裙摆附近）
        self.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.9);
                border-radius: 10px;
                padding: 8px;
                font-family: "Microsoft YaHei", SimSun;
                font-size: 14px;
                color: #333;
            }
        """)
        self.state = 'input'        # input / thinking / reply
        self.allow_reset = True     # 回复完成后才允许点击恢复输入
        self.prefix_visible = True  # 输入态绘制"你："装饰
        self.to_input_state()

    # ---------- 状态切换 ----------
    def to_input_state(self):
        """等待用户输入：左上角绘制"你："（装饰，不可删除），可编辑"""
        self.state = 'input'
        self.allow_reset = True
        self.prefix_visible = True
        self.setPlainText("")  # 内容区仅存放用户输入，"你："由 paintEvent 绘制
        # 首行缩进，为"你："预留空间
        cursor = self.textCursor()
        fm = QFontMetrics(self.document().defaultFont())
        fmt = QTextBlockFormat()
        fmt.setLeftMargin(fm.horizontalAdvance(self.PREFIX) + 4)
        cursor.mergeBlockFormat(fmt)
        self.setReadOnly(False)
        self.setFocus()

    def to_thinking_state(self):
        """AI 思考中：显示"哈达莉思考中......"，禁止输入"""
        self.state = 'thinking'
        self.allow_reset = False
        self.prefix_visible = False
        self.setPlainText("哈达莉思考中......")
        self.setReadOnly(True)

    def append_ai_chunk(self, content):
        """追加流式回复内容（首次调用时切换为回复状态）"""
        if self.state != 'reply':
            self.state = 'reply'
            self.prefix_visible = False
            self.setPlainText("哈达莉：")
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(content)
        # 滚动到底部
        vbar = self.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def finalize_ai_reply(self, full_text):
        """回复完成：确保显示完整内容，允许点击恢复输入"""
        self.state = 'reply'
        self.prefix_visible = False
        self.setPlainText(f"哈达莉：{full_text}")
        self.setReadOnly(True)
        self.allow_reset = True

    # ---------- 事件 ----------
    def paintEvent(self, event):
        """在输入态左上角绘制"你："前缀（不写入文档，无法被选中或删除）"""
        super().paintEvent(event)
        if not self.prefix_visible:
            return
        painter = QPainter(self.viewport())
        font = self.document().defaultFont()
        painter.setFont(font)
        fm = QFontMetrics(font)
        margin = self.document().documentMargin()
        painter.setPen(QColor(70, 70, 70))
        painter.drawText(int(margin), int(margin + fm.ascent()), self.PREFIX)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.state == 'input' and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            content = self.toPlainText().strip()
            if content:
                self.submit.emit(content)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # 右键弹出功能菜单（关闭 / 最小化）
        if event.button() == Qt.MouseButton.RightButton:
            win = self.window()
            if hasattr(win, 'show_context_menu'):
                win.show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        # 回复完成后点击聊天框，恢复等待输入状态
        if self.state in ('thinking', 'reply') and self.allow_reset:
            self.to_input_state()
            event.accept()
            return
        super().mousePressEvent(event)


class Live2DWidget(QOpenGLWidget):
    """渲染 Live2D 模型的部件（固定神态动作，形象自动适配窗口并居中，随窗口等比缩放）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 透明背景，便于叠加在无边框透明窗口上
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.model = None
        self.motion_started = False
        self.scale_factor = 1.0   # 模型缩放倍数（由 do_fit 动态计算）
        self.offset_x = 0.0       # 模型水平偏移（画布单位）
        self.offset_y = 0.0       # 模型垂直偏移（画布单位）
        self.need_fit = True      # 初始化后自动适配窗口
        self.fit_count = 0
        # 拖拽相关
        self.dragging = False
        self.drag_offset = QPoint()
        self.is_in_la = False
        self.setMinimumSize(200, 250)
        self.resize(400, 500)

    def initializeGL(self) -> None:
        # 将当前窗口作为 OpenGL 的上下文，图形绘制到当前窗口
        live2d.glInit()
        # 创建并加载模型
        self.model = live2d.LAppModel()
        self.model.LoadModelJson(MODEL_PATH)
        self.model.SetScale(self.scale_factor)
        self.model.SetOffset(self.offset_x, self.offset_y)
        # 保持固定神态：开启自动呼吸与眨眼
        try:
            self.model.SetAutoBreathEnable(True)
            self.model.SetAutoBlinkEnable(True)
        except Exception:
            pass
        # 以 fps = 120 的频率进行绘图
        self.startTimer(int(1000 / 120))

    def resizeGL(self, w, h):
        # 使模型的参数按窗口大小进行更新，并保持缩放比例与居中偏移
        if self.model:
            self.model.Resize(w, h)
            self.model.SetScale(self.scale_factor)
            self.model.SetOffset(self.offset_x, self.offset_y)

    def paintGL(self):
        live2d.clearBuffer()
        self.model.Update()
        self.model.Draw()
        if self.need_fit:
            self.do_fit()

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
        # glReadPixels 的 y 轴向上，翻转成 Qt 的左上原点坐标
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
        # 目标尺寸：占窗口宽高 88%
        s = min((self.width() * 0.88) / mw, (self.height() * 0.88) / mh)
        s = max(0.05, min(s, 20.0))
        # 画布单位 → 窗口像素换算
        canvas_w = self.model.GetCanvasSize()[0] or 1.0
        px_per_unit = (self.width() / canvas_w) * self.scale_factor
        # 调整缩放
        if abs(s - 1.0) > 0.005:
            self.scale_factor *= s
            px_per_unit *= s
            self.model.SetScale(self.scale_factor)
        # 调整位置使模型中心与窗口中心重合
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx = (self.width() / 2 - cx) / px_per_unit
        dy = (self.height() / 2 - cy) / px_per_unit
        self.offset_x += dx
        self.offset_y += dy
        self.model.SetOffset(self.offset_x, self.offset_y)
        # 收敛判断：缩放与偏移变化足够小时停止迭代
        if abs(s - 1.0) < 0.02 and abs(dx) * px_per_unit < 2 and abs(dy) * px_per_unit < 2:
            self.need_fit = False
        else:
            self.update()

    def timerEvent(self, a0: QTimerEvent | None) -> None:
        if not self.isVisible():
            return
        if not self.motion_started and self.model:
            # 播放一次固定动作，不随机切换表情
            try:
                self.model.StartMotion("TapBody", 0, live2d.MotionPriority.FORCE)
            except Exception:
                pass
            self.motion_started = True
        # 更新鼠标是否位于模型区域内（供拖拽判断）
        widget_pos = self.mapFromGlobal(QCursor.pos())
        self.is_in_la = self.is_in_l2d_area(int(widget_pos.x()), int(widget_pos.y()))
        self.update()

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
        # 右键弹出功能菜单（关闭 / 最小化）
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
        if self.dragging:
            self.window().move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self.dragging = False

    # ---------- 滚轮缩放（窗口与形象同步等比缩放，形象始终不超出窗口） ----------
    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        zoom = 1.1 if delta > 0 else 0.9
        # 等比缩放窗口；模型由 resizeGL 的 Resize 跟随缩放，保持适配比例不变
        win = self.window()
        new_w = int(win.width() * zoom)
        new_h = int(win.height() * zoom)
        if 300 <= new_w <= 1500 and 400 <= new_h <= 2000:
            win.resize(new_w, new_h)
            if hasattr(win, 'ensure_on_screen'):
                win.ensure_on_screen()
        event.accept()


class ImageWindow(QWidget):
    """桌宠主窗口：Live2D 形象 + 半透明聊天框 + 系统托盘"""

    def __init__(self):
        super().__init__()
        # 设置窗口无边框、置顶、不显示在任务栏
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        # 启用透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Live2D 形象部件：占满整个窗口
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.live2d_widget = Live2DWidget()
        layout.addWidget(self.live2d_widget)

        # 半透明聊天框：浮动覆盖在形象裙摆附近（位置由 resizeEvent 控制）
        self.chat_box = ChatBox(self)
        self.chat_box.submit.connect(self.on_input_submitted)
        self.chat_box.raise_()

        # 窗口初始大小
        self.setMinimumSize(300, 450)
        self.resize(420, 700)

        # 托盘图标
        self.init_tray_icon()

        # AI 工作线程
        self.ai_worker = None

    def resizeEvent(self, event):
        """窗口大小改变时调整关闭按钮与聊天框位置"""
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        # 聊天框覆盖在形象中间偏下（裙摆附近）：水平居中、宽 80%、高 150px
        bw, bh = int(w * 0.8), 150
        bx = (w - bw) // 2
        by = int(h * 0.52)
        if by + bh > h:
            by = max(10, h - bh - 10)
        self.chat_box.setGeometry(bx, by, bw, bh)

    def init_tray_icon(self):
        """初始化系统托盘图标和菜单"""
        # 自绘一个红色圆作为托盘图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(230, 76, 60)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(pixmap))

        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示窗口")
        quit_action = tray_menu.addAction("退出")
        show_action.triggered.connect(self.show)
        quit_action.triggered.connect(self.quit_app)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def tray_icon_activated(self, reason):
        """双击托盘图标恢复窗口"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()

    def quit_app(self):
        """退出应用程序"""
        self.tray_icon.hide()
        QApplication.quit()

    def show_context_menu(self, global_pos):
        """鼠标右键弹出的功能菜单：最小化到托盘 / 关闭AI助手"""
        menu = QMenu(self)
        minimize_action = menu.addAction("最小化")
        quit_action = menu.addAction("关闭AI助手")
        minimize_action.triggered.connect(self.hide_to_tray)
        quit_action.triggered.connect(self.quit_app)
        menu.exec(global_pos)

    def hide_to_tray(self):
        """最小化到系统托盘（不关闭程序，可从托盘恢复）"""
        self.hide()
        self.tray_icon.setToolTip("Live2D 桌宠已最小化到托盘")

    def on_input_submitted(self, user_input):
        """处理用户输入提交事件"""
        # 上一轮 AI 还在回复时禁止新一轮输入
        if self.ai_worker and self.ai_worker.isRunning():
            return
        # 切换为思考中状态，禁止输入
        self.chat_box.to_thinking_state()
        # 创建 AI 工作线程
        self.ai_worker = AIWorker(user_input)
        self.ai_worker.chunk_received.connect(self.on_ai_chunk)
        self.ai_worker.response_ready.connect(self.on_ai_response)
        self.ai_worker.start()

    def on_ai_chunk(self, content):
        """处理 AI 流式回复块"""
        self.chat_box.append_ai_chunk(content)

    def on_ai_response(self, response):
        """处理 AI 完整回复事件"""
        self.chat_box.finalize_ai_reply(response)

    def ensure_on_screen(self):
        """确保窗口保持在屏幕可见范围内"""
        screen_geometry = self.screen().availableGeometry()
        window_geometry = self.geometry()
        if window_geometry.right() > screen_geometry.right():
            self.move(screen_geometry.right() - window_geometry.width(), self.y())
        if window_geometry.bottom() > screen_geometry.bottom():
            self.move(self.x(), screen_geometry.bottom() - window_geometry.height())
        if window_geometry.left() < screen_geometry.left():
            self.move(screen_geometry.left(), self.y())
        if window_geometry.top() < screen_geometry.top():
            self.move(self.x(), screen_geometry.top())

    def closeEvent(self, event):
        """窗口关闭时隐藏到托盘而不是真正退出"""
        event.ignore()
        self.hide()
        self.tray_icon.setToolTip("Live2D 桌宠已最小化到托盘")
