import Foundation

/// One Python process per app. Only JSON Lines travel over stdout.
@MainActor
final class AgentProcessService {
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var buffer = Data()
    private var pending: CheckedContinuation<AgentResult, Error>?
    private var requestID: String?
    private var timeout: Task<Void, Never>?
    private let reminders = ReminderService()

    private struct ReminderLookupArguments: Decodable {
        let query: String
        let due_date: String?
        let list_name: String?
        let include_completed: Bool
    }

    private struct Reply: Decodable {
        let id: String?
        let type: String
        let answer: String?
        let error: String?
        let path: String?
        let diff: String?
        let operation: String?
        let reminder: ReminderProposal?
        let tool: String?
        let call_id: String?
        let arguments: ReminderLookupArguments?
    }

    enum AgentResult {
        case answer(String)
        case proposal(FileEditProposal)
        case reminder(ReminderProposal)
    }

    private struct Request: Encodable {
        let id: String
        let type = "generate_reply"
        let conversation_id: String
        let message: String
        let working_directory: String?
    }

    private struct DeleteRequest: Encodable {
        let id: String
        let type = "delete_conversation"
        let conversation_id: String
    }

    private struct ReviewRequest: Encodable {
        let id: String
        let type = "review_file_change"
        let conversation_id: String
        let decision: String
    }

    private struct ReminderReviewRequest: Encodable {
        let id: String
        let type = "review_reminder"
        let conversation_id: String
        let result: ReminderReviewResult
    }

    struct ReminderReviewResult: Encodable {
        let proposal_id: String
        let status: String
        let identifier: String?
        let error: String?
    }

    private struct NativeToolResult: Encodable {
        let id: String
        let type = "native_tool_result"
        let call_id: String
        let result: ReminderSearchResult?
        let error: String?
    }

    struct AgentFailure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// Starts the persistent worker as soon as the app launches. Python then
    /// performs its imports and model warm-up while the chat UI is idle.
    func prewarm() {
        do {
            try startIfNeeded()
        } catch {
            // Keep startup failures for the first user-visible request, where
            // they can be shown in the conversation instead of blocking launch.
        }
    }

