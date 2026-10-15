# Personal Agent for macOS

SwiftUI 화면과 로컬 Python 에이전트를 하나의 저장소에서 관리합니다. Swift가 `Process`로 Python을 실행하고 표준입출력(JSON Lines)으로 요청합니다. FastAPI와 별도 웹 서버는 필요하지 않습니다.

## 주요 기능

| 기능 | 제공 내용 | 승인·제한 |
| --- | --- | --- |
| AI 채팅 | Granite 로컬 / GPT-6 Luna API 선택, SQLite 대화 이력 및 장기 대화 요약, Swift 대화 목록 저장·복원 | 대화 삭제 시 Python 체크포인트도 삭제 |
| 작업 폴더와 파일 | macOS에서 작업 폴더 선택, 파일·하위 폴더 목록 조회, UTF-8 텍스트 파일 읽기·생성·수정 | 파일 생성·수정은 변경안 확인 후 승인 필요 |
| 웹 검색 | DuckDuckGo 검색 결과 조회 | 검색 서비스 상태에 따라 결과가 없거나 실패할 수 있음 |
| macOS 단축키 | 공통 및 Finder·Spotlight·텍스트 편집별 Markdown 카탈로그에서 관련 항목 안내 | 앱·macOS 버전·키보드 배열 설정에 따라 다를 수 있음 |
| macOS 캘린더 | EventKit으로 기간·제목 조회, 일정 생성·부분 수정 | 생성·수정은 앱 확인 창에서 승인. 수정은 조회한 일정만 가능하며 변경 충돌 검사. 반복·종일·참석자 일정 수정 및 삭제는 미지원 |
| macOS 미리 알림 | EventKit으로 검색·등록·수정·삭제 | 등록·수정·삭제는 승인 필요. 수정·삭제 대기 중 항목이 변경되면 적용하지 않음 |

미리 알림 등록은 **제목과 날짜**가 필수입니다. 시간·메모·URL·목록·반복(매일/매주/매월/매년)·우선순위는 선택 사항입니다. 긴급, 태그, 깃발, 위치, 메시지 조건, 이미지, 사전 알림은 현재 자동 등록 대상이 아닙니다. 미리 알림 접근 권한은 macOS에서 허용해야 합니다.

macOS 권한이 빌드마다 초기화되지 않도록 Debug 빌드는 `PersonalAgent/DebugSigning.xcconfig`에서 로컬 서명을 지원합니다. 이 Mac의 인증서 선택은 Git에 포함되지 않는 `PersonalAgent/DebugSigning.local.xcconfig`에만 저장합니다. 다른 Mac에서는 자체 코드 서명 인증서를 준비한 뒤 같은 파일에 `CODE_SIGN_STYLE = Manual`과 `CODE_SIGN_IDENTITY = 인증서 이름`을 설정할 수 있습니다. 로컬 인증서를 설정하지 않으면 기존 임시 서명으로 빌드됩니다.

## 준비 및 실행

1. Apple Silicon Mac에 Xcode와 uv를 설치합니다. Python 환경은 프로젝트 설정에 따라 3.13을 사용합니다.
2. 저장소의 `agent` 폴더에서 Python 환경을 준비합니다.

   ```bash
   cd agent
   uv sync
   cp .env.example .env
   ```

3. 로컬 Granite를 사용할 경우 `agent/.env`의 `MODEL_DIR`를 확인합니다. 기본값은 `/Volumes/sh_disk/model`이며 그 아래 `granite-4.2-3b` 모델 파일이 있어야 합니다. 모델은 자동으로 내려받지 않고 로컬 파일만 읽습니다. 추론에는 Apple Silicon의 MPS를 사용합니다.
4. `PersonalAgent/PersonalAgent.xcodeproj`를 Xcode에서 열고 `PersonalAgent` / `My Mac`으로 실행합니다.

앱을 실행하면 백그라운드에서 Python 워커, 그래프 및 체크포인트 저장소를 미리 준비합니다. 모델은 선택한 모델의 첫 요청에서 초기화하고 이후에는 재사용합니다. GPT-6 Luna를 선택하면 Granite 가중치를 불러오지 않습니다. 초기화 중 입력된 첫 메시지는 워커가 준비될 때까지 대기한 뒤 처리됩니다. 이후에는 같은 Python 프로세스와 모델을 재사용합니다. 오류는 대화창에 표시하며 자세한 로그는 Xcode 콘솔에서 확인합니다. 10분 동안 응답이 없으면 프로세스를 종료하며 다음 요청에서 다시 시작합니다.

