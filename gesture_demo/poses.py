"""손 모양 진단 값 계산 (2단계).

손 하나(Hand)의 관절 좌표에서 다음 값을 계산합니다. 제스처를 판정하거나 명령을 내지는 않습니다.
  - 손바닥/손등 방향   : 손목(0), 검지 뿌리(5), 새끼 뿌리(17) 로 만든 두 벡터의 외적 부호 + 왼손/오른손
  - 펴진 손가락        : 검지~새끼는 손목에서 손끝/가운데 마디까지 거리 비, 엄지는 새끼 뿌리(17)에서의 거리 비
  - 검지·엄지 방향      : 검지 뿌리(5)->검지 끝(8), 엄지 뿌리(2)->엄지 끝(4) 벡터의 각도
  - 엄지-검지 끝 거리   : OK 사인 확인용, 손바닥 크기 배수

좌표는 hand_tracker.py 가 돌려주는 '거울 화면 기준 픽셀'입니다.
  x 증가 = 사용자 오른쪽, y 증가 = 아래쪽.  label = 사용자 실제 손("Left"/"Right")
MediaPipe 와 OpenCV 를 import 하지 않으므로 가짜 좌표로 자동 테스트할 수 있습니다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import config as C
from .common import Hand

# MediaPipe 손 관절 번호
WRIST = 0
THUMB_MCP, THUMB_TIP = 2, 4
INDEX_MCP, INDEX_TIP = 5, 8
MIDDLE_MCP = 9
PINKY_MCP = 17
# (이름, 가운데 마디 PIP, 손끝 TIP)
FOUR_FINGERS = (("검지", 6, 8), ("중지", 10, 12), ("약지", 14, 16), ("새끼", 18, 20))
FINGER_NAMES = ("엄지", "검지", "중지", "약지", "새끼")

PALM, BACK, SIDE = "손바닥", "손등", "옆면(불확실)"
FACING_EN = {PALM: "PALM", BACK: "BACK", SIDE: "SIDE"}
UP, DOWN, LEFT, RIGHT = "위", "아래", "왼쪽", "오른쪽"
DIR_EN = {UP: "UP", DOWN: "DOWN", LEFT: "LEFT", RIGHT: "RIGHT"}


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def palm_size(lm) -> float:
    """손목(0) ~ 중지 뿌리(9) 길이. 카메라와 거리가 달라져도 같은 기준으로 비교하기 위한 단위."""
    return max(_dist(lm[WRIST], lm[MIDDLE_MCP]), 1e-6)


def palm_cross(lm) -> float:
    """(검지 뿌리 - 손목) x (새끼 뿌리 - 손목) 의 z 성분 / 손바닥 크기^2.

    손을 화면 안에서 어떻게 돌려도 부호는 유지되고, 손을 뒤집으면(손바닥 <-> 손등) 부호가 바뀝니다.
    거울 좌표에서 오른손은 손바닥이 카메라를 향할 때 +, 왼손은 - 입니다 (두 손은 서로 거울상).
    크기가 0에 가까우면 손을 옆으로 세운 상태입니다.
    """
    w, i, p = lm[WRIST], lm[INDEX_MCP], lm[PINKY_MCP]
    ax, ay = i[0] - w[0], i[1] - w[1]
    bx, by = p[0] - w[0], p[1] - w[1]
    return (ax * by - ay * bx) / palm_size(lm) ** 2


def facing(label: str, cross: float) -> str:
    if abs(cross) < C.FACING_MIN_CROSS:
        return SIDE
    palm = cross > 0 if label == "Right" else cross < 0
    return PALM if palm else BACK


def angle_deg(a, b) -> float:
    """a -> b 방향 각도 (사용자 기준). 0 = 오른쪽, 90 = 위, 180/-180 = 왼쪽, -90 = 아래."""
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))  # 화면 y는 아래로 증가하므로 부호 반전


def direction(angle: float) -> str:
    if 45 <= angle < 135:
        return UP
    if -135 <= angle < -45:
        return DOWN
    return RIGHT if -45 <= angle < 45 else LEFT


def finger_ratios(lm) -> dict[str, float]:
    """손가락마다 '펴짐 정도' 비율. 기준값보다 크면 펴진 것으로 봅니다.

    검지~새끼: 손목~손끝 / 손목~가운데 마디  (펴면 약 1.3 이상, 접으면 1보다 작음)
    엄지     : 엄지 끝~새끼 뿌리 / 엄지 뿌리~새끼 뿌리 (엄지를 손바닥 쪽으로 접으면 작아짐)
    """
    w = lm[WRIST]
    ratios = {"엄지": _dist(lm[THUMB_TIP], lm[PINKY_MCP]) / max(_dist(lm[THUMB_MCP], lm[PINKY_MCP]), 1e-6)}
    for name, pip, tip in FOUR_FINGERS:
        ratios[name] = _dist(w, lm[tip]) / max(_dist(w, lm[pip]), 1e-6)
    return ratios


@dataclass
class HandPose:
    label: str
    score: float
    cross: float
    facing: str
    ratios: dict[str, float]
    extended: dict[str, bool]
    index_angle: float
    thumb_angle: float
    ok_ratio: float          # 엄지 끝~검지 끝 / 손바닥 크기

    @property
    def index_dir(self) -> str:
        return direction(self.index_angle)

    @property
    def thumb_dir(self) -> str:
        return direction(self.thumb_angle)

    def pattern(self) -> str:
        """펴진 손가락 목록. 예: '엄지+검지'"""
        names = [n for n in FINGER_NAMES if self.extended[n]]
        return "+".join(names) if names else "모두 접힘"

    def signature(self) -> tuple:
        """터미널에 '바뀜'으로 출력할 기준 (각도·비율 숫자는 제외)."""
        return (self.label, self.facing, tuple(self.extended[n] for n in FINGER_NAMES),
                self.index_dir, self.thumb_dir)


def analyze(hand: Hand) -> HandPose:
    lm = hand.landmarks
    cross = palm_cross(lm)
    ratios = finger_ratios(lm)
    extended = {n: r > (C.THUMB_EXTENDED_RATIO if n == "엄지" else C.FINGER_EXTENDED_RATIO)
                for n, r in ratios.items()}
    return HandPose(
        label=hand.label,
        score=hand.score,
        cross=cross,
        facing=facing(hand.label, cross),
        ratios=ratios,
        extended=extended,
        index_angle=angle_deg(lm[INDEX_MCP], lm[INDEX_TIP]),
        thumb_angle=angle_deg(lm[THUMB_MCP], lm[THUMB_TIP]),
        ok_ratio=_dist(lm[THUMB_TIP], lm[INDEX_TIP]) / palm_size(lm),
    )
