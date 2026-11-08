"""2단계 확인: 손 모양 진단 도구.

손마다 손바닥/손등 방향, 펴진 손가락, 검지·엄지 방향, 엄지-검지 끝 거리를 터미널에 보여 줍니다.
V, OK, 총, 검지 위, 엄지 아래 제스처를 할 때 각 값이 어떻게 나오는지 확인하는 용도입니다.
제스처 판정·명령 실행·유튜브 제어는 하지 않습니다.

실행 (gesture-demo 폴더에서):
    check_poses.bat                 터미널 로그만
    check_poses.bat --preview       미리보기 창도 표시 (손가락 방향 화살표 포함)
    check_poses.bat --interval 0.5  손이 보이는 동안 0.5초마다 현재 값 출력 (기본 1초)
종료: 터미널에서 Ctrl+C  (미리보기 창에서는 q / ESC)
"""
from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict

from check_hands import HAND_KO, MAX_READ_FAILS, log, ordered
from gesture_demo import config
from gesture_demo.poses import DIR_EN, FACING_EN, FINGER_NAMES, HandPose, analyze

CHANGE_MIN_GAP = 0.25   # 같은 손의 '바뀜' 출력 최소 간격(초) — 깜빡임으로 터미널이 넘치지 않게


def hand_keys(hands) -> list[str]:
    """같은 판별이 두 번 나오면 두 번째에 #2 를 붙임 (예: Right, Right#2)."""
    keys, seen = [], Counter()
    for h in hands:
        seen[h.label] += 1
        keys.append(h.label if seen[h.label] == 1 else f"{h.label}#{seen[h.label]}")
    return keys


def format_pose(key: str, p: HandPose) -> str:
    name = HAND_KO.get(p.label, p.label) + (key[len(p.label):] if key != p.label else "")
    return (f"{name} | {p.facing}({p.cross:+.2f}) | 펴짐: {p.pattern()} | "
            f"검지 {p.index_dir}({round(p.index_angle):+d}°) | 엄지 {p.thumb_dir}({round(p.thumb_angle):+d}°) | "
            f"엄지-검지 끝 {p.ok_ratio:.2f}")


def format_ratios(p: HandPose) -> str:
    return "      비율: " + " ".join(f"{n} {p.ratios[n]:.2f}" for n in FINGER_NAMES)


def finger_code(p: HandPose) -> str:
    """미리보기용 영문: 펴진 손가락 T I M R P, 접힌 손가락 '-'."""
    return "".join(c if p.extended[n] else "-" for c, n in zip("TIMRP", FINGER_NAMES))


