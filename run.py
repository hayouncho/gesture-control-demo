"""손 제스처 동영상 제어 — 통합 샘플.

    run.bat              테스트 모드(기본): 인식 상태와 명령만 출력, 키는 보내지 않음
    run.bat --live       실제 모드: 유튜브 창을 찾아 활성화 + 플레이어 포커스 확인 후 단축키 전송
    run.bat --preview    미리보기 창도 표시 (테스트용, --live 와 함께 써도 됨)
    run.bat --camera 1   다른 웹캠 사용
종료: 터미널에서 Ctrl+C  (미리보기 창에서는 q / ESC)

흐름 (한 프레임마다)
    Camera.read() -> HandTracker.detect() -> GestureRecognizer.update() -> 터미널 출력
      원본 프레임      손 목록 list[Hand]        이벤트 list[Event]          (--live: ControlWorker.submit)
    유튜브 창 활성화·포커스·키 전송은 ControlWorker 스레드가 처리 -> 카메라 인식은 멈추지 않음
"""
from __future__ import annotations

import argparse
import time

from gesture_demo import config
from gesture_demo.common import COMMAND_KEY, COMMAND_KO, EventType

MAX_READ_FAILS = 30


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def print_banner(live: bool) -> None:
    mode = ("실제 모드 — 명령 때 유튜브 창을 활성화하고 플레이어 포커스를 확인한 뒤 키를 보냅니다"
            if live else "테스트 모드 — 키는 보내지 않고 명령 이름과 대응 키만 출력합니다")
    print(f"""
================ 손 제스처 동영상 제어 (통합 샘플) ================
 {mode}
 [시작/종료]   V 사인 {config.ACTIVATION_HOLD_SEC:g}초 유지 (어느 손이든)
 [재생/정지]   OK 사인                         -> K
 [10초 앞으로] 왼손 총 (손등, 엄지+검지)        -> L
 [10초 뒤로]   오른손 총 (손등, 엄지+검지)      -> J
 [볼륨 증가]   검지 위 (손바닥)                 -> ↑  {config.VOLUME_HOLD_SEC:g}초 후 {config.VOLUME_REPEAT_SEC:g}초마다
 [볼륨 감소]   엄지 아래 (손바닥)               -> ↓  같은 반복
 OK·총은 한 번만 실행 -> 다른 자세로 바꿨다가 다시 해야 재실행
 손이 {config.AUTO_DEACTIVATE_SEC:g}초 동안 안 보이면 인식 자동 종료
 종료: Ctrl+C
===================================================================
""", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="손 제스처 동영상 제어 (통합 샘플)")
    parser.add_argument("--live", action="store_true", help="실제로 유튜브에 키를 보냄 (기본: 테스트 모드)")
    parser.add_argument("--preview", action="store_true", help="미리보기 창 표시 (테스트용)")
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX, help="웹캠 번호 (기본 0)")
    args = parser.parse_args()

    from gesture_demo.camera import Camera, mirror_view
    from gesture_demo.gestures import GestureRecognizer
    from gesture_demo.hand_tracker import HandTracker

    print_banner(args.live)
    recognizer = GestureRecognizer()
    worker = None
    if args.live:
        from gesture_demo.control_worker import ControlWorker
        worker = ControlWorker(log)
        worker.start()   # 유튜브 창 검색은 이 스레드에서 (읽기 전용, 포커스를 바꾸지 않음)

    try:
        with Camera(args.camera, config.FRAME_WIDTH, config.FRAME_HEIGHT) as cam, \
             HandTracker(config.MODEL_PATH, config.NUM_HANDS, config.MIN_DETECTION_CONFIDENCE,
                         config.MIN_PRESENCE_CONFIDENCE, config.MIN_TRACKING_CONFIDENCE) as tracker:
            if args.preview:
                import cv2
                from gesture_demo.overlay import GRAY, GREEN, RED, YELLOW, draw_hand, draw_lines
                cv2.namedWindow(config.WINDOW_NAME)

            log("준비 완료. 현재 상태: 대기 (V 사인 1초로 인식 시작)")
            fails = 0
            last_info: dict[str, str] = {}
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

                    hands = tracker.detect(raw, int(now * 1000))
                    for ev in recognizer.update(hands, now):
                        if ev.type == EventType.COMMAND:
                            key = COMMAND_KEY[ev.command]
                            if worker is None:
                                log(f"[명령·테스트] {COMMAND_KO[ev.command]} -> {key} 키 (보내지 않음)  | {ev.message}")
                            else:
                                log(f"[명령] {COMMAND_KO[ev.command]} -> {key} 키 요청  | {ev.message}")
                                worker.submit(ev.command)   # 실제 처리 결과는 제어 스레드가 출력
                        elif ev.type == EventType.ACTIVATED:
                            log(f"[인식 시작] {ev.message}")
                        elif ev.type == EventType.DEACTIVATED:
                            log(f"[인식 종료] {ev.message}")
                        else:
                            log(f"[무시] {ev.message}")

                    info = recognizer.hand_info
                    if info != last_info:   # 손별 확정 자세가 바뀌었을 때만
                        state = "인식 중" if recognizer.active else "대기"
                        parts = [f"{recognizer._name(k)}: {v}" for k, v in sorted(info.items())]
                        log(f"  ({state}) 자세 " + (" / ".join(parts) if parts else "손 없음"))
                        last_info = dict(info)

                    if args.preview:
                        frame = mirror_view(raw)
                        for key, hand in zip(GestureRecognizer._keys(hands), hands):
                            st = recognizer._states.get(key)
                            draw_hand(frame, hand, st.stable.value if st and st.stable else "-")
                        draw_lines(frame, [
                            ("ACTIVE" if recognizer.active else "IDLE - hold V 1s",
                             GREEN if recognizer.active else YELLOW),
                            ("LIVE (sending keys)" if args.live else "TEST MODE (no keys)",
                             RED if args.live else GRAY),
                            (f"hands: {len(hands)}" if hands else "NO HAND", GREEN if hands else RED),
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
    finally:
        if worker is not None:
            worker.stop()
            worker.join(timeout=3)
    log("종료했습니다.")


if __name__ == "__main__":
    main()
