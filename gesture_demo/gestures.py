"""제스처 판별 + 인식 상태 관리 (3~4단계).

poses.py 의 진단 값(손바닥/손등, 펴진 손가락, 방향, 엄지-검지 거리)으로 손 하나의 자세를 고르고,
손마다 상태를 따로 기억해서 명령(Event)을 만듭니다. 키 입력·유튜브 제어는 하지 않습니다.
조하연 개인 샘플 gestures.py 의 구조(손별 상태, 연속 프레임 확인, V 사인 전환, 자동 종료)를 재사용했습니다.

  자세        조건                                              명령
  V 사인      검지·중지 펴짐, 약지·새끼 접힘 (엄지·방향 무관)       1초 유지 -> 인식 시작/종료 전환
  OK 사인     엄지 끝~검지 끝 가까움 + 중지·약지·새끼 펴짐          재생/일시정지 (K) 1회
  총          엄지·검지만 펴짐 + 손등                              왼손 10초 앞으로 (L) / 오른손 10초 뒤로 (J) 1회
  검지 위     검지만 펴짐 + 손바닥 + 검지 위쪽                      볼륨 증가 (↑) 0.5초 후 0.3초마다 반복
  엄지 아래   엄지만 펴짐 + 손바닥 + 엄지 아래쪽                    볼륨 감소 (↓) 같은 반복

안정화
  - 자세는 CONFIRM_FRAMES 프레임 연속으로 같아야 바뀜 (풀릴 때도 같음) -> 순간 깜빡임 무시
  - 1회 명령(OK·총)은 '자세가 새로 확정된 순간'에만 실행 -> 유지해도 반복 없음, 풀었다 다시 해야 재실행
  - V 사인은 한 번 유지에 한 번만 전환, 두 손 V 가 동시에 전환하지 않음
  - 전환 직후 TOGGLE_BLOCK_SEC 동안 명령 무시
  - 양손이 서로 다른 명령 자세면 아무것도 실행하지 않음 (그 사이 새로 취한 1회 명령은 버림, 볼륨은 대기 시간부터 다시)
  - 인식 중 손이 AUTO_DEACTIVATE_SEC 동안 안 보이면 자동 종료
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from . import config as C
from .common import COMMAND_KEY, COMMAND_KO, Command, Event, EventType, Hand
from .poses import BACK, DOWN, FINGER_NAMES, PALM, UP, HandPose, analyze

HAND_KO = {"Left": "왼손", "Right": "오른손"}


class Gesture(Enum):
    V = "V"
    OK = "OK"
    GUN = "GUN"
    POINT_UP = "POINT_UP"
    THUMB_DOWN = "THUMB_DOWN"


GESTURE_KO = {Gesture.V: "V 사인", Gesture.OK: "OK 사인", Gesture.GUN: "총",
              Gesture.POINT_UP: "검지 위", Gesture.THUMB_DOWN: "엄지 아래"}
REPEAT_COMMANDS = (Command.VOLUME_UP, Command.VOLUME_DOWN)


def classify(p: HandPose) -> Gesture | None:
    """한 프레임의 자세. 해당 없으면 None."""
    ext = p.extended

    def only(*names: str) -> bool:
        return all(ext[n] == (n in names) for n in FINGER_NAMES)

    if p.ok_ratio <= C.OK_MAX_TIP_DIST and ext["중지"] and ext["약지"] and ext["새끼"]:
        return Gesture.OK
    if ext["검지"] and ext["중지"] and not ext["약지"] and not ext["새끼"]:
        return Gesture.V
    if only("엄지", "검지") and p.facing == BACK:
        return Gesture.GUN
    if only("검지") and p.facing == PALM and p.index_dir == UP:
        return Gesture.POINT_UP
    if only("엄지") and p.facing == PALM and p.thumb_dir == DOWN:
        return Gesture.THUMB_DOWN
    return None


def command_for(g: Gesture | None, label: str) -> Command | None:
    if g == Gesture.OK:
        return Command.PLAY_PAUSE
    if g == Gesture.GUN:
        return Command.SEEK_FORWARD_10 if label == "Left" else Command.SEEK_BACK_10
    if g == Gesture.POINT_UP:
        return Command.VOLUME_UP
    if g == Gesture.THUMB_DOWN:
        return Command.VOLUME_DOWN
    return None


_UNSET = object()


@dataclass
class _HandState:
    """손 하나(왼손/오른손)마다 따로 기억하는 상태."""

    last_seen: float = -math.inf
    stable: Gesture | None = None     # 연속 프레임 확인을 통과한 자세
    stable_since: float = 0.0         # 그 자세를 처음 취한 시각
    fresh: bool = False               # 이번 프레임에 자세가 새로 확정됐는지
    candidate: object = _UNSET
    candidate_count: int = 0
    candidate_since: float = 0.0
    toggled: bool = False             # 이번 V 사인 유지로 이미 전환했는지
    next_repeat: float | None = None  # 볼륨: 다음 실행 시각 (None = 아직 대기 시작 전)

    def update(self, raw: Gesture | None, t: float) -> None:
        if raw is self.candidate:
            self.candidate_count += 1
        else:
            self.candidate, self.candidate_count, self.candidate_since = raw, 1, t
        self.fresh = False
        if self.candidate_count >= C.CONFIRM_FRAMES and raw != self.stable:
            self.stable, self.stable_since, self.fresh = raw, self.candidate_since, True
            self.toggled = False
            self.next_repeat = None

    def reset(self) -> None:
        last_seen = self.last_seen
        self.__init__()
        self.last_seen = last_seen


class GestureRecognizer:
    def __init__(self) -> None:
        self.active = False
        self.block_until = -math.inf
        self.last_hand_time: float | None = None
        self.in_conflict = False
        self._states: dict[str, _HandState] = {}
        self.hand_info: dict[str, str] = {}   # 표시용: 손 키 -> 확정된 자세 이름

    # ------------------------------------------------------------------ 공개 함수
    def update(self, hands: list[Hand], t: float) -> list[Event]:
        """한 프레임의 손 목록과 현재 시각(초)을 받아 이벤트 목록을 돌려줍니다."""
        events: list[Event] = []
        proposals: list[tuple[str, _HandState, Command]] = []
        keys = self._keys(hands)
        toggled_now = False

        for key, hand in zip(keys, hands):
            st = self._states.setdefault(key, _HandState())
            if t - st.last_seen > C.HAND_LOST_RESET_SEC:
                st.reset()  # 손을 놓쳤다가 다시 찾음 -> 새 자세로 시작
            st.last_seen = t
            st.update(classify(analyze(hand)), t)

            if (st.stable == Gesture.V and not st.toggled and not toggled_now
                    and t - st.stable_since >= C.ACTIVATION_HOLD_SEC):
                st.toggled = toggled_now = True
                self._set_active(not self.active, t)
                word = "시작" if self.active else "종료"
                events.append(Event(EventType.ACTIVATED if self.active else EventType.DEACTIVATED,
                                    f"{self._name(key)} V 사인 {C.ACTIVATION_HOLD_SEC:g}초 -> 인식 {word}", hand=key))

            cmd = command_for(st.stable, hand.label)
            if cmd is not None:
                proposals.append((key, st, cmd))

        if self.active and t >= self.block_until and not toggled_now:
            events.extend(self._commands(proposals, t))
        else:
            for _, st, _ in proposals:
                st.next_repeat = None   # 인식 꺼짐·전환 직후: 볼륨은 대기 시간부터 다시
            self.in_conflict = False

        if hands:
            self.last_hand_time = t
        elif (self.active and self.last_hand_time is not None
              and t - self.last_hand_time >= C.AUTO_DEACTIVATE_SEC):
            self._set_active(False, t)
            events.append(Event(EventType.DEACTIVATED,
                                f"손이 {C.AUTO_DEACTIVATE_SEC:g}초 동안 보이지 않아 인식을 종료합니다."))

        self.hand_info = {k: GESTURE_KO.get(self._states[k].stable, "-") for k in keys}
        return events

    # ------------------------------------------------------------------ 명령
    def _commands(self, proposals, t: float) -> list[Event]:
        cmds = {cmd for _, _, cmd in proposals}
        if len(cmds) > 1:   # 양손이 서로 다른 명령 -> 아무것도 실행하지 않음
            for _, st, _ in proposals:
                st.next_repeat = None
            if self.in_conflict:
                return []
            self.in_conflict = True
            desc = ", ".join(f"{self._name(k)} {COMMAND_KO[c]}" for k, _, c in proposals)
            return [Event(EventType.IGNORED, f"양손 명령 충돌 ({desc}) -> 실행하지 않음")]
        self.in_conflict = False

        events, fired = [], set()
        for key, st, cmd in proposals:
            if cmd in REPEAT_COMMANDS:
                if st.next_repeat is None:
                    # 자세를 취한 순간부터 대기. 충돌·꺼짐으로 멈췄다가 다시 시작하면 지금부터 대기
                    st.next_repeat = st.stable_since + C.VOLUME_HOLD_SEC if st.fresh else t + C.VOLUME_HOLD_SEC
                if t < st.next_repeat:
                    continue
                st.next_repeat += C.VOLUME_REPEAT_SEC
                if st.next_repeat <= t:            # 프레임이 늦게 들어와도 몰아서 실행하지 않음
                    st.next_repeat = t + C.VOLUME_REPEAT_SEC
            elif not st.fresh:
                continue                          # 1회 명령: 새로 확정된 순간에만
            if cmd in fired:                      # 두 손이 같은 명령을 같은 프레임에 -> 한 번만
                continue
            fired.add(cmd)
            events.append(Event(EventType.COMMAND,
                                f"{self._name(key)} {GESTURE_KO[st.stable]} -> {COMMAND_KO[cmd]} ({COMMAND_KEY[cmd]} 키)",
                                cmd, key))
        return events

    # ------------------------------------------------------------------ 도우미
    def _set_active(self, active: bool, t: float) -> None:
        self.active = active
        self.block_until = t + C.TOGGLE_BLOCK_SEC
        self.last_hand_time = t
        self.in_conflict = False
        for st in self._states.values():
            st.next_repeat = None
            if st.stable == Gesture.V:
                st.toggled = True   # 다른 손이 들고 있던 V 사인이 곧바로 다시 전환하지 않도록

    @staticmethod
    def _keys(hands: list[Hand]) -> list[str]:
        keys, seen = [], {}
        for h in hands:
            n = seen.get(h.label, 0)
            seen[h.label] = n + 1
            keys.append(h.label if n == 0 else f"{h.label}#{n + 1}")  # 같은 판별이 두 개 잡힌 경우
        return keys

    @staticmethod
    def _name(key: str) -> str:
        label, _, rest = key.partition("#")
        return HAND_KO.get(label, label) + (f"#{rest}" if rest else "")
