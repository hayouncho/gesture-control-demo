"""유튜브 제어 자동 테스트 (실제 창·키 입력 없음: 가짜 백엔드 + 가짜 키 입력).

    python -m unittest discover -s tests -t .
"""
import threading
import time
import unittest

from gesture_demo.common import Command
from gesture_demo.control_worker import ControlWorker, choose_target
from gesture_demo.controller import FAILED, KEYMAP, SENT, STAGE_SEND, TEST, VERIFIED, YouTubeController
from gesture_demo.youtube_target import NO_ACCESS, NO_VIDEO, STAGE_FOCUS, STAGE_TARGET, UNKNOWN, VIDEO, Target


def target(hwnd=100, tab=1, selected=True, page=VIDEO):
    return Target(hwnd, "browser", "Edge", f"영상{tab}", (tab,), selected, page, 1, tab)


class FakeBackend:
    def __init__(self, targets=None, prepare_result=(True, "", "창 활성화 -> 플레이어 포커스"),
                 ready=False, prepare_delay=0.0):
        self.targets = [target()] if targets is None else targets
        self.prepare_results = [prepare_result] if isinstance(prepare_result, tuple) else list(prepare_result)
        self.ready_value = ready
        self.prepare_delay = prepare_delay
        self.calls = []
        self.presses = 0

    def find_targets(self):
        self.calls.append("find")
        return list(self.targets)

    def is_alive(self, t):
        return True, "OK"

    def ready(self, t):
        self.calls.append("ready")
        if isinstance(self.ready_value, Exception):
            raise self.ready_value
        return self.ready_value

    def prepare(self, t):
        self.calls.append("prepare")
        time.sleep(self.prepare_delay)
        return self.prepare_results.pop(0) if len(self.prepare_results) > 1 else self.prepare_results[0]

    def player_state(self, t):
        self.calls.append("state")
        n = self.presses
        return {"paused": n % 2 == 1, "volume": 50 + 5 * n, "position": 10.0 * n}


class Keys:
    def __init__(self, backend=None):
        self.sent = []
        self.backend = backend
        self.lock = threading.Lock()

    def __call__(self, vk, extended):
        with self.lock:
            self.sent.append(vk)
            if self.backend:
                self.backend.presses += 1


def make_controller(backend, live=True, tgt=None):
    keys = Keys(backend)
    ctl = YouTubeController(live=live, backend=backend, press=keys, target=tgt or target(), verify_delay=0)
    return ctl, keys


# ====================================================================== controller.py
class ControllerTest(unittest.TestCase):
    def test_keymap(self):
        names = {cmd: KEYMAP[cmd][0] for cmd in Command}
        self.assertEqual(names, {Command.PLAY_PAUSE: "K", Command.SEEK_FORWARD_10: "L", Command.SEEK_BACK_10: "J",
                                 Command.VOLUME_UP: "Up", Command.VOLUME_DOWN: "Down"})

    def test_test_mode_never_touches_window_or_keys(self):
        b = FakeBackend()
        ctl, keys = make_controller(b, live=False)
        r = ctl.execute(Command.PLAY_PAUSE)
        self.assertEqual((r.sent, r.outcome, keys.sent, b.calls), (False, TEST, [], []))

    def test_no_target_sends_nothing(self):
        b = FakeBackend()
        ctl, keys = make_controller(b)
        ctl.target = None
        r = ctl.execute(Command.PLAY_PAUSE)
        self.assertEqual((r.sent, r.stage, keys.sent), (False, STAGE_TARGET, []))

    def test_prepare_failure_sends_nothing_and_names_stage(self):
        b = FakeBackend(prepare_result=(False, STAGE_FOCUS, "영상 플레이어에 입력 포커스를 주지 못했습니다"))
        ctl, keys = make_controller(b)
        r = ctl.execute(Command.VOLUME_UP)
        self.assertEqual((r.sent, r.outcome, keys.sent), (False, FAILED, []))
        self.assertIn(STAGE_FOCUS, r.message)

    def test_one_shot_prepares_sends_once_and_verifies(self):
        b = FakeBackend()
        ctl, keys = make_controller(b)
        r = ctl.execute(Command.PLAY_PAUSE)
        self.assertEqual((r.sent, r.outcome, keys.sent), (True, VERIFIED, [0x4B]))
        self.assertIn("prepare", b.calls)

    def test_quick_skips_prepare_when_focus_kept(self):
        b = FakeBackend(ready=True)
        ctl, keys = make_controller(b)
        r = ctl.execute(Command.VOLUME_UP, quick=True, verify=False)
        self.assertEqual((r.sent, r.outcome, keys.sent), (True, SENT, [0x26]))
        self.assertEqual(b.calls, ["ready"])          # 활성화·포커스·결과 확인 없음

    def test_quick_falls_back_to_prepare(self):
        for ready in (False, RuntimeError("UIA 오류")):
            with self.subTest(ready=ready):
                b = FakeBackend(ready=ready)
                ctl, keys = make_controller(b)
                r = ctl.execute(Command.VOLUME_DOWN, quick=True, verify=False)
                self.assertEqual((r.sent, keys.sent), (True, [0x28]))
                self.assertEqual(b.calls, ["ready", "prepare"])

    def test_quick_never_sends_when_prepare_fails(self):
        b = FakeBackend(ready=False, prepare_result=(False, STAGE_FOCUS, "포커스 실패"))
        ctl, keys = make_controller(b)
        r = ctl.execute(Command.VOLUME_UP, quick=True, verify=False)
        self.assertEqual((r.sent, keys.sent), (False, []))

    def test_key_error_is_reported(self):
        b = FakeBackend()

        def boom(vk, ext):
            raise OSError("입력 차단")
        ctl = YouTubeController(live=True, backend=b, press=boom, target=target(), verify_delay=0)
        r = ctl.execute(Command.PLAY_PAUSE)
        self.assertEqual((r.sent, r.stage), (False, STAGE_SEND))


