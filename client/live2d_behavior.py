'''Live2D 行为纯函数：鼠标坐标归一化、平滑插值、随机动作组选择

设计约束：
- 不依赖 Qt / live2d，全部为纯函数，便于单元测试与调参；
- 归一化坐标范围为 [-1, 1]（部件中心为 0），超出部分按边界限幅；
- `Live2DWidget` 负责读取光标、调用本模块并把结果交给 `model.Drag`。
'''
import random

# 归一化坐标边界（-1 左/上，1 右/下）
CURSOR_MIN = -1.0
CURSOR_MAX = 1.0

# 空闲随机动作的触发间隔范围（秒）
RANDOM_INTERVAL_MIN = 8.0
RANDOM_INTERVAL_MAX = 15.0

# 动作状态机状态：空闲 / 随机动作播放中 / 表情动作播放中 / 表情回归过渡中
STATE_IDLE = "idle"
STATE_RANDOM_PLAYING = "random_playing"
STATE_EMOTION_PLAYING = "emotion_playing"
STATE_EMOTION_RETURNING = "emotion_returning"


def clamp(value: float, low: float = CURSOR_MIN, high: float = CURSOR_MAX) -> float:
    '''把数值限制在 [low, high] 区间'''
    return max(low, min(high, value))


def normalize_cursor(cursor_x: float, cursor_y: float,
                     width: float, height: float) -> tuple[float, float]:
    '''把部件内坐标映射为 [-1, 1] 的归一化坐标并限幅

    参数：
        cursor_x / cursor_y : 光标在部件内的坐标（像素）
        width / height      : 部件尺寸（像素），非正数时返回 (0.0, 0.0)
    返回：
        (nx, ny)，中心为 (0, 0)，左上为 (-1, -1)，右下为 (1, 1)
    '''
    if width <= 0 or height <= 0:
        return 0.0, 0.0
    nx = (cursor_x / width) * 2.0 - 1.0
    ny = (cursor_y / height) * 2.0 - 1.0
    return clamp(nx), clamp(ny)


def denormalize_cursor(nx: float, ny: float,
                       width: float, height: float) -> tuple[float, float]:
    '''把归一化坐标还原为部件内像素坐标（供 model.Drag 使用）

    与 `normalize_cursor` 互为逆运算；宽度/高度非正时返回 (0.0, 0.0)。
    '''
    if width <= 0 or height <= 0:
        return 0.0, 0.0
    return (nx + 1.0) * 0.5 * width, (ny + 1.0) * 0.5 * height


def smooth_toward(current: float, target: float, factor: float) -> float:
    '''指数平滑插值：把 current 朝 target 推进

    factor 取 0~1（越界自动限幅）：0 表示不动，1 表示立刻到达目标。
    逐帧调用可实现无跳变的跟随效果。
    '''
    f = clamp(factor, 0.0, 1.0)
    return current + (target - current) * f


def pick_random_group(groups, rng=None, exclude=None):
    '''从动作组中随机选择一个，尽量避开 exclude（避免连续重复）

    参数：
        groups  : 可选动作组名序列（如 GetMotionGroups() 的键）
        rng     : random.Random 实例或模块，默认 global random
        exclude : 刚播放过的组名；候选只剩它时仍会返回它
    返回：
        选中的组名；groups 为空时返回 None
    '''
    all_groups = list(groups)
    if not all_groups:
        return None
    candidates = [g for g in all_groups if g != exclude] or all_groups
    return (rng or random).choice(candidates)


def random_interval_seconds(rng=None,
                            low: float = RANDOM_INTERVAL_MIN,
                            high: float = RANDOM_INTERVAL_MAX) -> float:
    '''返回 [low, high] 区间内的随机间隔（秒）

    low > high 时自动交换，保证返回值始终落在合法区间。
    '''
    lo, hi = (low, high) if low <= high else (high, low)
    return (rng or random).uniform(lo, hi)


def next_state_on_motion_end(state: str) -> str:
    '''动作播放结束时的状态迁移

    表情动作 → 回归过渡；随机动作 → 空闲；其余保持不变。
    '''
    if state == STATE_EMOTION_PLAYING:
        return STATE_EMOTION_RETURNING
    if state == STATE_RANDOM_PLAYING:
        return STATE_IDLE
    return state
