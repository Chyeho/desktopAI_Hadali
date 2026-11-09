"""
聊天机器人语音合成模块（TTS，client 表现层）

P3 由根目录 chatbotTTS.py 迁移而来，逻辑未改；`.env` 改为按项目根定位
（`utils.path_tool.get_abs_path`），避免文件移动后读不到配置。

职责：
- 为桌宠提供语音播报能力：AI 回复完成后同步朗读回复内容
- 服务架构（通过 .env 的 TTS_MODE 切换）：
  - 演示模式 demo（默认）：优先 qwen3-tts（阿里云百炼，多语言混说/自定义音色），失败时 edge-tts 兜底
  - 开发模式 dev ：仅使用 edge-tts（免费、零配置、无网络 Key 依赖）
- 合成与播放均在独立后台线程中执行，不阻塞桌宠 UI

配置项（.env）：
- TTS_MODE                           demo / dev（默认 demo）
- EDGE_TTS_VOICE                     兜底服务 edge-tts 音色（中文女声，安静温柔型）
- DASHSCOPE_API_KEY                  阿里云百炼 API Key（qwen3-tts 必需）
- DASHSCOPE_MODEL                    qwen3-tts 模型（默认 qwen3-tts-vd-2026-01-26）
- DASHSCOPE_VOICE                    qwen3-tts 音色（内置音色或百炼声音设计音色 ID）
"""
import asyncio
import base64
import io
import itertools
import queue
import re
import threading
import traceback

import numpy as np

from utils.path_tool import get_abs_path

# .env 位于项目根目录（按项目根定位，保证任意工作目录启动均可找到）
_ENV_PATH = get_abs_path('.env')


