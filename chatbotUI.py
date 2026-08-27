"""
Live2D 桌宠 AI 聊天界面

桌面 UI ： Live2D 形象（固定神态动作）。
聊天交互为单轮对话框模式：你：输入 → 哈达莉思考中...... → 哈达莉：流式回复 → 点击恢复输入。

四大组件：
- AIWorker      ：后台线程，调用大模型接口（避免阻塞 UI），支持流式回传
- ChatBox       ：单轮对话聊天框，三态状态机（input / thinking / reply）
- Live2DWidget  ：OpenGL 渲染 Live2D 形象，自动适配窗口居中，支持拖拽/缩放/右键
- ImageWindow   ：无边框透明主窗口，组装形象与聊天框，提供系统托盘与右键菜单
"""
import os

import numpy as np            # 数值计算：把 glReadPixels 读回的字节流转成数组分析像素
import OpenGL.GL as gl        # OpenGL 底层 API：读像素（包围盒检测、拖拽判定）
import live2d.v3 as live2d    # live2d-py 第三方封装（v3 版 Cubism SDK）
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
import chatbotTTS

# Live2D 模型路径（相对本文件所在目录，保证任意工作目录启动都能找到）
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Resources", "v3", "hiyori", "hiyori_free_t08.model3.json",
)


class AIWorker(QThread):
    """处理大模型请求的工作线程（支持流式回传）

    为什么需要线程？
    - AI 网络请求是阻塞操作，若放在主线程（UI 线程），界面会卡死无法响应
    - 继承 QThread 后，run() 在独立线程执行，完成后通过信号把结果发回主线程
    """

    chunk_received = Signal(str)   # 自定义信号：流式生成的一块内容
    response_ready = Signal(str)   # 自定义信号：完整回复（结束）

    def __init__(self, user_input):
        super().__init__()
        self.user_input = user_input
        self.full_reply = ""       # 累积本次对话的完整回复

    def run(self):
        """QThread 启动后自动执行的方法（子线程环境）"""
        def on_chunk(content):
            """流式回调：每生成一块内容就累加并通过信号发射给主线程"""
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
    """单轮对话聊天框：等待输入 / 思考中 / 回复 三态切换

    状态机：
    - input   ：左上角绘制"你："装饰，可编辑，回车触发 submit 信号
    - thinking：显示"哈达莉思考中......"，只读
    - reply   ：显示"哈达莉：回复内容"（流式追加），只读，点击后恢复 input
    """

    submit = Signal(str)  # 自定义信号：用户输入内容（已去除前后空白）
    PREFIX = "你："        # 输入态前缀（由 paintEvent 绘制，不属于文档，不可编辑删除）

    def __init__(self, parent=None):
        super().__init__(parent)
        # 半透明样式（由 ImageWindow 浮动定位，盖在形象裙摆附近）
        self.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.85);   /* 半透明白色底，隐约透出形象与桌面 */
                border: 1px solid rgba(255, 255, 255, 0.9);
                border-radius: 10px;                     /* 圆角 */
                padding: 8px;
                font-family: "Microsoft YaHei", SimSun;
                font-size: 14px;
                color: #333;
            }
        """)
        self.state = 'input'        # input / thinking / reply 三态
        self.allow_reset = True     # 回复完成后才允许点击恢复输入（防止思考中误触）
        self.prefix_visible = True  # 输入态绘制"你："装饰（AI 回复时隐藏）
        self.to_input_state()

    # ---------- 状态切换 ----------
    def to_input_state(self):
        """等待用户输入：左上角绘制"你："（装饰，不可删除），可编辑"""
        self.state = 'input'
        self.allow_reset = True
        self.prefix_visible = True
        self.setPlainText("")  # 内容区仅存放用户输入，"你："由 paintEvent 绘制
        # 首行缩进，为"你："预留空间（缩进宽度 = 前缀宽度 + 4px 间距）
        cursor = self.textCursor()
        fm = QFontMetrics(self.document().defaultFont())
        fmt = QTextBlockFormat()
        fmt.setLeftMargin(fm.horizontalAdvance(self.PREFIX) + 4)
        cursor.mergeBlockFormat(fmt)
        self.setReadOnly(False)
        self.setFocus()  # 获取焦点，光标直接进入输入态

    def to_thinking_state(self):
        """AI 思考中：显示"哈达莉思考中......"，禁止输入"""
        self.state = 'thinking'
        self.allow_reset = False
        self.prefix_visible = False
        self.setPlainText("哈达莉思考中......")
        self.setReadOnly(True)

    def append_ai_chunk(self, content):
        """追加流式回复内容（首次调用时自动切换为回复状态）"""
        if self.state != 'reply':
            self.state = 'reply'
            self.prefix_visible = False
            self.setPlainText("哈达莉：")
        # 把光标移到末尾再插入，实现"逐字追加"效果
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(content)
        # 滚动到底部，保证最新内容可见
        vbar = self.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def finalize_ai_reply(self, full_text):
        """回复完成：确保显示完整内容，并允许点击恢复输入"""
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
        painter = QPainter(self.viewport())  # 在文本视口上创建画笔
        font = self.document().defaultFont()  # 与文档文字使用同一字体，保证对齐
        painter.setFont(font)
        fm = QFontMetrics(font)
        margin = self.document().documentMargin()
        painter.setPen(QColor(70, 70, 70))
        # drawText 的 y 参数是文字基线，用 ascent 计算出第一行文字的基线位置
        painter.drawText(int(margin), int(margin + fm.ascent()), self.PREFIX)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """拦截回车：输入态下回车 = 发送，其余按键交给默认处理"""
        if self.state == 'input' and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            content = self.toPlainText().strip()
            if content:
                self.submit.emit(content)  # 通过信号把内容交给外部（ImageWindow）
            event.accept()  # 标记已处理，阻止 QTextEdit 默认的换行行为
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标事件：右键弹菜单；回复完成后左键点击恢复输入态"""
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
    """渲染 Live2D 模型的部件（固定神态动作，形象自动适配窗口并居中，随窗口等比缩放）

    核心功能：
    - 自动适配：初始化后读取帧像素，动态调整缩放/偏移，让形象完整居中显示
    - 等比缩放：滚轮只缩放窗口，模型由 resizeGL 跟随，形象始终占窗口固定比例不越界
    - 像素级交互：通过 glReadPixels 判断鼠标是否落在模型上（拖拽/点击）
    """

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
        self.fit_count = 0        # 防止 fit 无限迭代的计数器
        # 拖拽相关
        self.dragging = False
        self.drag_offset = QPoint()
        self.is_in_la = False
        self.setMinimumSize(200, 250)
        self.resize(400, 500)

    # ---------- OpenGL 三钩子（Qt 自动按序调用） ----------
    def initializeGL(self) -> None:
        """只调用一次：初始化 GL 环境并加载模型"""
        # 将当前窗口作为 OpenGL 的上下文，图形绘制到当前窗口
        live2d.glInit()
        # 创建并加载模型（解析 model3.json → moc/贴图/动作/物理）
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
        # 以 fps = 120 的频率进行绘图（每帧触发 timerEvent → update() → paintGL）
        self.startTimer(int(1000 / 120))

    def resizeGL(self, w, h):
        """窗口大小变化时：更新画布，并保持缩放比例与居中偏移"""
        if self.model:
            self.model.Resize(w, h)   # 重设画布尺寸为窗口大小（模型随之等比缩放）
            self.model.SetScale(self.scale_factor)
            self.model.SetOffset(self.offset_x, self.offset_y)

    def paintGL(self):
        """每帧绘制：清屏 → 更新模型状态 → 绘制模型"""
        live2d.clearBuffer()   # 清空颜色缓冲（保持透明背景）
        self.model.Update()    # 更新模型状态（呼吸、眨眼、动作动画进度）
        self.model.Draw()      # 绘制模型到当前帧缓冲
        if self.need_fit:
            self.do_fit()      # 初始适配窗口（读像素 → 调缩放/偏移）

    # ---------- 形象自动适配窗口 ----------
    def compute_model_bbox(self):
        """读取当前帧，返回模型非透明像素在窗口坐标下的包围盒 (x0, y0, x1, y1)"""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0 or self.model is None:
            return None
        ds = self.devicePixelRatioF()  # 高 DPI 缩放系数，读像素要按实际分辨率
        rw, rh = max(1, int(w * ds)), max(1, int(h * ds))
        try:
            # 把 GPU 画好的整帧读回内存（RGBA 字节流）
            data = gl.glReadPixels(0, 0, rw, rh, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
        except Exception:
            return None
        arr = np.frombuffer(data, dtype=np.uint8).reshape(rh, rw, 4)
        alpha = arr[:, :, 3]                     # 只取 alpha 通道
        ys, xs = np.nonzero(alpha > 0)           # 找到所有不透明像素的坐标
        if len(xs) == 0:
            return None
        x0, x1 = xs.min() / ds, xs.max() / ds
        y0_gl, y1_gl = ys.min() / ds, ys.max() / ds
        # glReadPixels 的 y 轴向上，需翻转成 Qt 的左上原点坐标
        y0, y1 = h - y1_gl, h - y0_gl
        return x0, y0, x1, y1

    def do_fit(self):
        """动态调整模型缩放与偏移：让形象完整居中显示在窗口内（占窗口约 88%）

        采用"测量 → 调整 → 重绘再测量"的迭代逼近方式，直到收敛。
        """
        self.fit_count += 1
        if self.fit_count > 8:   # 迭代上限，防止死循环
            self.need_fit = False
            return
        bbox = self.compute_model_bbox()
        if bbox is None:
            self.need_fit = False
            return
        x0, y0, x1, y1 = bbox
        mw, mh = x1 - x0, y1 - y0     # 模型当前像素宽高
        if mw <= 1 or mh <= 1:
            self.need_fit = False
            return
        # 目标尺寸：占窗口宽高 88%（取宽高两个方向中更小的缩放比，保证完整显示）
        s = min((self.width() * 0.88) / mw, (self.height() * 0.88) / mh)
        s = max(0.05, min(s, 20.0))   # 限制缩放范围
        # 画布单位 → 窗口像素换算（offset 参数单位是画布单位）
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
            self.update()  # 触发重绘，下一帧再次测量验证

    # ---------- 动画循环与鼠标检测 ----------
    def timerEvent(self, a0: QTimerEvent | None) -> None:
        """定时器回调（由 startTimer 驱动，实现动画循环）"""
        if not self.isVisible():
            return
        if not self.motion_started and self.model:
            # 播放一次固定动作，不随机切换表情（保持固定神态）
            try:
                self.model.StartMotion("TapBody", 0, live2d.MotionPriority.FORCE)
            except Exception:
                pass
            self.motion_started = True
        # 每帧更新"鼠标是否位于模型区域内"（供拖拽判断），避免在 mousePress 时读像素
        widget_pos = self.mapFromGlobal(QCursor.pos())
        self.is_in_la = self.is_in_l2d_area(int(widget_pos.x()), int(widget_pos.y()))
        self.update()  # 请求重绘（触发 paintGL）

    def is_in_l2d_area(self, click_x, click_y) -> bool:
        """判断点击位置是否落在 Live2D 模型的非透明像素上"""
        if click_x < 0 or click_y < 0 or click_x >= self.width() or click_y >= self.height():
            return False
        scale = self.devicePixelRatioF()
        h = self.height()
        try:
            # 只读取 1 个像素的 alpha 通道：>0 说明该点被模型覆盖
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
        # 右键弹出功能菜单（关闭 / 最小化）
        if event.button() == Qt.MouseButton.RightButton:
            win = self.window()
            if hasattr(win, 'show_context_menu'):
                win.show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        # 只有点到模型实体（非透明像素）才允许拖动窗口
        if event.button() == Qt.MouseButton.LeftButton and self.is_in_la:
            self.dragging = True
            # 记录鼠标与窗口左上角的偏移（用全局坐标，因为窗口会移动）
            self.drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动：拖拽状态下移动整个窗口"""
        if self.dragging:
            self.window().move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放：结束拖拽"""
        self.dragging = False

    # ---------- 滚轮缩放（窗口与形象同步等比缩放，形象始终不超出窗口） ----------
    def wheelEvent(self, event) -> None:
        """滚轮：等比缩放窗口；模型由 resizeGL 的 Resize 跟随缩放"""
        delta = event.angleDelta().y()  # 正 = 向上滚（放大），负 = 向下滚（缩小）
        zoom = 1.1 if delta > 0 else 0.9
        # 等比缩放窗口；模型由 resizeGL 的 Resize 跟随缩放，保持适配比例不变
        win = self.window()
        new_w = int(win.width() * zoom)
        new_h = int(win.height() * zoom)
        if 300 <= new_w <= 1500 and 400 <= new_h <= 2000:  # 限制缩放范围
            win.resize(new_w, new_h)
            if hasattr(win, 'ensure_on_screen'):
                win.ensure_on_screen()
        event.accept()


class ImageWindow(QWidget):
    """桌宠主窗口：Live2D 形象 + 半透明聊天框 + 系统托盘

    特点：无边框、透明背景、置顶、不占任务栏；聊天框浮动盖在形象中部偏下。
    """

    def __init__(self):
        super().__init__()
        # 设置窗口无边框、置顶、不显示在任务栏（桌宠悬浮效果的三大要素）
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        # 启用透明背景（配合 OpenGL 部件的 alpha 通道实现圆角/镂空桌宠）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Live2D 形象部件：占满整个窗口
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.live2d_widget = Live2DWidget()
        layout.addWidget(self.live2d_widget)

        # 半透明聊天框：浮动覆盖在形象裙摆附近（位置由 resizeEvent 控制）
        self.chat_box = ChatBox(self)   # 不加入布局，手动 setGeometry 定位
        self.chat_box.submit.connect(self.on_input_submitted)
        self.chat_box.raise_()          # 提到最上层，盖在 OpenGL 部件之上

        # 窗口初始大小
        self.setMinimumSize(300, 450)
        self.resize(420, 700)

        # 托盘图标
        self.init_tray_icon()

        # AI 工作线程（同一时间只允许一个在运行）
        self.ai_worker = None

    def resizeEvent(self, event):
        """窗口大小改变时调整聊天框位置（等比缩放时聊天框相对位置不变）"""
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        # 聊天框覆盖在形象中间偏下（裙摆附近）：水平居中、宽 80%、高 150px
        bw, bh = int(w * 0.8), 150
        bx = (w - bw) // 2
        by = int(h * 0.52)
        if by + bh > h:  # 窗口太矮时贴底
            by = max(10, h - bh - 10)
        self.chat_box.setGeometry(bx, by, bw, bh)

    def init_tray_icon(self):
        """初始化系统托盘图标和菜单（最小化到托盘后可从这里恢复/退出）"""
        # 自绘一个红色圆作为托盘图标（避免依赖外部图标文件）
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
        """退出应用程序（彻底结束进程）"""
        self.tray_icon.hide()
        QApplication.quit()

    def show_context_menu(self, global_pos):
        """鼠标右键弹出的功能菜单：最小化到托盘 / 关闭AI助手"""
        menu = QMenu(self)
        minimize_action = menu.addAction("最小化")
        quit_action = menu.addAction("关闭AI助手")
        minimize_action.triggered.connect(self.hide_to_tray)
        quit_action.triggered.connect(self.quit_app)
        menu.exec(global_pos)  # exec 为阻塞式：在鼠标位置弹出菜单

    def hide_to_tray(self):
        """最小化到系统托盘（不关闭程序，可从托盘恢复）"""
        self.hide()
        self.tray_icon.setToolTip("Live2D 桌宠已最小化到托盘")

    def on_input_submitted(self, user_input):
        """处理用户输入提交事件：启动 AI 工作线程"""
        # 上一轮 AI 还在回复时禁止新一轮输入
        if self.ai_worker and self.ai_worker.isRunning():
            return
        # 切换为思考中状态，禁止输入
        self.chat_box.to_thinking_state()
        # 创建并启动 AI 工作线程（连接两个信号：流式块 / 完成）
        self.ai_worker = AIWorker(user_input)
        self.ai_worker.chunk_received.connect(self.on_ai_chunk)
        self.ai_worker.response_ready.connect(self.on_ai_response)
        self.ai_worker.start()

    def on_ai_chunk(self, content):
        """处理 AI 流式回复块：实时显示到聊天框"""
        self.chat_box.append_ai_chunk(content)

    def on_ai_response(self, response):
        """处理 AI 完整回复事件：显示最终内容并同步语音播报"""
        self.chat_box.finalize_ai_reply(response)
        # 同步播报回复内容（非阻塞，TTS 在后台线程执行；错误信息不播报）
        if not response.startswith("错误"):
            chatbotTTS.speak(response)

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
        event.ignore()  # 忽略关闭事件
        self.hide()     # 隐藏窗口
        self.tray_icon.setToolTip("Live2D 桌宠已最小化到托盘")
