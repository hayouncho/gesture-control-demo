"""1단계 확인: 웹캠 + MediaPipe HandLandmarker 로 양손을 검출하고 손마다 왼손/오른손 판별 결과를 보여 줍니다.

제스처 판별·유튜브 키 입력은 하지 않습니다.

실행 (gesture-demo 폴더에서):
    check_hands.bat                 터미널 로그만
    check_hands.bat --preview       미리보기 창도 표시 (테스트용)
    check_hands.bat --camera 1      다른 웹캠 사용
종료: 터미널에서 Ctrl+C  (미리보기 창이 있으면 창을 클릭하고 q / ESC, 또는 창 닫기)
종료하면 이번 실행의 요약(손 개수별 프레임 수, 왼손/오른손 조합, 판별이 바뀐 횟수)을 출력합니다.
"""
from __future__ import annotations

import argparse
import time
from collections import Counter

from gesture_demo import config
from gesture_demo.common import Hand

MAX_READ_FAILS = 30   # 연속으로 이만큼 프레임을 못 읽으면 종료
HAND_KO = {"Left": "왼손", "Right": "오른손"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def side_of(hand: Hand, width: int) -> str:
    """손목이 미리보기(거울) 화면의 어느 쪽에 있는지 = 사용자 기준 왼쪽/오른쪽."""
    return "왼쪽" if hand.landmarks[0][0] < width / 2 else "오른쪽"


def ordered(hands: list[Hand]) -> list[Hand]:
    """사용자 기준 왼쪽에 있는 손부터 (거울 좌표에서 x가 작은 손부터)."""
    return sorted(hands, key=lambda h: h.landmarks[0][0])


def labels_key(hands: list[Hand]) -> tuple[str, ...]:
    """위치 순서대로의 판별 결과. 예: ('Left', 'Right')"""
    return tuple(h.label for h in ordered(hands))


def describe(hands: list[Hand], width: int) -> str:
    if not hands:
        return "손 없음"
    parts = [f"{HAND_KO.get(h.label, h.label)}({h.label} {h.score:.2f}, 화면 {side_of(h, width)})"
             for h in ordered(hands)]
    text = f"손 {len(hands)}개: " + " | ".join(parts)
    if len(hands) == 2 and hands[0].label == hands[1].label:
        text += "  <- 같은 판별 2개 (판별 오류)"
    return text


def combo_name(key: tuple[str, ...]) -> str:
    if not key:
        return "손 없음"
    return " + ".join(HAND_KO.get(k, k) for k in key) + " (화면 왼쪽부터)"


class Summary:
    """실행이 끝날 때 보여 줄 집계."""

    def __init__(self) -> None:
        self.frames = 0
        self.hand_counts: Counter = Counter()     # 손 개수 -> 프레임 수
        self.combos: Counter = Counter()          # 판별 조합 -> 프레임 수
        self.label_flips = 0                      # 손이 1개일 때 판별이 바로 앞 프레임과 달라진 횟수
        self._prev_single: str | None = None

    def add(self, hands: list[Hand]) -> None:
        self.frames += 1
        self.hand_counts[len(hands)] += 1
        self.combos[labels_key(hands)] += 1
        if len(hands) == 1:
            label = hands[0].label
            if self._prev_single is not None and label != self._prev_single:
                self.label_flips += 1
            self._prev_single = label
        else:
            self._prev_single = None

    def report(self, seconds: float) -> str:
        if self.frames == 0:
            return "처리한 프레임이 없습니다."
        fps = self.frames / max(seconds, 1e-6)
        lines = [f"==== 요약: {seconds:.1f}초, {self.frames}프레임, 평균 {fps:.1f} FPS ===="]
        for n in sorted(self.hand_counts):
            c = self.hand_counts[n]
            lines.append(f"  손 {n}개: {c}프레임 ({c / self.frames * 100:.1f}%)")
        lines.append("  판별 조합:")
        for key, c in self.combos.most_common():
            if not key:
                continue
            warn = "  <- 같은 판별 2개 (판별 오류)" if len(key) == 2 and key[0] == key[1] else ""
            lines.append(f"    {combo_name(key)}: {c}프레임{warn}")
        lines.append(f"  손 1개일 때 왼손/오른손 판별이 바뀐 횟수: {self.label_flips}회")
        return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="1단계: 양손 검출 + 왼손/오른손 판별 확인")
    parser.add_argument("--preview", action="store_true", help="미리보기 창 표시 (테스트용)")
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX, help="웹캠 번호 (기본 0)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="손이 보이는 동안 이 간격(초)으로 현재 상태를 다시 출력 (0이면 바뀔 때만)")
    args = parser.parse_args()

    # OpenCV·MediaPipe 는 무거워서 --help 가 빨리 나오도록 여기서 import
    from gesture_demo.camera import Camera, mirror_view
    from gesture_demo.hand_tracker import HandTracker

    print("1단계: 양손 검출 + 왼손/오른손 판별 확인 (제스처 판별·키 입력 없음)")
    print(f"  모델: {config.MODEL_PATH.name}, 최대 손 {config.NUM_HANDS}개, "
          f"신뢰도 기준 검출 {config.MIN_DETECTION_CONFIDENCE} / 존재 {config.MIN_PRESENCE_CONFIDENCE} / "
          f"추적 {config.MIN_TRACKING_CONFIDENCE}")
    print("  왼손/오른손 = 사용자 본인의 실제 손 기준, '화면 왼쪽/오른쪽' = 사용자 기준 위치")
    print("  종료: Ctrl+C" + (" 또는 미리보기 창에서 q / ESC" if args.preview else ""), flush=True)

    summary = Summary()
    started = time.monotonic()
    with Camera(args.camera, config.FRAME_WIDTH, config.FRAME_HEIGHT) as cam, \
         HandTracker(config.MODEL_PATH, config.NUM_HANDS, config.MIN_DETECTION_CONFIDENCE,
                     config.MIN_PRESENCE_CONFIDENCE, config.MIN_TRACKING_CONFIDENCE) as tracker:
        if args.preview:
            import cv2
            from gesture_demo.overlay import GRAY, GREEN, RED, draw_hand, draw_lines
            cv2.namedWindow(config.WINDOW_NAME)

        log("웹캠과 손 인식 모델 준비 완료")
        started = time.monotonic()
        fails = 0
        last_key: tuple | None = None
        last_print = 0.0
        try:
            while True:
                raw = cam.read()                      # 카메라 원본 (반전 안 함)
                if raw is None:
                    fails += 1
                    if fails >= MAX_READ_FAILS:
                        log("웹캠에서 영상을 계속 받지 못해 종료합니다. 연결 상태를 확인하세요.")
                        break
                    time.sleep(0.01)
                    continue
                fails = 0
                now = time.monotonic()
                width = raw.shape[1]

                # 원본으로 인식 -> label 은 사용자 실제 손, 좌표는 거울 화면 기준
                hands = tracker.detect(raw, int(now * 1000))
                summary.add(hands)

                key = labels_key(hands)
                changed = key != last_key
                periodic = bool(hands) and args.interval > 0 and now - last_print >= args.interval
                if changed or periodic:
                    log(("[변경] " if changed else "       ") + describe(hands, width))
                    last_key, last_print = key, now

                if args.preview:
                    frame = mirror_view(raw)
                    for hand in hands:
                        draw_hand(frame, hand)        # 손목 아래에 "Left 0.97" 처럼 표시
                    elapsed = max(now - started, 1e-6)
                    draw_lines(frame, [
                        (f"hands: {len(hands)}" if hands else "NO HAND", GREEN if hands else RED),
                        (f"FPS {summary.frames / elapsed:4.1f}   q/ESC: quit", GRAY),
                    ])
                    cv2.imshow(config.WINDOW_NAME, frame)
                    k = cv2.waitKey(1) & 0xFF
                    if k in (ord("q"), 27):
                        break
                    if cv2.getWindowProperty(config.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        break
        except KeyboardInterrupt:
            pass
        finally:
            if args.preview:
                cv2.destroyAllWindows()

    print(summary.report(time.monotonic() - started), flush=True)
    log("종료했습니다.")


if __name__ == "__main__":
    main()
