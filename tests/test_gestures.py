"""3~4단계 자동 테스트: 제스처 판별 + 인식 상태 관리 (웹캠 없음, 가짜 손 좌표 + 가짜 시각).

    python -m unittest discover -s tests -t .
"""
import unittest

from gesture_demo import config as C
from gesture_demo.common import Command, EventType
from gesture_demo.gestures import Gesture, GestureRecognizer, classify
from gesture_demo.poses import analyze
from tests.test_poses import ALL, make

DT = 1 / 30   # 30 FPS


# ---------------------------------------------------------------- 가짜 자세 (cx: 화면 위치)
def v_sign(label="Right", cx=480):
    return make("IM", label=label, flip=(label == "Left"), cx=cx)


def ok_sign(label="Right", cx=480):
    h = make(ALL, label=label, flip=(label == "Left"), cx=cx)
    h.landmarks[4] = (h.landmarks[8][0] + 3, h.landmarks[8][1] + 3)   # 엄지 끝을 검지 끝에 붙임
    return h


def gun(label):  # 손등이 보이는 총: 왼손 👉, 오른손 👈
    return make("TI", label="Left", rot=-90, cx=160) if label == "Left" else \
        make("TI", label="Right", flip=True, rot=90, cx=480)


def point_up(label="Right", cx=480):   # 손바닥
    return make("I", label=label, flip=(label == "Left"), cx=cx)


def thumb_down(label="Right", cx=480):  # 손바닥
    return make("T", label=label, flip=(label == "Left"), rot=(90 if label == "Right" else -90), cx=cx)


def open_palm(label="Right", cx=480):
    return make(ALL, label=label, flip=(label == "Left"), cx=cx)


class Runner:
    def __init__(self):
        self.rec = GestureRecognizer()
        self.t = 0.0
        self.events = []   # (시각, Event)

    def feed(self, hands_fn, seconds):
        """seconds 동안 매 프레임 hands_fn() 의 손 목록을 넣음."""
        for _ in range(round(seconds / DT)):
            for ev in self.rec.update(hands_fn(), self.t):
                self.events.append((self.t, ev))
            self.t += DT

    def activate(self):
        self.feed(lambda: [v_sign()], C.ACTIVATION_HOLD_SEC + 0.2)
        self.feed(lambda: [open_palm()], C.TOGGLE_BLOCK_SEC + 0.2)
        assert self.rec.active
        self.events.clear()

    def commands(self):
        return [ev.command for _, ev in self.events if ev.type == EventType.COMMAND]

    def times(self, cmd):
        return [t for t, ev in self.events if ev.type == EventType.COMMAND and ev.command == cmd]

    def of_type(self, kind):
        return [ev for _, ev in self.events if ev.type == kind]


class ClassifyTest(unittest.TestCase):
    def test_each_gesture(self):
        cases = [(v_sign(), Gesture.V), (v_sign("Left"), Gesture.V), (ok_sign(), Gesture.OK),
                 (gun("Left"), Gesture.GUN), (gun("Right"), Gesture.GUN),
                 (point_up(), Gesture.POINT_UP), (point_up("Left"), Gesture.POINT_UP),
                 (thumb_down(), Gesture.THUMB_DOWN), (thumb_down("Left"), Gesture.THUMB_DOWN),
                 (open_palm(), None), (make(""), None)]
        for hand, expected in cases:
            with self.subTest(expected=expected, label=hand.label):
                self.assertEqual(classify(analyze(hand)), expected)

    def test_wrong_facing_or_direction_is_not_a_gesture(self):
        self.assertIsNone(classify(analyze(make("TI", label="Right", rot=90))))           # 총인데 손바닥
        self.assertIsNone(classify(analyze(make("I", label="Right", flip=True))))         # 검지 위인데 손등
        self.assertIsNone(classify(analyze(make("I", label="Right", rot=180))))           # 검지 아래
        self.assertIsNone(classify(analyze(make("T", label="Right", rot=-90))))           # 엄지 위


