"""유튜브 제어 (조하연 개인 샘플 controller.py 재사용).

방식: 유튜브 창(브라우저 탭 또는 유튜브 앱)을 명령이 있을 때만 활성화하고, 영상 플레이어에
      입력 포커스가 있는 것을 확인한 뒤 유튜브 '키보드 단축키'를 보냅니다.

    명령            유튜브 단축키
    재생/일시정지    K
    10초 뒤로        J      (← 화살표는 5초라서 10초에 맞추려고 J/L 사용)
    10초 앞으로      L
    볼륨 증가        ↑      (유튜브 영상 자체 볼륨 5%. 플레이어에 포커스가 있어야 동작)
    볼륨 감소        ↓

왜 플레이어 포커스가 필요한가
  - K/J/L 은 검색창에 커서가 있으면 글자로 입력됩니다.
  - ↑/↓ 는 플레이어에 포커스가 있을 때만 볼륨이고, 아니면 브라우저가 페이지를 스크롤합니다.
  그래서 '포커스가 실제로 플레이어 안에 있는지'를 확인한 뒤에만 키를 보냅니다.

gesture-demo 변경점
  - execute(quick=True): 이미 맨 앞 + 플레이어 포커스 유지(backend.ready)면 활성화·포커스 단계를 건너뜀.
    확인에 실패하면 원래대로 전체 준비(prepare)를 합니다. -> 볼륨 반복이 밀리지 않게
  - execute(verify=False): 키를 보낸 뒤 결과 확인(0.25초 대기 + 상태 읽기)을 생략
  - 대상 선택은 control_worker.py 에서 자동으로 함 (번호 입력 선택 기능 제거)
"""
from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .common import COMMAND_KO, Command
from .youtube_target import STAGE_TARGET, Target

VK_UP, VK_DOWN = 0x26, 0x28
KEYMAP: dict[Command, tuple[str, int, bool]] = {
    #                         (표시 이름, 가상 키 코드, 확장 키 여부)
    Command.PLAY_PAUSE: ("K", 0x4B, False),
    Command.SEEK_BACK_10: ("J", 0x4A, False),
    Command.SEEK_FORWARD_10: ("L", 0x4C, False),
    Command.VOLUME_UP: ("Up", VK_UP, True),
    Command.VOLUME_DOWN: ("Down", VK_DOWN, True),
}

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def send_key(vk: int, extended: bool) -> None:
    """키를 한 번 눌렀다 뗍니다 (맨 앞 창의 포커스된 요소로 전달됨)."""
    if sys.platform != "win32":
        raise RuntimeError("키 입력은 Windows에서만 지원합니다.")
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = KEYEVENTF_EXTENDEDKEY if extended else 0
    user32.keybd_event(vk, scan, flags, 0)
    user32.keybd_event(vk, scan, flags | KEYEVENTF_KEYUP, 0)


class Backend(Protocol):
    """youtube_target.UIABackend 와 같은 함수 모양. 테스트에서는 가짜로 바꿔 끼웁니다."""

    def find_targets(self) -> list[Target]: ...
    def is_alive(self, t: Target) -> tuple[bool, str]: ...
    def ready(self, t: Target) -> bool: ...
    def prepare(self, t: Target) -> tuple[bool, str, str]: ...   # (성공, 실패 단계, 설명)
    def player_state(self, t: Target) -> dict | None: ...


# 결과 종류
TEST = "test"                # 테스트 모드: 아무것도 안 함
FAILED = "failed"            # 준비 단계에서 실패 -> 키를 보내지 않음
VERIFIED = "verified"        # 키를 보냈고 플레이어 상태 변화도 확인함
UNVERIFIED = "unverified"    # 키는 보냈지만 결과를 확인하지 못함 (재전송하지 않음)
SENT = "sent"                # 키를 보냄, 결과 확인은 생략 (볼륨 반복)

STAGE_SEND = "키 전송"
STAGE_VERIFY = "결과 확인"


@dataclass
class ControlResult:
    sent: bool              # 실제로 키를 보냈는지
    message: str            # 표시용 설명
    outcome: str = ""       # TEST / FAILED / VERIFIED / UNVERIFIED / SENT
    stage: str = ""         # 실패(또는 확인 실패) 단계 이름


