# gesture-control-demo

MediaPipe HandLandmarker로 웹캠 속 두 손을 인식해 유튜브를 제어하는 손 제스처 샘플입니다.
손 모양을 유튜브 단축키(K / L / J / ↑ / ↓)로 바꿔 보냅니다.

## 주요 기능

| 제스처 | 동작 |
|---|---|
| V 사인 1초 유지 (어느 손이든) | 인식 시작 / 종료 |
| OK 사인 | 재생 / 일시정지 (K) |
| 왼손 총 👉 (손등이 보이게, 엄지+검지) | 10초 앞으로 (L) |
| 오른손 총 👈 (손등이 보이게, 엄지+검지) | 10초 뒤로 (J) |
| 검지 위 (손바닥이 보이게), 유지하면 반복 | 볼륨 증가 (↑) |
| 엄지 아래 (손바닥이 보이게), 유지하면 반복 | 볼륨 감소 (↓) |

## 설치

필요 환경: Windows 11, Python 3.14, 웹캠

```powershell
git clone https://github.com/hayouncho/gesture-control-demo.git
cd gesture-control-demo
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_model.py
```

## 실행

```powershell
.\run.bat            # 테스트 모드: 인식된 명령만 출력, 키는 보내지 않음
.\run.bat --live     # 실제 제어 모드: 유튜브 창에 키 전송
```

- 실제 제어 모드는 Edge에서 유튜브 **영상 재생 페이지 하나**를 열어 두고, 입력기를 영문 상태로 둔 뒤 실행합니다.
- 실행 후 V 사인을 1초 유지해야 인식이 시작됩니다.
- `--preview`를 붙이면 손 인식 미리보기 창이 열립니다. 종료는 터미널에서 Ctrl+C.