class ActivationTest(unittest.TestCase):
    def test_nothing_runs_while_inactive(self):
        r = Runner()
        for fn in (ok_sign, lambda: gun("Left"), lambda: gun("Right"), point_up, thumb_down, open_palm):
            r.feed(lambda: [fn()], 1.5)
            r.feed(lambda: [open_palm()], 0.3)
        self.assertFalse(r.rec.active)
        self.assertEqual(r.commands(), [])

    def test_holding_v_toggles_once(self):
        r = Runner()
        r.feed(lambda: [v_sign()], 4.0)
        self.assertEqual(len(r.of_type(EventType.ACTIVATED)), 1)
        self.assertEqual(r.of_type(EventType.DEACTIVATED), [])
        self.assertTrue(r.rec.active)

    def test_v_toggle_time_and_release_then_toggle_off(self):
        r = Runner()
        r.feed(lambda: [v_sign()], 0.9)
        self.assertFalse(r.rec.active)                    # 1초 전에는 전환 안 됨
        r.feed(lambda: [v_sign()], 0.3)
        self.assertTrue(r.rec.active)
        r.feed(lambda: [open_palm()], 0.5)
        r.feed(lambda: [v_sign()], 1.2)
        self.assertFalse(r.rec.active)
        self.assertEqual(len(r.of_type(EventType.DEACTIVATED)), 1)

    def test_v_flicker_does_not_retoggle(self):
        r = Runner()
        r.feed(lambda: [v_sign()], 1.2)
        for _ in range(5):                                # 1~2프레임 끊김 반복
            r.feed(lambda: [open_palm()], 2 * DT)
            r.feed(lambda: [v_sign()], 0.5)
        r.feed(lambda: [v_sign()], 1.5)
        self.assertEqual(len(r.of_type(EventType.ACTIVATED)), 1)
        self.assertEqual(r.of_type(EventType.DEACTIVATED), [])

    def test_two_hands_v_toggle_once(self):
        r = Runner()
        r.feed(lambda: [v_sign("Left", cx=160), v_sign("Right")], 3.0)
        self.assertEqual(len(r.of_type(EventType.ACTIVATED)), 1)
        self.assertTrue(r.rec.active)

    def test_auto_deactivate_after_10s_without_hands(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [], C.AUTO_DEACTIVATE_SEC - 0.5)
        self.assertTrue(r.rec.active)
        r.feed(lambda: [], 0.6)
        self.assertFalse(r.rec.active)
        self.assertEqual(len(r.of_type(EventType.DEACTIVATED)), 1)

    def test_no_auto_deactivate_while_hand_visible(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [open_palm()], C.AUTO_DEACTIVATE_SEC + 2)
        self.assertTrue(r.rec.active)


class OneShotTest(unittest.TestCase):
    def test_ok_held_runs_once(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [ok_sign()], 3.0)
        self.assertEqual(r.commands(), [Command.PLAY_PAUSE])

    def test_guns_run_once_each_with_right_keys(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [gun("Left")], 2.0)
        r.feed(lambda: [open_palm(cx=160)], 0.3)
        r.feed(lambda: [gun("Right")], 2.0)
        self.assertEqual(r.commands(), [Command.SEEK_FORWARD_10, Command.SEEK_BACK_10])

    def test_rerun_after_changing_pose(self):
        r = Runner()
        r.activate()
        for _ in range(3):
            r.feed(lambda: [gun("Right")], 0.5)
            r.feed(lambda: [make("", label="Right", flip=True, rot=90, cx=480)], 0.3)  # 접기
        self.assertEqual(r.commands(), [Command.SEEK_BACK_10] * 3)

    def test_short_flicker_or_dropout_does_not_rerun(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [ok_sign()], 0.5)
        for _ in range(4):
            r.feed(lambda: [open_palm()], 2 * DT)   # 2프레임 다른 자세
            r.feed(lambda: [ok_sign()], 0.3)
            r.feed(lambda: [], 0.2)                 # 0.2초 손 놓침
            r.feed(lambda: [ok_sign()], 0.3)
        self.assertEqual(r.commands(), [Command.PLAY_PAUSE])

    def test_pose_held_from_before_activation_does_not_fire(self):
        r = Runner()
        r.feed(lambda: [v_sign("Left", cx=160), ok_sign()], 1.5)   # 오른손 OK 를 든 채 시작
        r.feed(lambda: [ok_sign()], 2.0)
        self.assertTrue(r.rec.active)
        self.assertEqual(r.commands(), [])

    def test_command_right_after_toggle_is_ignored(self):
        r = Runner()
        r.feed(lambda: [v_sign()], 1.1)
        self.assertTrue(r.rec.active)
        r.feed(lambda: [ok_sign()], 1.0)            # 전환 직후 0.5초 안에 OK 확정
        self.assertEqual(r.commands(), [])


