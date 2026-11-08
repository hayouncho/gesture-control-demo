"""유튜브 제어 작업 스레드 (조하연 개인 샘플 workers.py 의 ControlWorker 를 줄인 버전).

카메라 루프(메인 스레드)는 명령을 submit() 으로 넘기기만 하고 바로 다음 프레임을 처리합니다.
창 찾기·활성화·플레이어 포커스·키 전송은 이 스레드가 순서대로 처리하므로 카메라 인식이 멈추지 않습니다.

  - 대상 자동 선택: 유튜브 창/탭을 찾아 (맨 앞 창 우선 -> 하나뿐이면 그것) 고름. 여러 개면 고르지 않음
  - 대상이 없을 때만 IDLE_REFRESH_SEC 마다 다시 찾음, 명령 때 대상이 사라졌으면 한 번 다시 찾아 재시도
  - 볼륨(반복 명령): 이전 명령을 처리 중이면 쌓지 않고 건너뜀 (입력 밀림 방지),
                     맨 앞 + 플레이어 포커스가 유지 중이면 활성화 단계를 건너뜀 (controller quick)
  - 1회 명령(K/L/J): 대기열에 넣되, COMMAND_MAX_WAIT 보다 오래 기다렸으면 실행하지 않음 (늦은 실행 방지)
  - UI Automation(COM)은 사용하는 스레드에서 초기화해야 하므로 이 스레드 안에서 백엔드를 만듦
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable

from .common import COMMAND_KO, Command
from .controller import FAILED, ControlResult, YouTubeController
from .youtube_target import NO_ACCESS, NOT_CONTROLLABLE, NO_VIDEO, STAGE_TARGET, Target

REPEAT_COMMANDS = (Command.VOLUME_UP, Command.VOLUME_DOWN)
COMMAND_MAX_WAIT = 2.0     # 이보다 오래 기다린 1회 명령은 실행하지 않음
IDLE_REFRESH_SEC = 3.0     # 대상이 없을 때 다시 찾는 간격
_STOP = object()


def choose_target(targets: list[Target], fg_hwnd: int) -> tuple[Target | None, str]:
    """제어할 대상 하나를 자동으로 고릅니다. (대상, 못 고른 이유)"""
    usable = [t for t in targets if t.page not in NOT_CONTROLLABLE]
    in_front = [t for t in usable if t.hwnd == fg_hwnd and t.selected]
    if len(in_front) == 1:
        return in_front[0], ""
    if len(usable) == 1:
        return usable[0], ""
    if len(usable) > 1:
        return None, (f"제어할 수 있는 유튜브 창/탭이 {len(usable)}개입니다. 제어할 유튜브를 맨 앞에 두거나 "
                      "하나만 열어 두세요")
    if any(t.page == NO_ACCESS for t in targets):
        return None, ("유튜브는 열려 있지만 브라우저가 웹 페이지 정보를 제공하지 않습니다 "
                      "(Chrome이면 chrome://accessibility 설정 확인)")
    if any(t.page == NO_VIDEO for t in targets):
        return None, "유튜브가 영상 재생 페이지가 아닙니다 (홈/검색/쇼츠). 영상을 열어 주세요"
    return None, "유튜브 창/탭을 찾지 못했습니다 (Edge에서 유튜브 영상을 열어 주세요)"


class ControlWorker(threading.Thread):
    def __init__(
        self,
        log: Callable[[str], None],
        backend_factory=None,
        press=None,
        foreground: Callable[[], int] | None = None,
        verify_delay: float = 0.25,
        idle_refresh: float = IDLE_REFRESH_SEC,
        max_wait: float = COMMAND_MAX_WAIT,
    ):
        super().__init__(name="ControlWorker", daemon=True)
        self._log = log
        self._backend_factory = backend_factory   # 테스트에서 가짜 백엔드 주입
        self._foreground = foreground
        self._idle_refresh = idle_refresh
        self._max_wait = max_wait
        self._jobs: queue.Queue = queue.Queue()
        self._busy = threading.Event()
        self._last_reason = ""
        kwargs = {"press": press} if press else {}
        self.controller = YouTubeController(live=True, verify_delay=verify_delay, **kwargs)

    # ---------------- 카메라(메인) 스레드에서 호출
    def submit(self, cmd: Command) -> bool:
        """명령을 넘김. 볼륨 반복인데 이전 명령을 처리 중이면 건너뛰고 False."""
        if cmd in REPEAT_COMMANDS and (self._busy.is_set() or not self._jobs.empty()):
            self._log(f"[건너뜀] {COMMAND_KO[cmd]}: 이전 명령을 처리하는 중이라 이번 반복은 보내지 않음")
            return False
        self._busy.set()   # 바로 다음 반복이 같은 틈에 또 들어오지 않도록 미리 표시
        self._jobs.put((cmd, time.monotonic()))
        return True

    def stop(self) -> None:
        self._jobs.put(_STOP)

    # ---------------- 제어 스레드
    def run(self) -> None:
        if self._backend_factory is not None:
            self._serve(self._backend_factory)
            return
        import uiautomation as auto  # UI Automation(COM)은 사용하는 스레드에서 초기화해야 함

        with auto.UIAutomationInitializerInThread():
            from .youtube_target import UIABackend
            self._serve(UIABackend)

    def _serve(self, factory) -> None:
        if self._foreground is None:
            from .youtube_target import foreground_hwnd
            self._foreground = foreground_hwnd
        try:
            self.controller.backend = factory()
        except Exception as e:
            self._log(f"[오류] 유튜브 창 제어 기능을 준비하지 못했습니다: {e}. 키를 보내지 않습니다")
            self._drain()
            return
        self._refresh()
        while True:
            try:
                job = self._jobs.get(timeout=self._idle_refresh)
            except queue.Empty:
                self._busy.clear()
                if self.controller.target is None:
                    self._refresh()
                continue
            if job is _STOP:
                break
            self._busy.set()
            try:
                self._command(*job)
            except Exception as e:  # 한 명령이 실패해도 스레드는 계속
                self._log(f"[오류] 제어 작업 오류: {e} (키를 보내지 않았거나 결과를 알 수 없음)")
            finally:
                if self._jobs.empty():
                    self._busy.clear()

    def _drain(self) -> None:
        """백엔드가 없을 때: 명령을 받아서 버리기만 함 (보내지 않은 이유는 시작할 때 한 번 출력)."""
        while self._jobs.get() is not _STOP:
            self._busy.clear()

    def _refresh(self) -> None:
        """유튜브 대상을 다시 찾음 (읽기 전용 — 포커스·재생 상태를 바꾸지 않음)."""
        backend = self.controller.backend
        try:
            targets = backend.find_targets()
        except Exception as e:
            targets = []
            self._log(f"[대상] 유튜브 창 검색 오류: {e}")
        target, reason = choose_target(targets, self._foreground())
        prev = self.controller.target
        self.controller.target = target
        if target is not None:
            if prev is None or not prev.same_as(target):
                if hasattr(backend, "reset_cache"):
                    backend.reset_cache()
                self._log(f"[대상] 제어 대상: {target.describe()}")
            self._last_reason = ""
        elif reason != self._last_reason:   # 같은 이유는 한 번만 출력
            self._log(f"[대상] {reason}")
            self._last_reason = reason

    def _command(self, cmd: Command, queued_at: float) -> None:
        waited = time.monotonic() - queued_at
        name = COMMAND_KO[cmd]
        if waited > self._max_wait:
            self._report(ControlResult(False, f"[취소] {name}: 이전 명령 처리로 {waited:.1f}초 늦어져 "
                                              "보내지 않음", FAILED, "대기"))
            return
        if self.controller.target is None:
            self._refresh()
            if self.controller.target is None:
                self._report(ControlResult(False, f"[실패:{STAGE_TARGET}] {name}: {self._last_reason or '대상 없음'} "
                                                  "(키를 보내지 않음)", FAILED, STAGE_TARGET))
                return
        repeat = cmd in REPEAT_COMMANDS
        result = self.controller.execute(cmd, quick=repeat, verify=not repeat)
        if not result.sent and result.stage == STAGE_TARGET:   # 대상이 닫힘·바뀜 -> 한 번 다시 찾아 재시도
            self._log(f"{result.message} -> 유튜브 창을 다시 찾습니다")
            self.controller.target = None
            self._refresh()
            if self.controller.target is None:
                self._report(ControlResult(False, f"[실패:{STAGE_TARGET}] {name}: {self._last_reason or '대상 없음'} "
                                                  "(키를 보내지 않음)", FAILED, STAGE_TARGET))
                return
            result = self.controller.execute(cmd, quick=repeat, verify=not repeat)
        self._report(result)

    def _report(self, result: ControlResult) -> None:
        self._log(result.message)
