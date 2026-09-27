import Foundation
import AppKit

@MainActor
final class ChatStore: ObservableObject {
    @Published private(set) var conversations: [Conversation]
    @Published var selectedConversationID: Conversation.ID?
    @Published private(set) var workingDirectory: URL?
    @Published var draft = ""
    @Published private(set) var isGeneratingReply = false

    private let agent = AgentProcessService()
    private let reminders = ReminderService()
    private let persistenceURL: URL

    private struct SavedState: Codable {
        let conversations: [Conversation]
        let selectedConversationID: Conversation.ID?
        let workingDirectory: String?
    }

    func shutdown() { agent.stop() }

    init() {
        let applicationSupport = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        )[0].appendingPathComponent("PersonalAgent", isDirectory: true)
        persistenceURL = applicationSupport.appendingPathComponent("conversations.json")

        if let savedState = Self.load(from: persistenceURL), !savedState.conversations.isEmpty {
            conversations = savedState.conversations
            selectedConversationID = savedState.selectedConversationID
                ?? savedState.conversations[0].id
            workingDirectory = savedState.workingDirectory.map(URL.init(fileURLWithPath:))
            agent.prewarm()
            return
        }

        let welcomeConversation = Conversation(
            title: "새 대화",
            messages: [
                ChatMessage(
                    role: .assistant,
                    content: "안녕하세요. 로컬 에이전트에게 무엇이든 물어보세요."
                )
            ]
        )
        conversations = [welcomeConversation]
        selectedConversationID = welcomeConversation.id
        workingDirectory = nil
        save()
        agent.prewarm()
    }

    var selectedConversation: Conversation? {
        conversations.first { $0.id == selectedConversationID }
    }

    func createConversation() {
        let conversation = Conversation()
        conversations.insert(conversation, at: 0)
        selectedConversationID = conversation.id
        draft = ""
        save()
    }

    func chooseWorkingDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "선택"
        panel.message = "에이전트가 작업할 폴더를 선택하세요."
        if let currentDirectory = workingDirectory {
            panel.directoryURL = currentDirectory
        }

        guard panel.runModal() == .OK, let url = panel.url else { return }
        workingDirectory = url
        save()
    }

    func deleteConversation(_ conversationID: Conversation.ID) {
        guard !isGeneratingReply else { return }
        conversations.removeAll { $0.id == conversationID }
        if selectedConversationID == conversationID {
            selectedConversationID = conversations.first?.id
        }
        save()

        Task { [weak self] in
            guard let self else { return }
            do {
                try await agent.deleteConversation(conversationID)
            } catch {
                NSLog("대화 이력 삭제 실패: %@", error.localizedDescription)
            }
        }
    }

    func sendDraft() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isGeneratingReply else { return }
        guard let conversationID = selectedConversationID,
              let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }
        guard !conversations[index].messages.contains(where: {
            $0.proposal?.status == .pending || ($0.reminderProposal.map { $0.status == .pending || $0.status == .saving || !$0.resultDelivered } ?? false)
        }) else { return }

        let userMessage = ChatMessage(role: .user, content: text)
        conversations[index].messages.append(userMessage)
        if conversations[index].title == "새 대화" {
            conversations[index].title = String(text.prefix(28))
        }
        draft = ""
        save()
        isGeneratingReply = true

        Task { [weak self] in
            guard let self else { return }
            defer { self.isGeneratingReply = false }
            do {
                let result = try await self.agent.reply(
                    to: text,
                    conversationID: conversationID,
                    workingDirectory: self.workingDirectory
                )
                self.appendResult(result, to: conversationID)
            } catch {
                self.appendReply("오류: \(error.localizedDescription)", to: conversationID)
            }
        }
    }

    func reviewProposal(_ messageID: UUID, approve: Bool) {
        guard !isGeneratingReply, let conversationID = selectedConversationID,
              let index = conversations.firstIndex(where: { $0.id == conversationID }),
              let messageIndex = conversations[index].messages.firstIndex(where: { $0.id == messageID }),
              conversations[index].messages[messageIndex].proposal?.status == .pending else { return }
        isGeneratingReply = true
        Task { [weak self] in
            guard let self else { return }
            defer { self.isGeneratingReply = false }
            do {
                let result = try await self.agent.review(conversationID: conversationID, approve: approve)
                if let currentIndex = self.conversations.firstIndex(where: { $0.id == conversationID }),
                   let currentMessageIndex = self.conversations[currentIndex].messages.firstIndex(where: { $0.id == messageID }) {
                    self.conversations[currentIndex].messages[currentMessageIndex].proposal?.status = approve ? .approved : .rejected
                    self.save()
                }
                self.appendResult(result, to: conversationID)
            } catch {
                if let currentIndex = self.conversations.firstIndex(where: { $0.id == conversationID }),
                   let currentMessageIndex = self.conversations[currentIndex].messages.firstIndex(where: { $0.id == messageID }) {
                    self.conversations[currentIndex].messages[currentMessageIndex].proposal?.status = .failed
                    self.save()
                }
                self.appendReply("오류: \(error.localizedDescription)", to: conversationID)
            }
        }
    }

    func reviewReminderProposal(_ messageID: UUID, approve: Bool) {
        guard !isGeneratingReply, let conversationID = selectedConversationID,
              let index = conversations.firstIndex(where: { $0.id == conversationID }),
              let messageIndex = conversations[index].messages.firstIndex(where: { $0.id == messageID }),
              let proposal = conversations[index].messages[messageIndex].reminderProposal,
              proposal.status == .pending else { return }
        isGeneratingReply = true
        Task { [weak self] in
            guard let self else { return }
            defer { self.isGeneratingReply = false }
            if approve {
                do {
                    try self.updateReminder(messageID, in: conversationID, status: .saving)
                } catch {
                    self.appendReply("저장 전 상태 기록에 실패해 미리 알림을 만들지 않았습니다: \(error.localizedDescription)", to: conversationID)
                    return
                }
                do {
                    let identifier = try await self.reminders.save(proposal)
                    try self.updateReminder(messageID, in: conversationID, status: .approved, identifier: identifier)
                } catch {
                    if case ReminderService.SaveError.uncertain = error {
                        try? self.updateReminder(messageID, in: conversationID, status: .saving, failure: error.localizedDescription)
                        self.appendReply("저장 결과를 확인할 수 없습니다. 미리 알림 앱을 확인한 뒤 카드에서 결과를 선택해 주세요. 자동으로 다시 저장하지 않습니다.", to: conversationID)
                        return
                    }
                    // A failed post-save journal write is also uncertain: never save again.
                    if self.reminder(messageID, in: conversationID)?.status == .saving,
                       !(error is ReminderService.SaveError) {
                        try? self.updateReminder(messageID, in: conversationID, status: .saving, failure: error.localizedDescription)
                        self.appendReply("저장 결과 기록에 실패했습니다. 미리 알림 앱에서 확인해 주세요. 자동으로 다시 저장하지 않습니다.", to: conversationID)
                        return
                    }
                    do {
                        try self.updateReminder(messageID, in: conversationID, status: .failed, failure: error.localizedDescription)
                    } catch {
                        self.appendReply("실패 결과를 기록하지 못했습니다. 앱에서 저장 여부를 확인해 주세요.", to: conversationID)
                        return
                    }
                }
            } else {
                do { try self.updateReminder(messageID, in: conversationID, status: .rejected) }
                catch {
                    self.appendReply("거부 결과를 기록하지 못했습니다: \(error.localizedDescription)", to: conversationID)
                    return
                }
            }
            await self.deliverReminderResult(messageID, in: conversationID)
        }
    }

    func retryReminderResult(_ messageID: UUID) {
        guard !isGeneratingReply, let conversationID = selectedConversationID,
              let proposal = reminder(messageID, in: conversationID),
              proposal.status != .pending, proposal.status != .saving,
              !proposal.resultDelivered else { return }
        isGeneratingReply = true
        Task { [weak self] in
            guard let self else { return }
            defer { self.isGeneratingReply = false }
            await self.deliverReminderResult(messageID, in: conversationID)
        }
    }

    func resolveUncertainReminder(_ messageID: UUID, wasSaved: Bool) {
        guard !isGeneratingReply, let conversationID = selectedConversationID,
              reminder(messageID, in: conversationID)?.status == .saving else { return }
        isGeneratingReply = true
        Task { [weak self] in
            guard let self else { return }
            defer { self.isGeneratingReply = false }
            do {
                try self.updateReminder(messageID, in: conversationID, status: wasSaved ? .approved : .failed,
                                        failure: wasSaved ? "사용자가 미리 알림 앱에서 등록을 확인함" : "사용자가 미리 알림 앱에서 미등록을 확인함")
                await self.deliverReminderResult(messageID, in: conversationID)
            } catch {
                self.appendReply("확인 결과를 기록하지 못했습니다: \(error.localizedDescription)", to: conversationID)
            }
        }
    }

    private func reminder(_ messageID: UUID, in conversationID: UUID) -> ReminderProposal? {
        conversations.first(where: { $0.id == conversationID })?.messages.first(where: { $0.id == messageID })?.reminderProposal
    }

    private func updateReminder(_ messageID: UUID, in conversationID: UUID, status: ReminderProposal.Status,
                                identifier: String? = nil, failure: String? = nil) throws {
        guard let index = conversations.firstIndex(where: { $0.id == conversationID }),
              let messageIndex = conversations[index].messages.firstIndex(where: { $0.id == messageID }),
              let previous = conversations[index].messages[messageIndex].reminderProposal else { return }
        conversations[index].messages[messageIndex].reminderProposal?.status = status
        conversations[index].messages[messageIndex].reminderProposal?.savedIdentifier = identifier
        conversations[index].messages[messageIndex].reminderProposal?.failureMessage = failure
        do { try persist() }
        catch {
            conversations[index].messages[messageIndex].reminderProposal = previous
            throw error
        }
    }

    private func deliverReminderResult(_ messageID: UUID, in conversationID: UUID) async {
        guard let proposal = reminder(messageID, in: conversationID) else { return }
        let status: String
        switch proposal.status {
        case .approved: status = proposal.savedIdentifier == nil ? "confirmed_saved" : "saved"
        case .rejected: status = "rejected"
        case .failed: status = proposal.failureMessage?.contains("미등록을 확인함") == true ? "confirmed_not_saved" : "failed"
        default: return
        }
        let result = AgentProcessService.ReminderReviewResult(proposal_id: proposal.proposalID, status: status,
                                                               identifier: proposal.savedIdentifier, error: proposal.failureMessage)
        do {
            let reply = try await agent.reviewReminder(conversationID: conversationID, result: result)
            if let index = conversations.firstIndex(where: { $0.id == conversationID }),
               let messageIndex = conversations[index].messages.firstIndex(where: { $0.id == messageID }) {
                conversations[index].messages[messageIndex].reminderProposal?.resultDelivered = true
                save()
            }
            appendResult(reply, to: conversationID)
        } catch {
            appendReply("결과 전달에 실패했습니다. 카드의 ‘결과 전달 재시도’를 눌러 주세요: \(error.localizedDescription)", to: conversationID)
        }
    }

    private func appendResult(_ result: AgentProcessService.AgentResult, to conversationID: Conversation.ID) {
        switch result {
        case .answer(let answer): appendReply(answer, to: conversationID)
        case .proposal(let proposal):
            guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }
            conversations[index].messages.append(ChatMessage(role: .assistant, content: "다음 파일 변경을 제안합니다. 내용을 확인한 뒤 승인해 주세요.", proposal: proposal))
            save()
        case .reminder(let proposal):
            guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }
            conversations[index].messages.append(ChatMessage(role: .assistant, content: "다음 미리 알림을 등록할까요? 내용을 확인한 뒤 승인해 주세요.", reminderProposal: proposal))
            save()
        }
    }

    private func appendReply(_ answer: String, to conversationID: Conversation.ID) {
        guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }
        conversations[index].messages.append(ChatMessage(role: .assistant, content: answer))
        save()
    }

    private func save() {
        do { try persist() }
        catch { NSLog("대화 저장 실패: %@", error.localizedDescription) }
    }

    private func persist() throws {
        let state = SavedState(
            conversations: conversations,
            selectedConversationID: selectedConversationID,
            workingDirectory: workingDirectory?.path
        )
        try FileManager.default.createDirectory(
            at: persistenceURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try JSONEncoder().encode(state)
        try data.write(to: persistenceURL, options: .atomic)
    }

    private static func load(from url: URL) -> SavedState? {
        do {
            let data = try Data(contentsOf: url)
            return try JSONDecoder().decode(SavedState.self, from: data)
        } catch {
            return nil
        }
    }
}
