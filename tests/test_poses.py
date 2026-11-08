"""2단계 자동 테스트: 가짜 손 좌표로 손바닥/손등, 펴진 손가락, 검지·엄지 방향 계산 확인 (웹캠 없음).

가짜 손은 '손목 기준 손 좌표'로 만든 뒤 (필요하면 좌우 뒤집기) -> 회전 -> 화면 위치로 옮깁니다.
손 좌표: 손가락이 위(-y), 엄지가 왼쪽(-x). 이 모양 그대로 화면에 두면
'오른손 손바닥이 카메라를 향한 모습'(거울 화면 기준)입니다.
"""
import math
import unittest

from gesture_demo.common import Hand
from gesture_demo.poses import BACK, DOWN, LEFT, PALM, RIGHT, SIDE, UP, analyze

ALL = "TIMRP"
MCP = {"I": (-30, -100), "M": (0, -105), "R": (25, -100), "P": (50, -90)}
IDX = {"I": (5, 6, 7, 8), "M": (9, 10, 11, 12), "R": (13, 14, 15, 16), "P": (17, 18, 19, 20)}


def local_hand(extended: str) -> list[tuple[float, float]]:
    pts = [(0.0, 0.0)] * 21
    pts[1] = (-30, -20)
    if "T" in extended:   # 엄지를 바깥(엄지 쪽)으로 벌림
        pts[2], pts[3], pts[4] = (-55, -45), (-85, -55), (-115, -60)
    else:                 # 엄지를 손바닥 쪽으로 접음
        pts[2], pts[3], pts[4] = (-50, -45), (-35, -70), (0, -80)
    for f, (mx, my) in MCP.items():
        a, b, c, d = IDX[f]
        offs = (0, -50, -80, -105) if f in extended else (0, -30, -15, 10)
        for i, oy in zip((a, b, c, d), offs):
            pts[i] = (mx, my + oy)
    return pts


def make(extended=ALL, label="Right", flip=False, rot=0.0, cx=320, cy=300) -> Hand:
    """flip=True: 좌우 뒤집기(손을 뒤집은 모양). rot: 화면에서 시계 반대 방향 회전 각도(도)."""
    t = math.radians(-rot)  # 화면 y가 아래로 증가하므로 부호 반전
    out = []
    for x, y in local_hand(extended):
        if flip:
            x = -x
        out.append((cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)))
    return Hand(label=label, score=0.95, landmarks=out)


class FacingTest(unittest.TestCase):
    def test_right_palm_and_back(self):
        self.assertEqual(analyze(make(label="Right")).facing, PALM)
        self.assertEqual(analyze(make(label="Right", flip=True)).facing, BACK)

    def test_left_palm_and_back(self):
        self.assertEqual(analyze(make(label="Left", flip=True)).facing, PALM)
        self.assertEqual(analyze(make(label="Left")).facing, BACK)

    def test_rotation_keeps_facing(self):
        for rot in (0, 45, 90, 135, 180, -90):
            with self.subTest(rot=rot):
                self.assertEqual(analyze(make(label="Right", rot=rot)).facing, PALM)
                self.assertEqual(analyze(make(label="Right", flip=True, rot=rot)).facing, BACK)

    def test_edge_on_hand_is_side(self):
        h = make()
        h.landmarks = [(320 + (x - 320) * 0.05, y) for x, y in h.landmarks]  # 손을 옆으로 세운 모습
        self.assertEqual(analyze(h).facing, SIDE)


class FingerTest(unittest.TestCase):
    def test_patterns(self):
        cases = {ALL: "엄지+검지+중지+약지+새끼", "": "모두 접힘", "IM": "검지+중지",
                 "TI": "엄지+검지", "I": "검지", "T": "엄지"}
        for ext, expected in cases.items():
            with self.subTest(ext=ext):
                self.assertEqual(analyze(make(ext)).pattern(), expected)

    def test_rotated_fingers_still_detected(self):
        self.assertEqual(analyze(make("TI", rot=90)).pattern(), "엄지+검지")


class DirectionTest(unittest.TestCase):
    def test_pointing_up_palm(self):            # 검지 위 (손바닥)
        p = analyze(make("I", label="Right"))
        self.assertEqual((p.facing, p.index_dir), (PALM, UP))

    def test_right_gun_back_points_left(self):  # 오른손 총 👈 (손등)
        p = analyze(make("TI", label="Right", flip=True, rot=90))
        self.assertEqual((p.facing, p.pattern(), p.index_dir, p.thumb_dir), (BACK, "엄지+검지", LEFT, UP))

    def test_left_gun_back_points_right(self):  # 왼손 총 👉 (손등)
        p = analyze(make("TI", label="Left", rot=-90))
        self.assertEqual((p.facing, p.pattern(), p.index_dir, p.thumb_dir), (BACK, "엄지+검지", RIGHT, UP))

    def test_thumb_down_palm(self):             # 엄지 아래 (손바닥)
        p = analyze(make("T", label="Right", rot=90))
        self.assertEqual((p.facing, p.pattern(), p.thumb_dir), (PALM, "엄지", DOWN))

    def test_angles(self):
        self.assertAlmostEqual(analyze(make("I")).index_angle, 90, delta=1)
        self.assertAlmostEqual(analyze(make("I", rot=-90)).index_angle, 0, delta=1)


class OkRatioTest(unittest.TestCase):
    def test_thumb_touching_index_is_small(self):
        h = make(ALL)
        h.landmarks[4] = (h.landmarks[8][0] + 3, h.landmarks[8][1] + 3)
        self.assertLess(analyze(h).ok_ratio, 0.1)
        self.assertGreater(analyze(make(ALL)).ok_ratio, 1.0)


if __name__ == "__main__":
    unittest.main()