def _load_env() -> dict:
    """解析 .env 文件（key=value 格式，跳过注释与空行），与 chatbot.py 保持一致的轻量实现"""
    env = {}
    try:
        with open(_ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                env[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


_ENV = _load_env()

# ---- 配置常量 ----
# TTS 运行模式：demo = 优先 qwen3-tts + edge-tts 兜底；dev = 仅 edge-tts
TTS_MODE = _ENV.get('TTS_MODE', 'demo').strip().lower() or 'demo'
if TTS_MODE not in ('demo', 'dev'):
    print(f"[TTS] 警告: 未知的 TTS_MODE={TTS_MODE}，回退为 demo")
    TTS_MODE = 'demo'

EDGE_TTS_VOICE = _ENV.get('EDGE_TTS_VOICE', 'zh-CN-XiaoxiaoNeural').strip() or 'zh-CN-XiaoxiaoNeural'

# 阿里云百炼 qwen3-tts（云端多语言，需 API Key）
DASHSCOPE_API_KEY = _ENV.get('DASHSCOPE_API_KEY', '').strip()
DASHSCOPE_MODEL = _ENV.get('DASHSCOPE_MODEL', 'qwen3-tts-vd-2026-01-26').strip() or 'qwen3-tts-vd-2026-01-26'
DASHSCOPE_VOICE = _ENV.get('DASHSCOPE_VOICE', 'longxiaoxia_v2').strip() or 'longxiaoxia_v2'

# 不适合朗读的字符（emoji / 常见 markdown 符号），避免 TTS 读出乱码
_UNSPEAKABLE_RE = re.compile(
    '['                                  # emoji 范围
    '\U0001F300-\U0001FAFF'
    '\U00002600-\U000027BF'
    '\U0001F900-\U0001F9FF'
    '\U0000FE00-\U0000FE0F'
    '\U0001F1E6-\U0001F1FF'
    '*`_~#'                              # markdown 强调/标题符号
    ']'
)


class _StreamPlayer:
    """流式 PCM 音频播放器：后台线程消费队列并写入声卡，不阻塞调用方

    - begin() 启动播放线程；enqueue() 追加音频块（float32 单声道）；end() 结束本次播报
    - clear() 打断当前播报（供新播报抢占旧播报使用）
    """

    SAMPLE_RATE = 32000   # 统一播放采样率；各服务输出会重采样到该采样率
    CHANNELS = 1

    def __init__(self):
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self._stream = None
        self._stream_lock = threading.Lock()
        self._session = None   # 当前有效会话 ID；不匹配的音频块一律丢弃

    def set_session(self, session: int):
        """设置当前有效会话 ID：只有携带该 ID 的音频块才会被播放，其余视为陈旧数据丢弃"""
        self._session = session

    @property
    def session(self) -> int:
        """当前有效会话 ID（供合成线程判断自己的会话是否已被取代）"""
        return self._session

    def begin(self):
        """启动播放线程（若未启动）；启动前清空可能残留的数据"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._drain()
        self._thread = threading.Thread(target=self._writer, daemon=True, name='tts-player')
        self._thread.start()

    def enqueue(self, pcm: np.ndarray, session: int = None):
        """追加一段 float32 单声道音频（非阻塞）。

        携带 session 的块必须与当前有效会话一致，否则说明是
        被新播报打断后残留的陈旧音频（如旧会话仍在合成），直接丢弃。
        """
        if session is not None and session != self._session:
            return
        self._queue.put(pcm)

    def end(self, session: int = None):
        """结束当前播报：播放完队列中剩余音频后播放线程自动退出。

        仅当传入的 session 仍是当前有效会话时才放入结束哨兵，
        避免陈旧会话的结束信号错误终止新会话的播放。
        """
        if session is not None and session != self._session:
            return
        self._queue.put(None)

    def clear(self):
        """打断当前播报：立即停止播放并清空未播放的数据"""
        self._stop.set()
        self._queue.put(None)
        self._drain()
        with self._stream_lock:
            stream = self._stream
            self._stream = None
        if stream:
            try:
                stream.abort()   # 立即中断正在进行的播放（释放被阻塞的 write）
            except Exception:
                pass
        thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _drain(self):
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _writer(self):
        """播放线程：从队列取音频块写入声卡"""
        import sounddevice as sd
        stream = None
        try:
            stream = sd.OutputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype='float32',
                blocksize=1024,
            )
            stream.start()
            with self._stream_lock:
                self._stream = stream
            while not self._stop.is_set():
                try:
                    chunk = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                stream.write(np.asarray(chunk, dtype=np.float32).reshape(-1))
        except Exception as e:
            print(f"[TTS] 音频播放出错: {e}")
        finally:
            with self._stream_lock:
                if self._stream is stream:
                    self._stream = None
            if stream:
                try:
                    stream.stop()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass


_player = _StreamPlayer()

# 会话 ID 计数器：每次播报（speak）分配一个新 ID，用于丢弃被取代的陈旧会话残留音频
_session_counter = itertools.count(1)


# ==================== edge-tts（免费兜底，无需 Key） ====================

def _speak_with_edge(text: str, session: int) -> bool:
    """使用 edge-tts 兜底合成并播放（MP3 流式接收 → 解码 → 重采样 → 播放）"""
    try:
        return asyncio.run(_edge_stream(text, session))
    except Exception as e:
        print(f"[TTS] edge-tts 合成出错: {e}")
        return False


async def _edge_stream(text: str, session: int) -> bool:
    """edge-tts 流式接收 MP3 音频块，解码为 float32 PCM 后推入播放队列"""
    import edge_tts
    import soundfile as sf
    import soxr

    communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
    mp3 = bytearray()
    async for chunk in communicate.stream():
        if session != _player.session:   # 会话已被取代，不再收集
            return False
        if chunk.get("type") == "audio":
            mp3.extend(chunk["data"])
    if not mp3:
        return False

    # 解码 MP3 → float32 单声道 PCM，并重采样到播放采样率
    pcm, rate = sf.read(io.BytesIO(bytes(mp3)), dtype='float32')
    pcm = np.asarray(pcm, dtype=np.float32)
    if pcm.ndim > 1:
        pcm = pcm[:, 0]
    if rate != _StreamPlayer.SAMPLE_RATE:
        pcm = soxr.resample(pcm, rate, _StreamPlayer.SAMPLE_RATE)

    # 按 100ms 分块推入播放队列，实现边写边播
    block = int(_StreamPlayer.SAMPLE_RATE * 0.1)
    for i in range(0, len(pcm), block):
        if session != _player.session:
            break
        _player.enqueue(pcm[i:i + block], session)
    return True


# ==================== qwen3-tts（阿里云百炼，云端多语言，需 API Key） ====================

def _speak_with_dashscope(text: str, session: int) -> bool:
    """使用阿里云百炼 qwen3-tts 合成并播放（多语言混说，无需本地显卡）

    按模型名自动选择接入方式：
    - qwen3-tts-* / qwen-tts*（Qwen-TTS 声音设计/复刻等）：HTTP 流式（MultiModalConversation）
    - 其他（cosyvoice-* / qwen-audio-3.0-tts-*）：WebSocket（SpeechSynthesizer）
    未配置 DASHSCOPE_API_KEY 或未安装 dashscope 库时直接返回 False（不抛异常）。
    """
    if not DASHSCOPE_API_KEY:
        print("[TTS] 未配置 DASHSCOPE_API_KEY，跳过 qwen3-tts（请在 .env 中填写阿里云百炼 API Key）")
        return False
    try:
        import dashscope
    except ImportError:
        print("[TTS] 未安装 dashscope 库（pip install dashscope），跳过 qwen3-tts")
        return False

    if DASHSCOPE_MODEL.startswith('qwen3-tts') or DASHSCOPE_MODEL.startswith('qwen-tts'):
        return _speak_with_qwen_tts(dashscope, text, session)
    return _speak_with_cosyvoice_ws(dashscope, text, session)


def _speak_with_qwen_tts(dashscope, text: str, session: int) -> bool:
    """Qwen-TTS 系列（HTTP 流式）：MultiModalConversation 边收边播

    输出格式：首块为带 WAV 头的音频（24kHz），后续块为裸 int16 PCM。
    """
    import soundfile as sf
    import soxr

    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
    try:
        response = dashscope.MultiModalConversation.call(
            model=DASHSCOPE_MODEL,
            api_key=DASHSCOPE_API_KEY,
            text=text,
            voice=DASHSCOPE_VOICE,
            stream=True,
        )
    except Exception as e:
        print(f"[TTS] qwen3-tts 合成出错: {e}")
        return False

    produced = False
    first = True
    rate = 24000   # Qwen-TTS 流式输出默认 24kHz
    for chunk in response:
        if session != _player.session:   # 会话已被新播报取代，提前退出
            return produced
        if chunk.output is None:
            continue
        audio = getattr(chunk.output, 'audio', None)
        if not audio:
            continue
        raw = base64.b64decode(audio.data)
        if not raw:
            continue
        if first:
            # 首个音频块带 WAV 头：用 soundfile 解码并读取实际采样率
            try:
                wav, rate = sf.read(io.BytesIO(raw), dtype='float32')
                pcm = np.asarray(wav, dtype=np.float32)
                if pcm.ndim > 1:
                    pcm = pcm[:, 0]
            except Exception:
                return produced
            first = False
        else:
            # 后续块为裸 int16 PCM
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
        produced = True
        if rate != _StreamPlayer.SAMPLE_RATE:
            pcm = soxr.resample(pcm, rate, _StreamPlayer.SAMPLE_RATE)
        block = int(_StreamPlayer.SAMPLE_RATE * 0.1)
        for i in range(0, len(pcm), block):
            if session != _player.session:
                break
            _player.enqueue(pcm[i:i + block], session)
    return produced


def _speak_with_cosyvoice_ws(dashscope, text: str, session: int) -> bool:
    """CosyVoice / Qwen-Audio-TTS（WebSocket）：SpeechSynthesizer 非流式取整段 mp3 后播放"""
    from dashscope.audio.tts_v2 import SpeechSynthesizer
    import soundfile as sf
    import soxr

    dashscope.api_key = DASHSCOPE_API_KEY
    try:
        synthesizer = SpeechSynthesizer(model=DASHSCOPE_MODEL, voice=DASHSCOPE_VOICE)
        # 非流式调用：阻塞返回完整 mp3 音频（云端合成，对桌宠短文本足够快）
        mp3 = synthesizer.call(text)
    except Exception as e:
        print(f"[TTS] DashScope 合成出错: {e}")
        return False
    if not mp3:
        print("[TTS] DashScope 返回空音频")
        return False
    if session != _player.session:   # 合成期间会话可能已被新播报取代
        return False

    # 解码 mp3 → float32 单声道 PCM，并重采样到播放采样率
    pcm, rate = sf.read(io.BytesIO(mp3), dtype='float32')
    pcm = np.asarray(pcm, dtype=np.float32)
    if pcm.ndim > 1:
        pcm = pcm[:, 0]
    if rate != _StreamPlayer.SAMPLE_RATE:
        pcm = soxr.resample(pcm, rate, _StreamPlayer.SAMPLE_RATE)

    # 按 100ms 分块推入播放队列，实现边写边播
    block = int(_StreamPlayer.SAMPLE_RATE * 0.1)
    for i in range(0, len(pcm), block):
        if session != _player.session:
            break
        _player.enqueue(pcm[i:i + block], session)
    return True


# ==================== 对外接口 ====================

def _clean_text(text: str) -> str:
    """清理不适合朗读的字符（emoji / markdown 符号）"""
    return _UNSPEAKABLE_RE.sub('', text).strip()


def _speak_worker(text: str):
    """后台线程：先打断上一轮播报，再按 TTS_MODE 选择合成服务"""
    session = next(_session_counter)   # 本次播报的会话 ID（用于丢弃上一轮残留的陈旧音频）
    _player.clear()
    _player.begin()
    _player.set_session(session)
    try:
        if TTS_MODE == 'dev':
            # 开发模式：仅使用 edge-tts（免费、零配置）
            _speak_with_edge(text, session)
        else:
            # 演示模式：优先 qwen3-tts，失败则 edge-tts 兜底
            if not _speak_with_dashscope(text, session):
                # 仅在会话仍有效时才走 edge-tts 兜底，避免陈旧会话重复播报
                if session == _player.session:
                    _speak_with_edge(text, session)
    except Exception:
        traceback.print_exc()
    finally:
        _player.end(session)


def speak(text: str) -> None:
    """播报一段文本（非阻塞）。

    服务链由 TTS_MODE 决定：demo = qwen3-tts → edge-tts 兜底；dev = 仅 edge-tts。
    若正在播报上一段内容会先打断；合成与播放均在独立后台线程中执行，不阻塞桌宠 UI。
    """
    text = _clean_text(text)
    if not text:
        return
    threading.Thread(target=_speak_worker, args=(text,), daemon=True, name='tts-speak').start()


def stop() -> None:
    """立即停止当前语音播报"""
    next(_session_counter)   # 使进行中的会话立即失效（其后续合成的音频块将被丢弃）
    _player.clear()


def _main_test() -> None:
    """按当前 TTS_MODE 播放一段中英混说测试文本，验证服务链路

    用法：python -m client.voice.tts
    """
    import time
    text = "你好呀，我是你的 AI 助手哈达莉。This is a mixed language test, 中英混说也可以很自然。今天天气不错，要一起喝杯咖啡吗？"
    print("=" * 60)
    print(f"[TTS] 当前模式: {TTS_MODE}（demo=优先 qwen3-tts，dev=仅 edge-tts）")
    print(f"[TTS] qwen3-tts 模型: {DASHSCOPE_MODEL}，音色: {DASHSCOPE_VOICE}")
    print(f"[TTS] edge-tts 音色: {EDGE_TTS_VOICE}")
    print(f"[TTS] 测试文本: {text}")
    if TTS_MODE == 'demo' and not DASHSCOPE_API_KEY:
        print("[TTS] 警告：演示模式但未配置 DASHSCOPE_API_KEY，将仅使用 edge-tts")
    print("=" * 60)

    speak(text)
    time.sleep(0.5)   # 等待播放线程启动
    thread = _player._thread
    if thread and thread.is_alive():
        thread.join(timeout=90)
    print("[TTS] 测试结束")


if __name__ == '__main__':
    _main_test()
