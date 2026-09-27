# Local Python Agent

Python 3.13에서 실행하는 Hugging Face / LangGraph 에이전트입니다. FastAPI나 HTTP 서버를 사용하지 않습니다. Swift가 Python 프로세스를 시작하고 JSON Lines로 요청합니다. 첫 유효 요청에서 Granite 모델을 로드하고 이후 요청에서 재사용합니다.

```bash
cd agent
uv sync
cp .env.example .env
uv run python -m personal_agent
```

`MODEL_DIR` 아래 `granite-4.2-3b` 모델이 필요합니다. 기존 프로젝트의 MPS / bfloat16 설정과 생성 파라미터를 유지하므로 Apple Silicon Mac이 필요합니다. 모델 파일은 내려받지 않고 로컬 파일만 읽습니다.

입력은 한 줄에 JSON 객체 하나이며 `id`는 요청 식별자, `conversation_id`는 대화별 UUID입니다.

```json
{"id":"request-1","type":"generate_reply","conversation_id":"12345678-1234-1234-1234-123456789abc","message":"안녕하세요","model":"granite"}
```

```json
{"id":"request-1","type":"assistant_reply","answer":"안녕하세요!","conversation_id":"12345678-1234-1234-1234-123456789abc","model":"granite"}
```

실패 응답은 `{"id":"request-1","type":"error","error":"설명"}`입니다. 잘못된 요청 이후에도 프로세스는 다음 요청을 처리합니다. 로그는 stderr로 출력합니다. stdin이 닫히면 SQLite 연결을 정리하고 종료합니다.

동일한 대화 UUID를 전달하면 SQLite에 저장된 이력을 이어서 사용합니다. LangMem 요약 노드도 이전 프로젝트에서 가져왔습니다. 기본 저장 위치는 `~/Library/Application Support/PersonalAgent/checkpoints.sqlite`이며 `AGENT_DATA_DIR`로 바꿀 수 있습니다. 기존 체크포인트를 사용하려면 해당 디렉터리를 지정하세요. `.env`는 실행 위치와 무관하게 이 `agent` 폴더에서 읽습니다.

Python에서 직접 사용할 때는 `Settings`, `ChatModels`, `open_checkpointer`, `AgentService`, `AgentRequest`를 사용하면 됩니다. HTTP 계층에 의존하지 않습니다.

## 소요 시간 로그

Xcode 콘솔에서 `[시작]`, `[진행]`, `[완료]`, `[실패]` 로그로 병목을 확인할 수 있습니다. 화면이나 JSON 응답에는 진행 상태를 추가하지 않습니다.

- Python 의존성 불러오기: 프로세스 시작 시 라이브러리 import 시간
- 모델 초기화: 토크나이저, 가중치/GPU 배치, 생성 파이프라인 시간 (첫 요청)
- 대화 이력 확인 및 필요 시 요약: 이력 검사와 실제 요약이 필요할 때의 처리 시간
- 답변 생성 (GPU 추론): 모델의 응답 생성 시간
- 요청 종료: 요청 수신 후 응답 전송까지의 합계 (프로세스 최초 import 시간은 별도)

10초 이상 걸리는 단계는 10초마다 경과 시간을 출력합니다. 중첩된 단계의 시간은 서로 포함되므로 모두 더하지 않습니다. 메시지 본문은 기록하지 않습니다. 모델 로딩 이후의 요청에서는 모델 초기화 로그가 생략됩니다.