Python 워커만 실행하려면 `agent` 폴더에서 `uv run python -m personal_agent`를 사용합니다. 이 경우 아래 JSON Lines 프로토콜로 표준입출력을 직접 연결해야 합니다. 미리 알림 조회·승인처럼 macOS 기능을 사용하는 요청에는 Swift의 응답도 필요합니다.

## OpenAI API 설정

1. 앱 왼쪽 아래 **설정** 버튼을 누릅니다.
2. OpenAI API 키를 입력하고 **저장**을 누릅니다.
3. 입력창의 모델 메뉴에서 **GPT-6 Luna · API**를 선택합니다.

키는 macOS 키체인에 저장되며 설정에서 교체하거나 삭제할 수 있습니다. 저장한 키 값은 다시 표시하지 않습니다. 키 변경은 다음 요청부터 적용되므로 앱을 재실행할 필요가 없습니다. 답변 생성 중에는 키 변경이 비활성화됩니다. 키 저장은 API 연결 성공을 의미하지 않으며 인증 오류는 실제 요청 시 대화창에 표시됩니다.

앱은 키체인의 키를 Python 워커의 환경 변수로 전달하며 대화 저장 파일이나 체크포인트에는 포함하지 않습니다. 앱에서는 `.env`나 상위 프로세스의 API 키 대신 설정에 저장한 키만 사용합니다. Python 워커를 직접 실행하는 개발 환경에서는 `OPENAI_API_KEY` 환경 변수 또는 `agent/.env` 설정도 사용할 수 있습니다.

GPT-6 Luna는 OpenAI Chat Completions API와 `reasoning_effort=none`을 사용하며, 도구 호출을 한 번에 하나씩 처리합니다. 기존 파일·미리 알림·캘린더 도구와 승인 흐름을 공유합니다. 답변과 대화 요약 모두 선택한 모델을 사용합니다. API 모델을 선택하면 대화 이력과 도구 결과가 OpenAI로 전송되며 API 사용량에 따라 비용이 발생합니다.

## 구조

```text
personal-agent/
├── PersonalAgent/                 # 기존 SwiftUI macOS 앱
│   ├── PersonalAgent.xcodeproj
│   └── PersonalAgent/
│       ├── App/
│       ├── Features/              # 채팅 / 대화 목록
│       ├── Models/
│       └── Services/              # Python 프로세스 통신 / EventKit 미리 알림
└── agent/
    ├── pyproject.toml
    ├── uv.lock
    └── src/personal_agent/
        ├── __main__.py            # JSON Lines 요청 루프
        ├── runtime.py             # 워커 초기화 / 요청 분배
        ├── chain/                 # 프롬프트
        ├── graph/                 # 생성, 이력 요약, 승인 흐름, 체크포인트
        ├── llm/                   # Hugging Face 모델 로딩과 모델별 설정
        ├── services/              # 채팅, 승인 재개, Swift 도구 브리지
        ├── tools/                 # 파일, 검색, 미리 알림, macOS 단축키 도구
        ├── data/macos_shortcuts/  # 공통 및 범주별 Markdown 단축키 문서
        ├── config/
        └── schemas/
```

Swift는 대화 UUID와 새 메시지를 전송하고 Python이 해당 UUID의 이력을 관리합니다. 새 대화는 별도 UUID를 사용합니다. 화면의 대화 목록과 선택한 작업 폴더는 Swift가 앱 지원 디렉터리에 저장해 다음 실행 때 복원합니다. Python 체크포인트는 기본적으로 `~/Library/Application Support/PersonalAgent/checkpoints.sqlite`에 저장됩니다. `AGENT_DATA_DIR`로 저장 디렉터리를 바꿀 수 있습니다.

개발 실행 시 Swift 소스 경로를 기준으로 같은 저장소의 `agent/.venv/bin/python`을 찾습니다. 필요하면 Xcode Scheme 환경 변수 `PERSONAL_AGENT_DIR`(agent 폴더 절대 경로), `PERSONAL_AGENT_PYTHON`(Python 실행 파일 절대 경로)으로 변경할 수 있습니다. 현재는 개발용 로컬 환경이며 Python 런타임·모델을 포함한 배포용 앱 번들 구성은 별도 작업입니다.

`.env`는 실행 위치와 관계없이 `agent/.env`에서 읽습니다. Python 코드에서 직접 사용할 때는 `Settings`, `ChatModels`, `open_checkpointer`, `AgentService`, `ReviewService`, `AgentRequest`를 사용할 수 있습니다. `AgentService`는 새 요청을 실행하고 `ReviewService`는 승인 대기 중인 그래프를 재개합니다.

