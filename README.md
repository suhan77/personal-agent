# Personal Agent for macOS

SwiftUI 화면과 로컬 Python 에이전트를 하나의 저장소에서 관리합니다. Swift가 `Process`로 Python을 실행하고 표준입출력(JSON Lines)으로 요청합니다. FastAPI와 별도 웹 서버는 필요하지 않습니다.

## 준비 및 실행

1. Apple Silicon Mac에 Xcode와 uv를 설치합니다.
2. 저장소의 `agent` 폴더에서 Python 환경을 준비합니다.

   ```bash
   cd agent
   uv sync
   cp .env.example .env
   ```

3. `agent/.env`의 `MODEL_DIR`를 확인합니다. 기본값은 `/Volumes/sh_disk/model`이며 그 아래 `granite-4.2-3b` 모델 파일이 있어야 합니다.
4. `PersonalAgent/PersonalAgent.xcodeproj`를 Xcode에서 열고 `PersonalAgent` / `My Mac`으로 실행합니다.

앱을 실행하면 백그라운드에서 Python 워커, 라이브러리, 모델, 그래프 및 체크포인트 저장소를 미리 준비합니다. 따라서 첫 메시지에서 모델을 메모리에 올리는 대기 시간은 발생하지 않습니다. 초기화 중 입력된 첫 메시지는 워커가 준비될 때까지 대기한 뒤 처리됩니다. 이후에는 같은 Python 프로세스와 모델을 재사용합니다. 오류는 대화창에 표시하며 자세한 로그는 Xcode 콘솔에서 확인합니다. 10분 동안 응답이 없으면 프로세스를 종료하며 다음 요청에서 다시 시작합니다.

## 구조

```text
personal-agent/
├── PersonalAgent/                 # 기존 SwiftUI macOS 앱
│   ├── PersonalAgent.xcodeproj
│   └── PersonalAgent/
│       ├── App/
│       ├── Features/              # 채팅 / 대화 목록
│       ├── Models/
│       └── Services/AgentProcessService.swift
└── agent/
    ├── pyproject.toml
    ├── uv.lock
    └── src/personal_agent/
        ├── __main__.py            # JSON Lines 요청 루프
        ├── chat_service.py        # LangGraph 실행
        ├── config/
        ├── schemas/
        └── modules/
            ├── langchain/         # 실제 Hugging Face 모델 로딩
            └── langgraph/         # 이력 요약, 생성, SQLite 체크포인트
```

`personal_agent` 프로젝트의 Granite 로딩, 프롬프트, 생성 설정, LangGraph, LangMem 요약 및 SQLite 체크포인트 코드를 가져왔습니다. API 라우터, FastAPI, Uvicorn 및 현재 에이전트에서 사용하지 않는 도구 의존성은 포함하지 않습니다.

Swift는 대화 UUID와 새 메시지를 전송하고 Python이 해당 UUID의 이력을 관리합니다. 새 대화는 별도 UUID를 사용합니다. 화면의 대화 목록은 아직 메모리에만 유지되므로 앱을 다시 열었을 때 이전 대화를 복원하는 기능은 없습니다. Python 체크포인트는 디스크에 유지됩니다.

개발 실행 시 Swift 소스 경로를 기준으로 같은 저장소의 `agent/.venv/bin/python`을 찾습니다. 필요하면 Xcode Scheme 환경 변수 `PERSONAL_AGENT_DIR`(agent 폴더 절대 경로), `PERSONAL_AGENT_PYTHON`(Python 실행 파일 절대 경로)으로 변경할 수 있습니다. 현재는 개발용 로컬 환경이며 Python 런타임·모델을 포함한 배포용 앱 번들 구성은 별도 작업입니다.

프로토콜 및 설정은 [agent/README.md](agent/README.md)를 참고하세요.

## 검증

```bash
cd agent
uv run python -m unittest discover -s tests
```

저장소 루트에서 macOS 앱 빌드:

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project PersonalAgent/PersonalAgent.xcodeproj \
  -scheme PersonalAgent -configuration Debug \
  -derivedDataPath /tmp/personal-agent-derived build CODE_SIGNING_ALLOWED=NO
```

Xcode 실행 시 앱용 Metal 검사 및 라이브러리 주입 환경 변수는 Python 프로세스에 전달하지 않습니다. PyTorch MPS가 Xcode의 Metal 검사 계층에서 강제 종료되는 것을 방지하며, Swift 앱 자체의 디버그 설정은 그대로 유지합니다.

## Xcode 시작 시 시스템 로그

공유 `PersonalAgent` Scheme의 Run 환경 변수에 `OS_ACTIVITY_MODE=disable`을 설정했습니다. macOS의 Intents/autoShortcut, ViewBridge 등에서 나오는 시스템 통합 로그를 Xcode 실행 중 숨깁니다. 시스템 서비스 자체의 연결 문제를 고치는 설정은 아니며, 해당 실행의 다른 `OSLog` 출력도 함께 숨깁니다. Python의 stderr 기반 단계별 시간 로그와 오류/traceback은 그대로 표시됩니다. Finder 실행이나 Archive/Profile에는 이 설정이 적용되지 않습니다.

변경 후 실행을 중지하고 Xcode에서 `PersonalAgent` Scheme으로 다시 실행하세요. 시스템 통합 로그를 조사해야 할 때는 Edit Scheme → Run → Arguments에서 이 환경 변수를 끄면 됩니다.
