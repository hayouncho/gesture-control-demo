# gesture-control-demo — 손 제스처로 유튜브 제어 (팀 통합 경량 샘플)

컴퓨터비전 1조 「실시간 손 제스처 인식 기반 동영상 제어 시스템」의 **중간 시연용 통합 샘플**입니다.
웹캠으로 두 손을 인식하고, 정해진 손 모양을 유튜브 단축키(K / L / J / ↑ / ↓)로 바꿔 보냅니다.
별도 GUI 없이 터미널 로그로 인식 상태와 명령 실행 결과를 보여 줍니다.

> 최종 완성본이 아니라 현재 구현 상황과 핵심 기능을 보여 주기 위한 샘플입니다.
> 동작 확인은 작성자 PC(Windows 11, Edge) 기준입니다. 아래 [검증 범위와 제약사항](#8-검증-범위와-알려진-제약사항) 참고.

---

## 1. 제스처와 기능

| 손 동작 | 기능 | 유튜브 키 | 실행 방식 |
|---|---|---|---|
| V 사인(검지+중지) **1초 유지**, 어느 손이든 | 인식 시작 ↔ 종료 | 없음 | 한 번 유지에 한 번만 전환 |
| OK 사인, 어느 손이든 | 재생 / 일시정지 | K | 1회. 다른 자세로 바꿨다가 다시 해야 재실행 |
| **왼손** 총 👉 (손등이 보이게, 엄지+검지) | 10초 앞으로 | L | 1회. 접었다 다시 펴야 재실행 |
| **오른손** 총 👈 (손등이 보이게, 엄지+검지) | 10초 뒤로 | J | 1회. 접었다 다시 펴야 재실행 |
| 검지 위 (손바닥이 보이게) | 볼륨 증가 | ↑ | 0.5초 유지 후 첫 실행, 이후 0.3초마다 반복 |
| 엄지 아래 (손바닥이 보이게) | 볼륨 감소 | ↓ | 0.5초 유지 후 첫 실행, 이후 0.3초마다 반복 |

오작동 방지 규칙
- 인식이 **꺼진 상태(대기)** 에서는 어떤 명령도 실행하지 않습니다. V 사인으로 켜야 합니다.
- 같은 자세가 **3프레임 연속**으로 보여야 자세가 바뀐 것으로 인정합니다 (순간적인 오인식·끊김 무시).
- 시작·종료 전환 직후 0.5초 동안은 명령을 무시합니다.
- **양손이 서로 다른 명령 자세**를 취하면 아무 명령도 실행하지 않습니다 (임시 규칙).
- 인식 중 손이 **10초 동안 보이지 않으면** 자동으로 인식을 종료합니다.

---

## 2. 개발 환경

| 항목 | 버전 |
|---|---|
| OS | Windows 11 (키 입력·창 제어가 Windows 전용) |
| Python | 3.14.0 |
| mediapipe | 1.2.2 (HandLandmarker, Tasks API) |
| opencv-contrib-python | 5.0.0.93 (웹캠 입력·미리보기에만 사용) |
| numpy | 2.5.4 |
| uiautomation | 2.0.29 (유튜브 창 찾기·플레이어 포커스) |
| 브라우저 | Microsoft Edge (Chrome은 아직 검증 전) |
| 손 모델 | `models/hand_landmarker.task` (MediaPipe 공식 배포, 약 7.8MB. 저장소에는 없고 `download_model.py` 로 받음) |
| 기타 | 웹캠 1대, 인터넷 연결(설치·모델 다운로드 때만) |

---

## 3. 설치

사전 준비: Windows 11, [Python 3.14](https://www.python.org/downloads/) (설치할 때 `py` 런처 포함), Git (또는 GitHub에서 ZIP 다운로드)

PowerShell에서 아래 순서대로 실행합니다. 모든 경로는 저장소 폴더 기준 상대경로입니다.

```powershell
# 1) 저장소 받기 (ZIP으로 받았다면 압축을 풀고 그 폴더로 이동)
git clone https://github.com/<계정>/gesture-control-demo.git
cd gesture-control-demo

# 2) 가상환경 만들기 + 패키지 설치
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3) 손 인식 모델 받기 (models\hand_landmarker.task, 약 7.8MB — 저장소에 포함되어 있지 않음)
.\.venv\Scripts\python.exe download_model.py

# 4) 설치 확인: 자동 테스트 (웹캠·유튜브 없이 실행, 모두 OK 여야 함)
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

- `opencv-python` 을 따로 설치하지 마세요. mediapipe 가 설치하는 `opencv-contrib-python` 과 충돌합니다.
- 폴더 경로에 한글·공백이 있어도 동작하도록 만들었습니다 (작성자 PC가 '바탕 화면' 아래에서 개발).
- `.bat` 실행 파일(`run.bat`, `check_hands.bat`, `check_poses.bat`)은 **저장소 폴더 안의 `.venv` 만** 사용합니다.
  2) 단계를 하지 않았거나 3) 모델이 없으면 실행하지 않고 해야 할 명령을 안내합니다.
- 비공개(Private) 저장소이므로 `git clone` 전에 저장소 관리자에게 초대(Collaborator)를 받아야 합니다.
  처음 clone 할 때 GitHub 로그인 창이 뜰 수 있습니다.
- 웹캠이 여러 대면 `--camera 1` 처럼 번호를 지정합니다.

---

## 4. 실행 — 테스트 모드와 실제 제어 모드

```powershell
.\run.bat                 # 테스트 모드 (기본값)
.\run.bat --live          # 실제 제어 모드
.\run.bat --live --preview  # 실제 제어 + 손 인식 미리보기 창 (확인용)
```
종료: 터미널에서 **Ctrl+C** (미리보기 창이 있으면 q / ESC 도 가능)

| | 테스트 모드 (`run.bat`) | 실제 제어 모드 (`run.bat --live`) |
|---|---|---|
| 손 인식·제스처 판별 | 함 | 함 |
| 유튜브 창 찾기·활성화 | **안 함** | 함 |
| 키 입력 | **보내지 않음** | 유튜브 플레이어에 포커스를 확인한 뒤 보냄 |
| 터미널 출력 | `[명령·테스트] 재생/일시정지 -> K 키 (보내지 않음)` | `[명령] … 요청` 다음 줄에 `[실행] …` 또는 `[실패:단계] 원인` |
| 용도 | 제스처가 의도대로 인식되는지 안전하게 확인 | 실제 유튜브 제어 시연 |

실제 제어 모드의 동작
- 유튜브 창이 **맨 앞에 없어도** 명령 때 자동으로 유튜브 창을 앞으로 가져오고 영상 플레이어에 포커스를 줍니다.
- 검색창·재생 위치 바 등 다른 요소에 포커스가 있으면 플레이어로 포커스를 옮긴 뒤 보냅니다.
  (검색창에 글자가 입력되거나, ↑/↓ 가 스크롤·재생 위치 이동으로 처리되는 것을 막기 위함)
- 유튜브를 찾지 못하거나 안전하게 포커스를 줄 수 없으면 **키를 보내지 않고** 원인을 출력합니다.
- 볼륨 반복은 이미 포커스가 유지되고 있으면 창 활성화 단계를 건너뛰고, 이전 명령을 처리 중이면 그 반복은 건너뜁니다 (`[건너뜀]`).

시연 순서 (약 1분)
1. Edge에서 유튜브 **영상 하나만** 열고, 입력기를 영문 상태로 둠 → `.\run.bat --live`
2. V 사인 1초 → `[인식 시작]`
3. OK → 일시정지, OK → 재생
4. 왼손 총 👉 → 10초 앞으로 (접었다 펴서 한 번 더) / 오른손 총 👈 → 10초 뒤로
5. 검지 위 2초 → 볼륨 증가 반복 / 엄지 아래 2초 → 볼륨 감소 반복
6. 메모장을 클릭해 앞에 둔 상태에서 OK → 유튜브가 자동으로 앞으로 와서 실행됨
7. 양손에 서로 다른 제스처 → 아무 명령도 실행되지 않음
8. V 사인 1초 → `[인식 종료]` → 제스처를 해도 반응 없음 → Ctrl+C

---

## 5. 파일 구성

### 실행에 필요한 파일
| 파일 | 역할 |
|---|---|
| `run.py`, `run.bat` | 프로그램 시작점. 카메라 → 손 인식 → 제스처 판별 → (실제 모드) 제어 스레드 |
| `gesture_demo/config.py` | 모든 기준값 (카메라, 신뢰도, 자세 판별 기준, 유지·반복 시간, 자동 종료 시간) |
| `gesture_demo/camera.py` | 웹캠 열기·프레임 읽기, 미리보기용 좌우 반전 |
| `gesture_demo/hand_tracker.py` | **MediaPipe HandLandmarker** 로 양손 검출 → `Hand`(왼손/오른손, 관절 21개 좌표) |
| `gesture_demo/poses.py` | 관절 좌표로 손바닥/손등, 펴진 손가락, 검지·엄지 방향, 엄지-검지 거리 계산 |
| `gesture_demo/gestures.py` | 자세 판별(V/OK/총/검지 위/엄지 아래) + 시작·종료, 1회/반복 실행, 양손 충돌, 자동 종료 |
| `gesture_demo/common.py` | 모듈 사이에서 주고받는 데이터 형식 (`Hand`, `Command`, `Event`), 명령별 키 이름 |
| `gesture_demo/control_worker.py` | 실제 모드의 제어 스레드: 유튜브 대상 자동 선택, 명령 대기열, 볼륨 반복 건너뛰기 |
| `gesture_demo/controller.py` | 키 전송(K/L/J/↑/↓), 전송 전 준비 확인, 1회 명령의 결과 확인 |
| `gesture_demo/youtube_target.py` | Windows UI Automation 으로 유튜브 창/탭 찾기, 창 활성화, 플레이어 포커스 확인 |
| `models/hand_landmarker.task` | MediaPipe 손 랜드마크 모델 (저장소에 없음, `download_model.py` 로 받음) |
| `requirements.txt`, `download_model.py` | 설치용 |
| `.gitignore` | `.venv`, 캐시, 모델 파일, 로그, 개인 설정이 저장소에 올라가지 않게 함 |

### 개발용 진단 도구 (시연에는 필요 없음)
| 파일 | 용도 |
|---|---|
| `check_hands.py`, `check_hands.bat` | 1단계: 양손 검출과 왼손/오른손 판별 확인, 종료 시 요약 |
| `check_poses.py`, `check_poses.bat` | 2단계: 손바닥/손등, 펴진 손가락, 방향 값을 출력해 기준값 조정 (`--preview` 로 화살표 표시) |
| `gesture_demo/overlay.py` | `--preview` 미리보기 창에 관절·글자 그리기 |

### 자동 테스트 (웹캠·유튜브 없이 실행)
| 파일 | 내용 |
|---|---|
| `tests/test_check_hands.py` | 좌표 반전, 1단계 표시·요약, 모델 로딩 |
| `tests/test_poses.py` | 가짜 손 좌표로 손바닥/손등, 손가락 펴짐, 방향 계산 |
| `tests/test_gestures.py` | 제스처 판별, V 전환, 1회·반복 실행, 양손 충돌, 자동 종료 |
| `tests/test_controller.py` | 키 매핑, 포커스 확인(재생 위치 바 거부 포함), 제어 스레드 (가짜 창·가짜 키) |

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

---

## 6. 처리 흐름과 MediaPipe 핵심 함수

```
[메인 스레드: 매 프레임 반복]
 Camera.read()                 웹캠 원본 프레임 (BGR, 반전 안 함)
   └─ HandTracker.detect()     MediaPipe HandLandmarker -> list[Hand] (최대 2손)
        └─ GestureRecognizer.update()   poses.analyze() -> classify() -> 상태 관리 -> list[Event]
             ├─ 테스트 모드: 터미널에 명령 이름과 키만 출력
             └─ 실제 모드:  ControlWorker.submit(명령)  (기다리지 않고 바로 다음 프레임)

[제어 스레드: ControlWorker]
 유튜브 대상 선택 -> (빠른 확인 ready() 또는 전체 준비 prepare()) -> 키 전송 -> 결과 로그
```
창 활성화·포커스에 시간이 걸려도 제어 스레드에서 처리하므로 카메라 인식은 멈추지 않습니다.

### MediaPipe HandLandmarker 사용 부분 (`gesture_demo/hand_tracker.py`)
| 함수 / 값 | 설명 |
|---|---|
| `BaseOptions(model_asset_buffer=...)` | 모델 파일 지정. 경로에 한글(예: 바탕 화면)이 있으면 파일을 못 여는 경우가 있어 내용을 읽어서 넘김 |
| `HandLandmarkerOptions(running_mode=VIDEO, num_hands=2, min_hand_detection_confidence, min_hand_presence_confidence, min_tracking_confidence)` | 연속 프레임 모드, **최대 두 손**, 신뢰도 기준 |
| `HandLandmarker.create_from_options(options)` | 인식기 생성 |
| `mp.Image(image_format=SRGB, data=rgb)` | OpenCV 의 BGR 프레임을 RGB 로 바꿔 MediaPipe 이미지로 감쌈 |
| `detect_for_video(image, timestamp_ms)` | 한 프레임 인식. VIDEO 모드는 타임스탬프가 계속 증가해야 함 |
| `result.hand_landmarks[i]` | 손 i 의 관절 21개 정규화 좌표 (x, y 는 0~1) |
| `result.handedness[i][0].category_name` | `"Left"` / `"Right"` 와 신뢰도 |

좌우 반전 처리: MediaPipe 에는 **카메라 원본**을 넣어야 `Left/Right` 가 사용자의 실제 손과 일치합니다
(반전된 영상을 넣으면 반대로 나옴). 대신 돌려받은 좌표만 `x -> 1 - x` 로 바꿔
"사용자 오른쪽 = 화면 오른쪽" 기준으로 쓰고, 미리보기 화면도 같은 기준으로 반전합니다.

### 자세 계산 (`gesture_demo/poses.py`, 관절 번호는 MediaPipe 기준)
| 값 | 사용한 관절 | 계산 |
|---|---|---|
| 손바닥/손등 | 손목 0, 검지 뿌리 5, 새끼 뿌리 17 | 벡터 0→5 와 0→17 의 외적 부호 + 왼손/오른손. 손을 뒤집으면 부호가 바뀜. 값이 0에 가까우면 옆면 |
| 검지~새끼 펴짐 | 손목 0, 가운데 마디 6/10/14/18, 손끝 8/12/16/20 | 손목~손끝 ÷ 손목~가운데 마디 > 1.1 |
| 엄지 펴짐 | 엄지 뿌리 2, 엄지 끝 4, 새끼 뿌리 17 | 엄지 끝~새끼 뿌리 ÷ 엄지 뿌리~새끼 뿌리 > 1.2 |
| 검지 / 엄지 방향 | 5→8 / 2→4 | 각도로 위·아래·왼쪽·오른쪽 판단 |
| OK | 엄지 끝 4, 검지 끝 8 | 두 점 거리 ÷ 손바닥 크기(0→9) ≤ 0.35 + 중지·약지·새끼 펴짐 |

거리는 모두 손바닥 크기(손목~중지 뿌리)로 나누어, 카메라와의 거리가 달라도 같은 기준을 씁니다.

---

## 7. 팀원 코드 재사용

| 출처 | 재사용한 부분 |
|---|---|
| 조하연 개인 샘플 | `camera.py`, `hand_tracker.py`, `common.py`, `overlay.py` (그대로), `gestures.py` 의 손별 상태·V 전환·자동 종료 구조, `controller.py`·`youtube_target.py` (Edge·Chrome 으로 축소, 빠른 포커스 확인·슬라이더 포커스 거부 추가), `workers.py` 의 제어 스레드 구조 |
| 고지혁 샘플 | OK 사인을 엄지 끝~검지 끝 거리로 판별하는 방식, 유지해도 한 번만 실행하는 규칙, 터미널 중심 표시 |
| 송준섭 샘플 | 손가락 펴짐 비율 판별 아이디어, 인식 ON/OFF 개념 |

---

## 8. 검증 범위와 알려진 제약사항

작성자 PC(Windows 11, Edge)에서 확인한 것
- 양손 동시 검출, 손바닥·손등 모두 왼손/오른손 판별
- V / OK / 왼손 총 / 오른손 총 / 검지 위 / 엄지 아래 인식과 명령 출력 (테스트 모드)
- 실제 제어: 유튜브가 맨 앞일 때, 다른 창이 맨 앞일 때, 유튜브 검색창에 커서가 있을 때
- 재생 위치 바에 포커스가 있을 때 검지 위 → 영상이 이동하지 않고 볼륨만 조절됨 (수정 후 확인)

아직 검증하지 않은 것
- 다른 팀원 PC, 다른 웹캠, 어두운 조명, 먼 거리
- Chrome (웹 접근성 설정이 필요할 수 있음: `chrome://accessibility`), 유튜브 설치형 앱 창
- **한글 입력 상태**에서의 키 입력 (시연 때는 영문 상태 권장)
- 장시간 연속 실행

알려진 제약
- Windows 전용 (키 입력과 창 제어에 Windows API·UI Automation 사용).
- 유튜브가 **여러 개** 열려 있고 그중 맨 앞에 있는 것이 없으면 대상을 고르지 않고 키를 보내지 않습니다. 시연 때는 하나만 열어 두세요.
- 영상 재생 페이지(`youtube.com/watch`)만 제어합니다. 홈·검색 결과·쇼츠는 제외.
- 엄지 아래 제스처는 가끔 인식이 끊겼다가 다시 잡힙니다. 끊기면 볼륨 반복은 0.5초 대기부터 다시 시작합니다.
- 총 모양은 손등 + 엄지·검지만 펴짐으로 판별하며, 검지가 가리키는 방향은 아직 조건에 넣지 않았습니다.
- 손을 0.5초 넘게 화면 밖으로 뺐다가 같은 자세로 다시 넣으면 새 동작으로 보고 다시 실행합니다.
- Windows 포커스 보호 때문에 창 활성화가 거부되면 그 명령은 보내지 않습니다 (로그에 원인 표시).
- 양손 서로 다른 명령 = 실행 안 함, 자동 종료 10초 등 일부 규칙과 기준값은 임시값이며 `config.py` 에서 바꿀 수 있습니다.
