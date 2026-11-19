'''单轮对话聊天框：等待输入 / 思考中 / 回复 三态切换

状态机：
- input   ：左上角绘制“你：”装饰，可编辑，回车触发 submit 信号
- thinking：显示“哈达莉思考中......”，只读；Esc 触发 interrupt_requested
- reply   ：显示“哈达莉：回复内容”（QTimer 逐字打字机），只读，点击后恢复 input

P3 起本部件不再直接调用 agent / TTS，只负责显示与发信号；事件由
`ImageWindow` 根据后端 SSE 事件驱动。
'''
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFontMetrics, QKeyEvent, QMouseEvent, QPainter,
    QTextBlockFormat, QTextCursor,
)
from PySide6.QtWidgets import QTextEdit


class ChatBox(QTextEdit):
    """单轮对话聊天框：等待输入 / 思考中 / 回复 三态切换"""

    submit = Signal(str)              # 用户输入内容（已去除前后空白）
    interrupt_requested = Signal()    # 思考/回复期间按 Esc：请求打断本轮
    PREFIX = "你："                    # 输入态前缀（由 paintEvent 绘制，不属于文档）

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.state = 'input'        # input / thinking / reply 三态
        self.allow_reset = True     # 回复完成后才允许点击恢复输入
        self.prefix_visible = True  # 输入态绘制“你：”装饰
        # 回复逐字显示（打字机效果）
        self._typing_timer = QTimer(self)
        self._typing_timer.timeout.connect(self._typing_tick)
        self._typing_queue = ""
        self._typing_pos = 0
        self.TYPE_INTERVAL = 15
        self.TYPE_CHARS = 2
        self.to_input_state()

    # ---------- 状态切换 ----------
    def to_input_state(self):
        """等待用户输入：左上角绘制“你：”（装饰，不可删除），可编辑"""
        self._typing_timer.stop()
        self.state = 'input'
        self.allow_reset = True
        self.prefix_visible = True
        self.setPlainText("")
        cursor = self.textCursor()
        fm = QFontMetrics(self.document().defaultFont())
        fmt = QTextBlockFormat()
        fmt.setLeftMargin(fm.horizontalAdvance(self.PREFIX) + 4)
        cursor.mergeBlockFormat(fmt)
        self.setReadOnly(False)
        self.setFocus()

    def to_thinking_state(self):
        """AI 思考中：显示“哈达莉思考中......”，禁止输入"""
        self._typing_timer.stop()
        self.state = 'thinking'
        self.allow_reset = False
        self.prefix_visible = False
        self.setPlainText("哈达莉思考中......")
        self.setReadOnly(True)

    def finalize_ai_reply(self, full_text):
        """回复就绪：切换回复态，并用打字机效果逐字显示完整内容"""
        self.state = 'reply'
        self.prefix_visible = False
        self.setReadOnly(True)
        self.setPlainText("哈达莉：")
        self.allow_reset = False   # 打字未完成前不允许点击恢复输入
        self._typing_queue = full_text
        self._typing_pos = 0
        self._typing_timer.start(self.TYPE_INTERVAL)

    def show_error(self, message):
        """错误提示：直接显示完整错误信息（不走打字机），点击即可回到输入态"""
        self._typing_timer.stop()
        self.state = 'reply'
        self.prefix_visible = False
        self.allow_reset = True
        self.setReadOnly(True)
        self.setPlainText(f"哈达莉：（出错了）{message}")
        self.moveCursor(QTextCursor.MoveOperation.End)

    def _typing_tick(self):
        """打字机定时回调：每次追加 TYPE_CHARS 个字符，直到显示完整回复"""
        if self._typing_pos >= len(self._typing_queue):
            self._typing_timer.stop()
            self.allow_reset = True
            return
        self._typing_pos = min(self._typing_pos + self.TYPE_CHARS, len(self._typing_queue))
        self.setPlainText(f"哈达莉：{self._typing_queue[:self._typing_pos]}")
        self.moveCursor(QTextCursor.MoveOperation.End)
        vbar = self.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    # ---------- 事件 ----------
    def paintEvent(self, event):
        """在输入态左上角绘制“你：”前缀（不写入文档，无法被选中或删除）"""
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
        """回车 = 发送；思考/回复期间 Esc = 打断本轮"""
        if event.key() == Qt.Key.Key_Escape and self.state in ('thinking', 'reply'):
            self.interrupt_requested.emit()
            event.accept()
            return
        if self.state == 'input' and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            content = self.toPlainText().strip()
            if content:
                self.submit.emit(content)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """右键弹菜单；回复完成后左键点击恢复输入态"""
        if event.button() == Qt.MouseButton.RightButton:
            win = self.window()
            if hasattr(win, 'show_context_menu'):
                win.show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        if self.state in ('thinking', 'reply') and self.allow_reset:
            self.to_input_state()
            event.accept()
            return
        super().mousePressEvent(event)