class FakeCtrl:
    """UIA 요소 흉내: 종류, AutomationId, 클래스, 부모."""

    def __init__(self, kind, aid="", cls="", parent=None, rid=None):
        self.ControlTypeName, self.AutomationId, self.ClassName, self.Name = kind, aid, cls, ""
        self._parent, self._rid = parent, rid or (id(self),)

    def GetParentControl(self):
        return self._parent

    def GetRuntimeId(self):
        return self._rid


class FocusCheckTest(unittest.TestCase):
    """youtube_target.UIABackend._focus_in_player: 재생 위치 바(슬라이더) 포커스는 거부해야 함."""

    def setUp(self):
        from gesture_demo.youtube_target import UIABackend
        doc = FakeCtrl("DocumentControl")
        self.player = FakeCtrl("GroupControl", aid="movie_player", parent=doc)
        self.backend = UIABackend.__new__(UIABackend)   # uiautomation 초기화 없이 함수만 시험
        self.focused = None
        self.backend.auto = type("Auto", (), {"GetFocusedControl": lambda _: self.focused})()
        self.doc = doc

    def check(self, focused):
        self.focused = focused
        return self.backend._focus_in_player(self.player)

    def test_player_itself(self):
        self.assertTrue(self.check(self.player))

    def test_button_inside_player(self):
        controls = FakeCtrl("GroupControl", cls="ytp-chrome-bottom", parent=self.player)
        self.assertTrue(self.check(FakeCtrl("ButtonControl", cls="ytp-play-button", parent=controls)))

    def test_progress_bar_is_rejected(self):
        controls = FakeCtrl("GroupControl", cls="ytp-chrome-bottom", parent=self.player)
        bar = FakeCtrl("SliderControl", cls="ytp-progress-bar", parent=controls)
        self.assertFalse(self.check(bar))
        self.assertIn("ytp-progress-bar", self.backend.last_focus)

    def test_volume_slider_is_rejected(self):
        self.assertFalse(self.check(FakeCtrl("SliderControl", cls="ytp-volume-panel", parent=self.player)))

    def test_outside_player_is_rejected(self):
        self.assertFalse(self.check(FakeCtrl("EditControl", aid="search", parent=self.doc)))
        self.assertFalse(self.check(None))


class FocusLogTest(unittest.TestCase):
    def test_focus_element_is_shown_in_result(self):
        b = FakeBackend(ready=True)
        b.last_focus = "GroupControl movie_player"
        ctl, _ = make_controller(b)
        r = ctl.execute(Command.VOLUME_UP, quick=True, verify=False)
        self.assertIn("포커스: GroupControl movie_player", r.message)


# ====================================================================== control_worker.py
class ChooseTargetTest(unittest.TestCase):
    def test_front_window_selected_tab_wins(self):
        a, b = target(hwnd=100), target(hwnd=200)
        self.assertIs(choose_target([a, b], 200)[0], b)

    def test_single_usable_target(self):
        t = target(selected=False, page=UNKNOWN)
        self.assertIs(choose_target([t, target(hwnd=300, page=NO_VIDEO)], 0)[0], t)

    def test_many_targets_not_in_front_choose_none(self):
        t, why = choose_target([target(hwnd=100), target(hwnd=200)], 999)
        self.assertIsNone(t)
        self.assertIn("2개", why)

    def test_reasons(self):
        self.assertIn("웹 페이지 정보", choose_target([target(page=NO_ACCESS)], 0)[1])
        self.assertIn("영상을 열어", choose_target([target(page=NO_VIDEO)], 0)[1])
        self.assertIn("찾지 못했습니다", choose_target([], 0)[1])