    func reply(to message: String, conversationID: UUID, workingDirectory: URL?) async throws -> AgentResult {
        guard pending == nil else { throw AgentFailure(message: "답변 생성 중입니다.") }
        try startIfNeeded()
        let id = UUID().uuidString
        var data = try JSONEncoder().encode(Request(
            id: id,
            conversation_id: conversationID.uuidString,
            message: message,
            working_directory: workingDirectory?.path
        ))
        data.append(0x0A)
        return try await withCheckedThrowingContinuation { continuation in
            pending = continuation
            requestID = id
            timeout = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(600)) } catch { return }
                self?.stop(reason: "모델 응답 시간이 초과되었습니다. 다시 시도해 주세요.")
            }
            do {
                try input?.write(contentsOf: data)
            } catch {
                stop(reason: "에이전트에 요청을 전달하지 못했습니다: \(error.localizedDescription)")
            }
        }
    }

    func review(conversationID: UUID, approve: Bool) async throws -> AgentResult {
        guard pending == nil else { throw AgentFailure(message: "답변 생성 중입니다.") }
        try startIfNeeded()
        let id = UUID().uuidString
        var data = try JSONEncoder().encode(ReviewRequest(id: id, conversation_id: conversationID.uuidString, decision: approve ? "approve" : "reject"))
        data.append(0x0A)
        return try await withCheckedThrowingContinuation { continuation in
            pending = continuation
            requestID = id
            timeout = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(600)) } catch { return }
                self?.stop(reason: "승인 처리 시간이 초과되었습니다.")
            }
            do { try input?.write(contentsOf: data) }
            catch { stop(reason: "승인 요청을 전달하지 못했습니다: \(error.localizedDescription)") }
        }
    }

    func reviewReminder(conversationID: UUID, result: ReminderReviewResult) async throws -> AgentResult {
        guard pending == nil else { throw AgentFailure(message: "답변 생성 중입니다.") }
        try startIfNeeded()
        let id = UUID().uuidString
        var data = try JSONEncoder().encode(ReminderReviewRequest(id: id, conversation_id: conversationID.uuidString, result: result))
        data.append(0x0A)
        return try await withCheckedThrowingContinuation { continuation in
            pending = continuation
            requestID = id
            timeout = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(600)) } catch { return }
                self?.stop(reason: "미리 알림 처리 시간이 초과되었습니다.")
            }
            do { try input?.write(contentsOf: data) }
            catch { stop(reason: "미리 알림 결과를 전달하지 못했습니다: \(error.localizedDescription)") }
        }
    }

    private func startIfNeeded() throws {
        if let process, process.isRunning { return }
        stop(reason: "에이전트를 다시 시작합니다.")
        let environment = ProcessInfo.processInfo.environment
        // Development default follows this checkout, even when Xcode launches from another cwd.
        let sourceRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let agentRoot = environment["PERSONAL_AGENT_DIR"].map { URL(fileURLWithPath: $0) }
            ?? sourceRoot.appendingPathComponent("agent")
        let python = environment["PERSONAL_AGENT_PYTHON"]
            ?? agentRoot.appendingPathComponent(".venv/bin/python").path
        guard FileManager.default.isExecutableFile(atPath: python) else {
            throw AgentFailure(message: "Python 환경이 없습니다. 프로젝트 agent 폴더에서 uv sync를 실행해 주세요.")
        }
        let child = Process()
        let stdin = Pipe()
        let stdout = Pipe()
        child.executableURL = URL(fileURLWithPath: python)
        child.arguments = ["-u", "-m", "personal_agent"]
        child.currentDirectoryURL = agentRoot
        // Xcode's injected libraries and Metal validation are for the Swift app.
        // Inheriting them can abort PyTorch MPS kernels in the Python worker.
        var childEnvironment = environment.filter { key, _ in
            !["DYLD_", "MTL_", "METAL_", "__XCODE_"].contains { key.hasPrefix($0) }
        }
        childEnvironment["MTL_DEBUG_LAYER"] = "0"
        childEnvironment["PYTHONPATH"] = agentRoot.appendingPathComponent("src").path
        childEnvironment["HF_HUB_OFFLINE"] = "1"
        child.environment = childEnvironment
        child.standardInput = stdin
        child.standardOutput = stdout
        child.standardError = FileHandle.standardError
        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            Task { @MainActor [weak self] in
                guard self?.process === child else { return }
                if data.isEmpty {
                    self?.stop(reason: "에이전트 연결이 종료되었습니다. 다시 시도해 주세요.")
                } else {
                    self?.receive(data)
                }
            }
        }
        child.terminationHandler = { [weak self] child in
            Task { @MainActor [weak self] in
                guard self?.process === child else { return }
                self?.stop(reason: "에이전트가 종료되었습니다 (\(child.terminationStatus)). 모델 경로와 Python 환경을 확인해 주세요.")
            }
        }
        process = child
        input = stdin.fileHandleForWriting
        output = stdout.fileHandleForReading
        do { try child.run() } catch {
            stop(reason: error.localizedDescription)
            throw error
        }
    }

    private func receive(_ data: Data) {
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 0x0A) {
            let line = Data(buffer[..<newline])
            buffer.removeSubrange(...newline)
            do {
                let reply = try JSONDecoder().decode(Reply.self, from: line)
                guard reply.id == requestID else { continue }
                // Ignore status events from workers started by an older build.
                if reply.type == "progress" { continue }
                if reply.type == "native_tool_request", let callID = reply.call_id {
                    handleNativeTool(reply, callID: callID)
                } else if reply.type == "assistant_reply", let answer = reply.answer {
                    finish(.success(.answer(answer)))
                } else if reply.type == "file_edit_proposal", let path = reply.path, let diff = reply.diff, let operation = reply.operation {
                    finish(.success(.proposal(FileEditProposal(path: path, diff: diff, operation: operation))))
                } else if reply.type == "reminder_proposal", let reminder = reply.reminder {
                    finish(.success(.reminder(reminder)))
                } else if reply.type == "conversation_deleted" {
                    finish(.success(.answer("")))
                } else {
                    finish(.failure(AgentFailure(message: reply.error ?? "에이전트 응답 오류")))
                }
            } catch {
                stop(reason: "에이전트 응답을 읽지 못했습니다: \(error.localizedDescription)")
                return
            }
        }
    }

    private func handleNativeTool(_ reply: Reply, callID: String) {
        guard let parentID = reply.id else { return }
        NSLog("macOS 도구 요청 수신: %@", reply.tool ?? "unknown")
        Task { [weak self] in
            guard let self else { return }
            let response: NativeToolResult
            if reply.tool == "find_reminders", let arguments = reply.arguments {
                do {
                    let items = try await reminders.find(query: arguments.query, dueDate: arguments.due_date,
                                                         listName: arguments.list_name,
                                                         includeCompleted: arguments.include_completed)
                    NSLog("미리 알림 조회 완료: %d건", items.items.count)
                    response = NativeToolResult(id: parentID, call_id: callID, result: items, error: nil)
                } catch {
                    NSLog("미리 알림 조회 실패: %@", error.localizedDescription)
                    response = NativeToolResult(id: parentID, call_id: callID, result: nil,
                                                error: error.localizedDescription)
                }
            } else {
                response = NativeToolResult(id: parentID, call_id: callID, result: nil,
                                            error: "지원하지 않는 macOS 도구 요청입니다.")
            }
            guard requestID == parentID else { return }
            do {
                var data = try JSONEncoder().encode(response)
                data.append(0x0A)
                try input?.write(contentsOf: data)
            } catch {
                stop(reason: "macOS 도구 결과를 전달하지 못했습니다: \(error.localizedDescription)")
            }
        }
    }

    func deleteConversation(_ conversationID: UUID) async throws {
        guard pending == nil else { throw AgentFailure(message: "답변 생성 중입니다.") }
        try startIfNeeded()
        let id = UUID().uuidString
        var data = try JSONEncoder().encode(DeleteRequest(
            id: id,
            conversation_id: conversationID.uuidString
        ))
        data.append(0x0A)
        _ = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<AgentResult, Error>) in
            pending = continuation
            requestID = id
            timeout = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(60)) } catch { return }
                self?.stop(reason: "대화 삭제 시간이 초과되었습니다.")
            }
            do {
                try input?.write(contentsOf: data)
            } catch {
                stop(reason: "대화 삭제 요청을 전달하지 못했습니다: \(error.localizedDescription)")
            }
        }
    }

    private func finish(_ result: Result<AgentResult, Error>) {
        timeout?.cancel()
        timeout = nil
        let continuation = pending
        pending = nil
        requestID = nil
        continuation?.resume(with: result)
    }

    func stop(reason: String = "앱이 종료되었습니다.") {
        output?.readabilityHandler = nil
        process?.terminationHandler = nil
        try? input?.close()
        try? output?.close()
        // Idle workers exit on stdin EOF and close SQLite cleanly.
        // An active generation must be interrupted when the app closes or times out.
        if pending != nil, process?.isRunning == true { process?.terminate() }
        process = nil
        input = nil
        output = nil
        buffer.removeAll()
        finish(.failure(AgentFailure(message: reason)))
    }
}
