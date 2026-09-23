# Personal Agent for macOS

Mac에서 로컬로 실행되는 개인 AI 에이전트입니다. ChatGPT처럼 대화하고, 모든 대화 내용과 모델 데이터는 사용자의 Mac 안에서 처리합니다.

## 실행 방법

현재 버전은 Mock Agent가 포함된 SwiftUI macOS 앱입니다. Xcode 26 이상이 설치된 Mac에서 실행할 수 있습니다.

1. [PersonalAgent.xcodeproj](/Users/jeonsuhan/dev/personal_agent/PersonalAgent/PersonalAgent.xcodeproj)를 Xcode로 엽니다.
2. 상단 Scheme에서 `PersonalAgent`와 `My Mac`을 선택합니다.
3. `⌘R`을 눌러 빌드하고 실행합니다.

터미널에서 Debug 빌드만 확인하려면 프로젝트 루트에서 다음을 실행합니다.

```bash
xcodebuild \
  -project PersonalAgent/PersonalAgent.xcodeproj \
  -scheme PersonalAgent \
  -configuration Debug \
  -derivedDataPath /tmp/personal-agent-derived \
  build CODE_SIGNING_ALLOWED=NO
```

빌드된 앱은 다음 명령으로 열 수 있습니다.

```bash
open /tmp/personal-agent-derived/Build/Products/Debug/PersonalAgent.app
```

## 핵심 구조

이 프로젝트는 **하나의 SwiftUI macOS 앱 프로젝트**로 관리합니다.

```text
PersonalAgent.app
├─ SwiftUI / Swift
│  ├─ 채팅 화면, 대화 목록, 설정 화면
│  ├─ 대화·메시지·설정 관리
│  ├─ SQLite 저장·조회
│  └─ Python Agent 프로세스 실행·통신
│
└─ Python Agent (앱 번들에 포함)
   ├─ LangChain
   ├─ LangGraph
   └─ 로컬 LLM으로 답변 생성
```

Python은 별도 백엔드 서버가 아닙니다. Swift 앱이 시작할 때 하나의 로컬 Python 프로세스로 실행되며, 모델을 한 번만 메모리에 올린 뒤 요청을 처리합니다.

## 역할 분리

| 구성 요소 | 기술 | 책임 |
| --- | --- | --- |
| 화면 | SwiftUI | 채팅 UI, 대화 목록, 입력창, 설정, macOS 사용자 경험 |
| 앱 로직 | Swift | 대화 생성·선택·삭제, 메시지 흐름, 앱 상태 관리 |
| 데이터 저장 | Swift + SQLite | 대화, 메시지, 설정을 로컬에 영속 저장 |
| AI 엔진 | Python + LangChain/LangGraph | 대화 이력으로 로컬 LLM을 실행하고 AI 답변 생성 |
| 연결 | Swift `Process` + JSON Lines | Swift와 장기 실행 Python Agent 간 요청·응답 통신 |

SwiftUI는 Swift의 UI 프레임워크입니다. 즉, 화면만 SwiftUI로 만들고 그 밖의 앱 기능은 모두 Swift로 작성합니다.

## 메시지 흐름

```text
사용자 입력 (SwiftUI)
  → Swift: 사용자 메시지를 SQLite에 저장
  → Swift: 대화 이력과 새 메시지를 Python Agent에 전달
  → Python: LangGraph / LangChain / 로컬 LLM으로 답변 생성
  → Swift: AI 답변을 SQLite에 저장
  → SwiftUI: AI 답변 표시
```

Swift와 Python은 표준입출력으로 JSON Lines를 주고받습니다. 한 줄이 하나의 JSON 메시지입니다.

```json
{"type":"generate_reply","conversation_id":"conv_123","messages":[...]}
```

```json
{"type":"assistant_reply","conversation_id":"conv_123","content":"안녕하세요!"}
```

## 예정 프로젝트 구조

```text
personal_agent/
├─ README.md
└─ PersonalAgent/                       # 하나의 Xcode / SwiftUI 프로젝트
   ├─ PersonalAgent.xcodeproj
   └─ PersonalAgent/
      ├─ App/                           # 앱 진입점·전역 상태
      ├─ Features/
      │  ├─ Chat/                       # 채팅 화면·ViewModel
      │  ├─ Conversations/              # 대화 목록 화면·ViewModel
      │  └─ Settings/                   # 설정 화면
      ├─ Models/                        # Conversation, Message 등 Swift 모델
      ├─ Services/
      │  ├─ ConversationService.swift   # 대화·메시지 관리
      │  ├─ DatabaseService.swift       # SQLite 접근
      │  └─ AgentProcessService.swift   # Python 실행·JSON Lines 통신
      ├─ Persistence/                   # SQLite 스키마·마이그레이션
      └─ Resources/
         └─ python_agent/               # 앱 번들에 포함하는 Python 코드
            ├─ main.py                  # JSON Lines 요청 루프
            ├─ chat_service.py          # AI 답변 생성 서비스
            ├─ langchain/               # 모델·프롬프트·콜백
            └─ langgraph/               # 그래프·상태·노드
```

개발 중에는 Python 코드를 Xcode 프로젝트 안에서 관리하고, 빌드할 때 앱 리소스로 번들에 포함합니다. 외부 배포 시에는 Python 런타임과 필요한 라이브러리도 앱에 포함해 사용자가 별도 Python을 설치하지 않도록 합니다.

## 로컬 데이터 위치

앱 번들 내부에는 사용자 데이터를 저장하지 않습니다. 업데이트 후에도 데이터를 보존하기 위해 다음 위치를 사용합니다.

```text
~/Library/Application Support/PersonalAgent/
├─ personal_agent.sqlite    # 대화, 메시지, 설정
├─ models/                  # 다운로드한 로컬 LLM 모델
└─ attachments/             # 사용자가 첨부한 파일
```

## 첫 번째 버전의 완료 기준

1. SwiftUI에서 새 대화를 만들고 메시지를 보낼 수 있다.
2. Swift가 SQLite에 대화와 메시지를 저장한다.
3. Swift가 앱 내부의 Python Agent에 대화 이력을 전달한다.
4. Python Agent가 로컬 LLM으로 답변을 생성한다.
5. SwiftUI에서 이전 대화를 열어 이어서 대화할 수 있다.