## Python 워커 프로토콜

Swift와 Python은 한 줄에 JSON 객체 하나를 주고받습니다. `id`는 요청 식별자, `conversation_id`는 대화별 UUID입니다. 같은 대화 UUID를 사용하면 저장된 이력을 이어서 사용합니다.

```json
{"id":"request-1","type":"generate_reply","conversation_id":"12345678-1234-1234-1234-123456789abc","message":"안녕하세요","model":"granite"}
```

```json
{"id":"request-1","type":"assistant_reply","answer":"안녕하세요!","conversation_id":"12345678-1234-1234-1234-123456789abc","model":"granite"}
```

실패 응답은 `{"id":"request-1","type":"error","error":"설명"}` 형식입니다. 잘못된 요청 뒤에도 워커는 다음 요청을 처리합니다. 로그는 stderr로 출력하고, stdin이 닫히면 SQLite 연결을 정리하고 종료합니다. 파일·미리 알림 승인 등은 별도의 요청/응답 유형을 사용합니다.

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

## 소요 시간 로그

Xcode 콘솔에서 `[시작]`, `[진행]`, `[완료]`, `[실패]` 로그로 Python 의존성 불러오기, 모델 초기화, 이력 요약, GPU 추론, 요청 전체 시간을 확인할 수 있습니다. 10초 이상 걸리는 단계는 경과 시간을 주기적으로 표시합니다. 중첩된 단계의 시간은 서로 포함되므로 모두 더하지 않습니다. 메시지 본문은 기록하지 않습니다.

## Xcode 시작 시 시스템 로그

공유 `PersonalAgent` Scheme의 Run 환경 변수에 `OS_ACTIVITY_MODE=disable`을 설정했습니다. macOS의 Intents/autoShortcut, ViewBridge 등에서 나오는 시스템 통합 로그를 Xcode 실행 중 숨깁니다. 시스템 서비스 자체의 연결 문제를 고치는 설정은 아니며, 해당 실행의 다른 `OSLog` 출력도 함께 숨깁니다. Python의 stderr 기반 단계별 시간 로그와 오류/traceback은 그대로 표시됩니다. Finder 실행이나 Archive/Profile에는 이 설정이 적용되지 않습니다.

변경 후 실행을 중지하고 Xcode에서 `PersonalAgent` Scheme으로 다시 실행하세요. 시스템 통합 로그를 조사해야 할 때는 Edit Scheme → Run → Arguments에서 이 환경 변수를 끄면 됩니다.

## 캘린더 사용 예시

- “내일 일정 보여줘” — 해당 날짜와 겹치는 일정을 최대 50건 조회합니다.
- “내일 오전 10시부터 11시까지 회의 추가해줘” — 제목·시간·캘린더·장소·메모를 확인하고 저장합니다.
- “내일 회의 장소를 회의실 A로 바꿔줘” — 먼저 조회한 후 변경 전후 내용을 승인합니다.

첫 사용 시 macOS 캘린더 전체 접근 권한이 필요합니다. 시간 일정의 제목·시작·종료·장소·메모를 지원하며 생성 시 캘린더 이름을 지정할 수 있습니다. 종료 시각이 없으면 에이전트가 확인합니다. 반복·종일 일정 생성, 참석자·알림 설정, 삭제는 지원하지 않습니다. 승인 창은 110초 내 응답해야 하며, 만료되면 다시 요청해야 합니다.

## 도구별 시연 질문

앱 상단의 폴더 버튼으로 시연용 작업 폴더를 선택합니다. GPT-6 Luna를 사용할 경우 왼쪽 아래 설정에서 API 키를 등록하고 모델 메뉴에서 선택합니다. 캘린더와 미리 알림은 첫 사용 시 macOS 접근 권한을 허용합니다. 아래 질문의 ‘내일’은 실행하는 날을 기준으로 해석합니다.

파일은 생성 → 읽기 → 수정, 미리 알림은 등록 → 조회 → 수정 → 삭제, 캘린더는 생성 → 조회 → 수정 순서로 진행합니다. 각 묶음은 새 대화에서 시작하면 편리합니다. 질문 하나가 조회와 수정 등 여러 도구를 호출할 수도 있습니다.