class PoseSummary:
    def __init__(self) -> None:
        self.frames = 0
        self.per_hand: dict[str, dict] = defaultdict(lambda: {
            "frames": 0, "facing": Counter(), "pattern": Counter(), "index": Counter(), "thumb": Counter(),
            "changes": 0, "last": None})

    def add(self, keyed: list[tuple[str, HandPose]]) -> None:
        self.frames += 1
        for key, p in keyed:
            s = self.per_hand[key]
            s["frames"] += 1
            s["facing"][p.facing] += 1
            s["pattern"][p.pattern()] += 1
            s["index"][p.index_dir] += 1
            s["thumb"][p.thumb_dir] += 1
            sig = p.signature()
            if s["last"] is not None and sig != s["last"]:
                s["changes"] += 1
            s["last"] = sig

    @staticmethod
    def _top(counter: Counter, total: int, n: int = 3) -> str:
        return ", ".join(f"{k} {c / total * 100:.0f}%" for k, c in counter.most_common(n))

    def report(self, seconds: float) -> str:
        if self.frames == 0:
            return "처리한 프레임이 없습니다."
        lines = [f"==== 요약: {seconds:.1f}초, {self.frames}프레임, 평균 {self.frames / max(seconds, 1e-6):.1f} FPS ===="]
        for key in sorted(self.per_hand):
            s = self.per_hand[key]
            t = s["frames"]
            label = key.split("#")[0]
            lines.append(f"  {HAND_KO.get(label, label)}{key[len(label):]}: {t}프레임 보임, "
                         f"모양·방향 값이 바뀐 횟수 {s['changes']}회")
            lines.append(f"    방향: {self._top(s['facing'], t)}")
            lines.append(f"    펴진 손가락: {self._top(s['pattern'], t)}")
            lines.append(f"    검지 방향: {self._top(s['index'], t)} / 엄지 방향: {self._top(s['thumb'], t)}")
        return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="2단계: 손 모양 진단 (판정·명령 없음)")
    parser.add_argument("--preview", action="store_true", help="미리보기 창 표시 (테스트용)")
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX, help="웹캠 번호 (기본 0)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="손이 보이는 동안 이 간격(초)으로 현재 값을 다시 출력 (0이면 바뀔 때만)")
    args = parser.parse_args()

    from gesture_demo.camera import Camera, mirror_view
    from gesture_demo.hand_tracker import HandTracker

    print("2단계: 손 모양 진단 (제스처 판정·키 입력 없음)")
    print(f"  펴짐 기준: 검지~새끼 비율 > {config.FINGER_EXTENDED_RATIO}, 엄지 비율 > {config.THUMB_EXTENDED_RATIO}"
          f" / 방향 값 크기 < {config.FACING_MIN_CROSS} 이면 옆면")
    print("  방향 각도: 0°=사용자 오른쪽, +90°=위, ±180°=왼쪽, -90°=아래")
    print("  종료: Ctrl+C" + (" 또는 미리보기 창에서 q / ESC" if args.preview else ""), flush=True)

    summary = PoseSummary()
    with Camera(args.camera, config.FRAME_WIDTH, config.FRAME_HEIGHT) as cam, \
         HandTracker(config.MODEL_PATH, config.NUM_HANDS, config.MIN_DETECTION_CONFIDENCE,
                     config.MIN_PRESENCE_CONFIDENCE, config.MIN_TRACKING_CONFIDENCE) as tracker:
        if args.preview:
            import cv2
            from gesture_demo.overlay import CYAN, GRAY, GREEN, RED, YELLOW, draw_hand, draw_lines, put_text
            cv2.namedWindow(config.WINDOW_NAME)

        log("웹캠과 손 인식 모델 준비 완료")
        started = time.monotonic()
        fails = 0
        last_sig: dict[str, tuple] = {}
        last_print: dict[str, float] = {}
        had_hands = False
        try:
            while True:
                raw = cam.read()
                if raw is None:
                    fails += 1
                    if fails >= MAX_READ_FAILS:
                        log("웹캠에서 영상을 계속 받지 못해 종료합니다. 연결 상태를 확인하세요.")
                        break
                    time.sleep(0.01)
                    continue
                fails = 0
                now = time.monotonic()

                hands = ordered(tracker.detect(raw, int(now * 1000)))   # 사용자 기준 왼쪽 손부터
                keyed = [(k, analyze(h)) for k, h in zip(hand_keys(hands), hands)]
                summary.add(keyed)

                if not hands and had_hands:
                    log("손 없음")
                    last_sig.clear()
                had_hands = bool(hands)
                for key, p in keyed:
                    sig = p.signature()
                    gap = now - last_print.get(key, -1e9)
                    changed = sig != last_sig.get(key) and gap >= CHANGE_MIN_GAP
                    periodic = args.interval > 0 and gap >= args.interval
                    if changed or periodic:
                        log(("[바뀜] " if changed else "       ") + format_pose(key, p))
                        print(format_ratios(p), flush=True)
                        last_sig[key], last_print[key] = sig, now

                if args.preview:
                    frame = mirror_view(raw)
                    for hand, (key, p) in zip(hands, keyed):
                        draw_hand(frame, hand, f"{FACING_EN[p.facing]}{p.cross:+.2f} {finger_code(p)}")
                        lm = [(int(x), int(y)) for x, y in hand.landmarks]
                        cv2.arrowedLine(frame, lm[5], lm[8], YELLOW, 3, tipLength=0.3)   # 검지 방향
                        cv2.arrowedLine(frame, lm[2], lm[4], CYAN, 3, tipLength=0.3)     # 엄지 방향
                        x, y = lm[0]
                        put_text(frame, f"idx {DIR_EN[p.index_dir]}  thumb {DIR_EN[p.thumb_dir]}  ok {p.ok_ratio:.2f}",
                                 (x - 40, min(frame.shape[0] - 10, y + 52)), CYAN)
                    elapsed = max(now - started, 1e-6)
                    draw_lines(frame, [
                        (f"hands: {len(hands)}" if hands else "NO HAND", GREEN if hands else RED),
                        ("yellow: index  cyan: thumb", GRAY),
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