class RepeatTest(unittest.TestCase):
    def _hold(self, fn, seconds):
        r = Runner()
        r.activate()
        start = r.t
        r.feed(lambda: [fn()], seconds)
        return r, start

    def test_volume_up_timing(self):
        r, start = self._hold(point_up, 1.55)
        times = [round(t - start, 2) for t in r.times(Command.VOLUME_UP)]
        expected = [C.VOLUME_HOLD_SEC + i * C.VOLUME_REPEAT_SEC for i in range(4)]   # 0.5 0.8 1.1 1.4
        self.assertEqual(len(times), len(expected), times)
        for got, want in zip(times, expected):
            self.assertAlmostEqual(got, want, delta=DT + 1e-6)

    def test_volume_down_repeats_too(self):
        r, _ = self._hold(thumb_down, 1.55)
        self.assertEqual(r.commands(), [Command.VOLUME_DOWN] * 4)

    def test_short_hold_does_nothing(self):
        r, _ = self._hold(point_up, 0.4)
        self.assertEqual(r.commands(), [])

    def test_repeat_stops_when_released(self):
        r, _ = self._hold(point_up, 1.0)
        n = len(r.commands())
        r.feed(lambda: [open_palm()], 1.0)
        self.assertEqual(len(r.commands()), n)


class ConflictTest(unittest.TestCase):
    def test_different_commands_on_two_hands_do_nothing(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [gun("Left"), ok_sign()], 2.0)
        self.assertEqual(r.commands(), [])
        self.assertEqual(len(r.of_type(EventType.IGNORED)), 1)

    def test_volume_up_and_down_together_do_nothing(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [point_up("Left", cx=160), thumb_down()], 2.0)
        self.assertEqual(r.commands(), [])

    def test_conflict_pauses_repeat_and_restarts_wait(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [point_up("Left", cx=160)], 0.6)                      # 1회 실행
        r.feed(lambda: [point_up("Left", cx=160), ok_sign()], 1.0)           # 충돌 중 정지
        self.assertEqual(r.commands(), [Command.VOLUME_UP])
        r.feed(lambda: [point_up("Left", cx=160), open_palm()], 0.45)        # 충돌 끝 -> 0.5초 대기부터
        self.assertEqual(r.commands(), [Command.VOLUME_UP])
        r.feed(lambda: [point_up("Left", cx=160), open_palm()], 0.2)          # (OK 해제 확정 3프레임 + 0.5초) 이후
        self.assertEqual(r.commands(), [Command.VOLUME_UP] * 2)

    def test_same_command_on_two_hands_is_not_doubled(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [point_up("Left", cx=160), point_up()], 1.55)
        self.assertEqual(r.commands(), [Command.VOLUME_UP] * 4)

    def test_v_on_other_hand_is_not_a_conflict(self):
        r = Runner()
        r.activate()
        r.feed(lambda: [v_sign("Left", cx=160), gun("Right")], 0.5)
        self.assertEqual(r.commands(), [Command.SEEK_BACK_10])


if __name__ == "__main__":
    unittest.main()
