"""1단계 자동 테스트 (웹캠 없이 실행).

    python -m unittest discover -s tests -t .
"""
import unittest

import numpy as np

from check_hands import Summary, describe, labels_key
from gesture_demo import config
from gesture_demo.common import Hand
from gesture_demo.hand_tracker import HandTracker, to_view_coords

W, H = 640, 480


def hand_at(view_x: float, label: str) -> Hand:
    """거울 화면 x 위치에 손목이 있는 가짜 손."""
    return Hand(label=label, score=0.95, landmarks=[(view_x, 240.0)] * 21)


class MirrorTest(unittest.TestCase):
    def test_x_is_flipped_y_is_kept(self):
        self.assertEqual(to_view_coords([(0.2, 0.3)], W, H), [(0.8 * W, 0.3 * H)])


class DescribeTest(unittest.TestCase):
    def test_hands_listed_from_user_left(self):
        hands = [hand_at(500, "Right"), hand_at(100, "Left")]
        self.assertEqual(labels_key(hands), ("Left", "Right"))
        text = describe(hands, W)
        self.assertLess(text.index("왼손"), text.index("오른손"))
        self.assertNotIn("판별 오류", text)

    def test_same_label_twice_is_flagged(self):
        self.assertIn("판별 오류", describe([hand_at(100, "Right"), hand_at(500, "Right")], W))

    def test_no_hand(self):
        self.assertEqual(describe([], W), "손 없음")


class SummaryTest(unittest.TestCase):
    def test_counts_and_single_hand_flips(self):
        s = Summary()
        for label in ["Left", "Left", "Right", "Right", "Left"]:
            s.add([hand_at(100, label)])
        s.add([])
        s.add([hand_at(100, "Left"), hand_at(500, "Right")])
        self.assertEqual(s.frames, 7)
        self.assertEqual(s.hand_counts[1], 5)
        self.assertEqual(s.label_flips, 2)
        self.assertIn("왼손 + 오른손", s.report(1.0))


@unittest.skipUnless(config.MODEL_PATH.exists(), "모델 파일 없음")
class TrackerTest(unittest.TestCase):
    def test_model_loads_and_blank_frame_has_no_hands(self):
        with HandTracker(config.MODEL_PATH, config.NUM_HANDS) as tracker:
            blank = np.zeros((H, W, 3), dtype=np.uint8)
            self.assertEqual(tracker.detect(blank, 0), [])
            self.assertEqual(tracker.detect(blank, 0), [])  # 같은 시각이 와도 타임스탬프 자동 증가


if __name__ == "__main__":
    unittest.main()