class YouTubeController:
    def __init__(
        self,
        live: bool = False,
        backend: Backend | None = None,
        press: Callable[[int, bool], None] = send_key,
        target: Target | None = None,
        verify_delay: float = 0.25,
    ):
        self.live = live
        self.backend = backend
        self.target = target
        self._press = press
        self._verify_delay = verify_delay

    def execute(self, cmd: Command, quick: bool = False, verify: bool = True) -> ControlResult:
        key_name, vk, extended = KEYMAP[cmd]
        name = COMMAND_KO[cmd]

        if not self.live:
            return ControlResult(False, f"[테스트] {name}: '{key_name}' 키 예정 (보내지 않음)", TEST)
        if self.target is None or self.backend is None:
            return ControlResult(False, f"[실패:{STAGE_TARGET}] {name}: 제어할 유튜브 창이 없습니다 "
                                        "(키를 보내지 않음)", FAILED, STAGE_TARGET)

        if quick and self._safe_ready():
            detail = "포커스 유지 확인"
        else:
            ok, stage, detail = self.backend.prepare(self.target)
            if not ok:
                return ControlResult(False, f"[실패:{stage}] {name}: {detail} (키를 보내지 않음)", FAILED, stage)
        focus = getattr(self.backend, "last_focus", "")
        if focus:   # 진단용: 키를 보내기 직전에 확인한 포커스 요소
            detail += f", 포커스: {focus}"

        before = self._safe_state() if verify else None
        try:
            self._press(vk, extended)   # 명령 1회 = 키 1회. 실패해도 다시 보내지 않음(중복 실행 방지)
        except Exception as e:
            return ControlResult(False, f"[실패:{STAGE_SEND}] {name}: 키 입력 오류 {e}", FAILED, STAGE_SEND)
        if not verify:
            return ControlResult(True, f"[실행] {name} -> '{key_name}' 키 ({detail})", SENT)
        time.sleep(self._verify_delay)
        after = self._safe_state()
        change, verified = _describe_change(cmd, before, after)
        if verified:
            return ControlResult(True, f"[실행] {name} -> '{key_name}' 키 ({detail}){change}", VERIFIED)
        # 키는 이미 보냈으므로 다시 보내지 않음. 화면으로 직접 확인하도록 안내
        return ControlResult(True, f"[실행·확인 안 됨] {name} -> '{key_name}' 키 보냄 ({detail}){change}. "
                                   "다시 보내지 않았습니다 — 영상 화면으로 확인하세요", UNVERIFIED, STAGE_VERIFY)

    def _safe_ready(self) -> bool:
        try:
            return bool(self.backend.ready(self.target))
        except Exception:
            return False

    def _safe_state(self) -> dict | None:
        try:
            return self.backend.player_state(self.target)
        except Exception:
            return None


def _describe_change(cmd: Command, before: dict | None, after: dict | None) -> tuple[str, bool]:
    """키를 보낸 뒤 플레이어 상태가 바뀌었는지. (표시 문구, 변화 확인 여부)"""
    if not before or not after:
        return " / 결과 확인 불가: 플레이어 상태를 읽지 못함", False
    if cmd in (Command.VOLUME_UP, Command.VOLUME_DOWN):
        key, label = "volume", "볼륨"
    elif cmd == Command.PLAY_PAUSE:
        b, a = before.get("paused"), after.get("paused")
        if b is None or a is None:
            return " / 결과 확인 불가: 재생 상태를 읽지 못함", False
        word = {True: "정지", False: "재생"}
        if a != b:
            return f" / 확인: {word[b]} -> {word[a]}", True
        return " / 재생 상태 변화가 확인되지 않음", False
    else:
        key, label = "position", "재생 위치(초)"
    b, a = before.get(key), after.get(key)
    if b is None or a is None:
        return f" / 결과 확인 불가: {label}를 읽지 못함", False
    if a != b:
        return f" / 확인: {label} {b:g} -> {a:g}", True
    return f" / {label} 변화가 확인되지 않음({a:g}, 최대·최소값일 수 있음)", False