| 기능 | 도구 | 시연용 질문 | 확인할 동작 |
| --- | --- | --- | --- |
| 작업 폴더 조회 | `list_directory` | 현재 작업 폴더의 파일과 하위 폴더 목록을 보여줘. | 선택한 폴더의 항목과 파일·폴더 구분 표시 |
| 파일 생성 | `create_file` | 현재 작업 폴더에 demo-note.txt 파일을 만들고, 내용은 ‘시연 준비 중’으로 작성해줘. | 경로·변경안 확인 및 승인 후 새 파일 생성 |
| 파일 읽기 | `read_file` | demo-note.txt 파일 내용을 읽어줘. | ‘시연 준비 중’이라는 실제 파일 내용 반환 |
| 파일 수정 | `update_file` | demo-note.txt의 ‘시연 준비 중’을 ‘시연 준비 완료’로 바꿔줘. | 원본 조회 후 변경안 표시, 승인 후 문구 변경 |
| 웹 검색 | `web_search` | macOS 캘린더 사용법에 관한 Apple 공식 지원 문서를 웹에서 검색하고 링크를 알려줘. | 웹 검색 결과와 출처 URL 표시 |
| macOS 단축키 | `get_macos_shortcuts` | Finder에서 자주 쓰는 단축키를 알려줘. | Finder 및 공통 단축키 카탈로그에 근거한 안내 |
| 미리 알림 등록 | `propose_reminder` | 내일 오전 9시에 ‘시연용 자료 준비’ 미리 알림을 추가해줘. 메모는 ‘발표 자료 확인’으로 해줘. | 제목·날짜·시간·메모가 포함된 등록안 표시, 승인 후 미리 알림 앱에 저장 |
| 미리 알림 조회 | `find_reminders` | 내일 예정된 ‘시연용 자료 준비’ 미리 알림을 찾아줘. | 등록된 항목의 제목·예정일 등 실제 조회 결과 표시 |
| 미리 알림 수정 | `propose_update_reminder` | 내일 ‘시연용 자료 준비’ 미리 알림의 시간을 오전 10시로 바꿔줘. | 대상 조회 후 변경 전후 표시, 승인 후 시간만 변경 |
| 미리 알림 삭제 | `propose_delete_reminder` | 내일 ‘시연용 자료 준비’ 미리 알림을 삭제해줘. | 대상 조회 후 삭제안 표시, 삭제 승인 후 해당 항목 제거 |
| 캘린더 일정 생성 | `create_calendar_event` | 내일 오후 6시부터 오후 7시까지 ‘시연용 러닝크루’ 일정을 추가해줘. 장소는 ‘한강공원’, 메모는 ‘운동화 챙기기’로 해줘. | 18:00~19:00 일정 확인 창 표시, 저장 승인 후 캘린더에 추가 |
| 캘린더 일정 조회 | `find_calendar_events` | 내일 ‘시연용 러닝크루’ 일정을 찾아서 시간과 장소를 알려줘. | 실제 일정의 시간·장소 조회 |
| 캘린더 일정 수정 | `update_calendar_event` | 내일 ‘시연용 러닝크루’ 일정의 장소를 ‘서울숲’으로 바꿔줘. | 대상 조회 후 변경 전후 확인 창 표시, 저장 승인 후 장소만 변경 |

### 추가 확인 시나리오

| 확인 항목 | 시연용 질문 또는 조작 | 확인할 동작 |
| --- | --- | --- |
| 필수 정보 확인 | 내일 오후 6시에 ‘시연용 저녁 모임’ 일정을 추가해줘. | 종료 시각이나 소요 시간을 질문하고 임의로 저장하지 않음 |
| 후속 답변 처리 | 위 질문에 이어 ‘오후 7시까지’라고 답하기 | 앞서 입력한 제목·날짜·시작 시각을 유지한 생성안 표시 |
| 승인 거부 | ‘demo-cancel.txt 파일을 만들고 내용은 취소 테스트로 해줘’ 요청 후 거부 선택 | 파일이 생성되지 않음 |
| 캘린더 저장 취소 | ‘내일 오후 8시부터 9시까지 시연용 취소 테스트 일정을 추가해줘’ 요청 후 확인 창에서 취소 선택 | 일정이 생성되지 않음 |
| 수정 결과 재확인 | 내일 ‘시연용 러닝크루’ 일정을 다시 조회해줘. | 시간은 18:00~19:00, 장소는 ‘서울숲’, 메모는 ‘운동화 챙기기’로 유지 |
| 삭제 결과 재확인 | 내일 ‘시연용 자료 준비’ 미리 알림을 다시 찾아줘. | 삭제한 항목이 검색 결과에 나타나지 않음 |

시연 후 생성한 캘린더 일정은 macOS 캘린더 앱에서 직접 삭제합니다. 현재 에이전트에는 캘린더 일정 삭제 도구가 없습니다.
