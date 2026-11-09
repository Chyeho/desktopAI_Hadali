'''桌宠主窗口：Live2D 形象 + 半透明聊天框 + 系统托盘

本模块是 client 侧的“事件翻译层”：把传输层收到的 SSE 事件映射为
聊天框状态、表情动作与语音播报，自身不包含任何对话逻辑。

线程模型：
- 传输线程只 emit Qt 信号；所有控件操作都在主线程执行
- live2d 只经 `Live2DWidget.request_play_motion` 信号进入主线程
'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from client.emotion_map import drive_expression
from client.ui.chat_box import ChatBox
from client.ui.live2d_widget import Live2DWidget
from client.voice import tts
from utils.logger_handler import logger


class ImageWindow(QWidget):
    """桌宠主窗口：无边框、透明背景、置顶、不占任务栏；聊天框浮动在形象中部偏下"""

    def __init__(self, transport, tts_module=None, parent=None):
        super().__init__(parent)
        self.transport = transport
        self.tts = tts_module or tts
        self._backend_ready = False
        self._turn_active = False     # 本轮是否仍在进行（turn.start ~ state=idle）
        self._error_shown = False     # 本轮是否已展示错误（错误轮不播报）

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.live2d_widget = Live2DWidget()
        layout.addWidget(self.live2d_widget)

        self.chat_box = ChatBox(self)
        self.chat_box.submit.connect(self.on_input_submitted)
        self.chat_box.interrupt_requested.connect(self.interrupt_turn)
        self.chat_box.raise_()

        self.setMinimumSize(300, 450)
        self.resize(420, 700)

        self.init_tray_icon()

        # 传输层信号 → 主线程处理（跨线程自动排队）
        self.transport.event_received.connect(self.on_transport_event)
        self.transport.failed.connect(self.on_transport_failed)

    # ---------- 布局 ----------
    def resizeEvent(self, event):
        """窗口大小改变时调整聊天框位置（等比缩放时相对位置不变）"""
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        bw, bh = int(w * 0.8), 150
        bx = (w - bw) // 2
        by = int(h * 0.52)
        if by + bh > h:
            by = max(10, h - bh - 10)
        self.chat_box.setGeometry(bx, by, bw, bh)

    # ---------- 后端状态 ----------
    def set_backend_ready(self, base_url: str) -> None:
        """后端就绪：允许发送对话"""
        self._backend_ready = True
        logger.info(f"[window]后端就绪：{base_url}")

    def show_backend_error(self, message: str) -> None:
        """后端不可用：聊天框给出明确提示，窗口保持可用（不崩、不黑屏）"""
        self._backend_ready = False
        self._turn_active = False
        self.chat_box.show_error(f"后端未就绪：{message}")

    # ---------- 用户交互 ----------
    def on_input_submitted(self, user_input: str) -> None:
        """用户提交一轮输入：进入思考态并交给传输层"""
        if self._turn_active:
            return
        if not self._backend_ready:
            self.show_backend_error("后端正在启动，请稍候再试")
            return
        self._turn_active = True
        self._error_shown = False
        self.chat_box.to_thinking_state()
        self.transport.send(user_input)

    def interrupt_turn(self) -> None:
        """打断本轮：通知后端、停语音、表情回常态、恢复到输入态"""
        if not self._turn_active:
            self.chat_box.to_input_state()
            return
        self.transport.interrupt()
        self._stop_speaking()
        self.live2d_widget.reset_emotion()
        self._turn_active = False
        self.chat_box.to_input_state()

    def _stop_speaking(self) -> None:
        """停止语音播报（TTS 失败不影响 UI）"""
        try:
            self.tts.stop()
        except Exception as exc:
            logger.warning(f"[window]停止语音失败：{exc}")

    # ---------- 后端事件 ----------
    def on_transport_event(self, name: str, payload: dict) -> None:
        """SSE 事件 → UI 动作（顺序与协议 v1 一致，见执行文档 6.3）"""
        if name == "turn.start":
            self._turn_active = True
            self._error_shown = False
            self.chat_box.to_thinking_state()
        elif name == "state":
            self._on_state(str(payload.get("value", "")))
        elif name == "text.delta":
            text = payload.get("text", "")
            if text:
                self.chat_box.finalize_ai_reply(text)
        elif name == "text.done":
            # 本期 text.delta 已整段下发；未来流式时在此收尾
            pass
        elif name == "emotion":
            drive_expression(payload.get("name", ""), live2d_widget=self.live2d_widget)
        elif name == "turn.end":
            self._on_turn_end(payload)
        elif name == "error":
            self._on_error(payload)
        elif name.startswith("audio."):
            logger.debug(f"[window]忽略音频事件：{name}")
        elif name in ("tool.call", "tool.result"):
            logger.debug(f"[window]{name} {payload}")
        else:
            logger.debug(f"[window]忽略未知事件：{name}")

    def _on_state(self, value: str) -> None:
        """state 事件：thinking 保持思考态；idle 收敛本轮"""
        if value == "thinking":
            self.chat_box.to_thinking_state()
        elif value == "idle":
            self._turn_active = False
            # 既没有 text.delta 也没有 error（异常路径）：直接恢复输入，避免卡在思考态
            if self.chat_box.state == 'thinking':
                self.chat_box.to_input_state()

    def _on_turn_end(self, payload: dict) -> None:
        """本轮完成：播报回复（错误轮不播报）"""
        reply = payload.get("reply", "")
        if not reply or self._error_shown:
            return
        try:
            self.tts.speak(reply)
        except Exception as exc:
            logger.warning(f"[window]语音播报失败：{exc}")

    def _on_error(self, payload: dict) -> None:
        """错误事件：显示错误信息，不播报，不阻塞后续输入"""
        self._error_shown = True
        message = payload.get("message") or payload.get("code") or "未知错误"
        self.chat_box.show_error(str(message))

    def on_transport_failed(self, message: str) -> None:
        """传输层失败（后端被杀 / 断连 / 鉴权失败）：恢复输入态并提示"""
        self._turn_active = False
        self.chat_box.show_error(message)

    # ---------- 托盘与菜单 ----------
    def init_tray_icon(self):
        """初始化系统托盘图标和菜单"""
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
        """退出应用程序：先释放语音与连接，再结束进程"""
        self._stop_speaking()
        try:
            self.transport.close()
        except Exception as exc:
            logger.warning(f"[window]关闭传输层失败：{exc}")
        self.tray_icon.hide()
        QApplication.quit()

    def show_context_menu(self, global_pos):
        """右键菜单：停止回复（进行中）/ 最小化 / 关闭"""
        menu = QMenu(self)
        if self._turn_active:
            stop_action = menu.addAction("停止当前回复")
            stop_action.triggered.connect(self.interrupt_turn)
        minimize_action = menu.addAction("最小化")
        quit_action = menu.addAction("关闭AI助手")
        minimize_action.triggered.connect(self.hide_to_tray)
        quit_action.triggered.connect(self.quit_app)
        menu.exec(global_pos)

    def hide_to_tray(self):
        """最小化到系统托盘（不关闭程序，可从托盘恢复）"""
        self.hide()
        self.tray_icon.setToolTip("Live2D 桌宠已最小化到托盘")

    def ensure_on_screen(self):
        """确保窗口保持在屏幕可见范围内（缩放后防止移出屏幕）"""
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