def wait_until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class WorkerTest(unittest.TestCase):
    def start(self, backend, **kw):
        self.logs = []
        self.keys = Keys(backend)
        w = ControlWorker(self.logs.append, backend_factory=lambda: backend, press=self.keys,
                          foreground=lambda: 0, verify_delay=0, idle_refresh=kw.pop("idle_refresh", 0.05), **kw)
        w.start()
        self.addCleanup(lambda: (w.stop(), w.join(2)))
        return w

    def log_has(self, text):
        return any(text in m for m in self.logs)

    def test_command_is_sent_once(self):
        b = FakeBackend()
        w = self.start(b)
        w.submit(Command.PLAY_PAUSE)
        self.assertTrue(wait_until(lambda: self.log_has("[실행]")))
        self.assertEqual(self.keys.sent, [0x4B])

    def test_no_youtube_sends_nothing_and_logs_reason(self):
        b = FakeBackend(targets=[])
        w = self.start(b)
        w.submit(Command.SEEK_FORWARD_10)
        self.assertTrue(wait_until(lambda: self.log_has("[실패:")))
        self.assertEqual(self.keys.sent, [])
        self.assertTrue(self.log_has("찾지 못했습니다"))

    def test_repeat_skipped_while_busy_then_accepted(self):
        b = FakeBackend(prepare_delay=0.3)
        w = self.start(b)
        self.assertTrue(w.submit(Command.VOLUME_UP))
        self.assertFalse(w.submit(Command.VOLUME_UP))     # 처리 중 -> 쌓지 않음
        self.assertFalse(w.submit(Command.VOLUME_UP))
        self.assertTrue(wait_until(lambda: len(self.keys.sent) == 1 and not w._busy.is_set()))
        self.assertTrue(w.submit(Command.VOLUME_UP))
        self.assertTrue(wait_until(lambda: len(self.keys.sent) == 2))
        self.assertEqual(sum("[건너뜀]" in m for m in self.logs), 2)

    def test_one_shot_waits_in_queue_while_busy(self):
        b = FakeBackend(prepare_delay=0.2)
        w = self.start(b)
        w.submit(Command.VOLUME_UP)
        w.submit(Command.PLAY_PAUSE)                       # 1회 명령은 버리지 않음
        self.assertTrue(wait_until(lambda: len(self.keys.sent) == 2))
        self.assertEqual(self.keys.sent, [0x26, 0x4B])

    def test_stale_one_shot_is_cancelled(self):
        b = FakeBackend(prepare_delay=0.3)
        w = self.start(b, max_wait=0.1)
        w.submit(Command.PLAY_PAUSE)
        w.submit(Command.SEEK_BACK_10)
        self.assertTrue(wait_until(lambda: self.log_has("[취소]")))
        self.assertEqual(self.keys.sent, [0x4B])

    def test_closed_target_is_found_again_and_retried_once(self):
        b = FakeBackend(prepare_result=[(False, STAGE_TARGET, "대상 탭이 닫혔습니다"), (True, "", "창 활성화")])
        w = self.start(b)
        self.assertTrue(wait_until(lambda: b.calls.count("find") >= 1))
        w.submit(Command.SEEK_FORWARD_10)
        self.assertTrue(wait_until(lambda: self.log_has("[실행")))
        self.assertEqual(self.keys.sent, [0x4C])
        self.assertEqual(b.calls.count("prepare"), 2)

    def test_volume_uses_quick_path_without_verification(self):
        b = FakeBackend(ready=True)
        w = self.start(b)
        w.submit(Command.VOLUME_DOWN)
        self.assertTrue(wait_until(lambda: self.log_has("[실행]")))
        self.assertNotIn("prepare", b.calls)
        self.assertNotIn("state", b.calls)

    def test_backend_failure_sends_nothing(self):
        self.logs = []
        keys = Keys()

        def broken():
            raise RuntimeError("uiautomation 없음")
        w = ControlWorker(self.logs.append, backend_factory=broken, press=keys, foreground=lambda: 0)
        w.start()
        w.submit(Command.PLAY_PAUSE)
        w.stop()
        w.join(2)
        self.assertFalse(w.is_alive())
        self.assertEqual(keys.sent, [])
        self.assertTrue(any("준비하지 못했습니다" in m for m in self.logs))

    def test_stop_ends_thread(self):
        w = self.start(FakeBackend())
        w.stop()
        w.join(2)
        self.assertFalse(w.is_alive())


if __name__ == "__main__":
    unittest.main()
