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
        guard !conversations[index].messages.contains(where: { $0.proposal?.status == .pending }) else { return }

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

    private func appendResult(_ result: AgentProcessService.AgentResult, to conversationID: Conversation.ID) {
        switch result {
        case .answer(let answer): appendReply(answer, to: conversationID)
        case .proposal(let proposal):
            guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }
            conversations[index].messages.append(ChatMessage(role: .assistant, content: "다음 파일 변경을 제안합니다. 내용을 확인한 뒤 승인해 주세요.", proposal: proposal))
            save()
        }
    }

    private func appendReply(_ answer: String, to conversationID: Conversation.ID) {
        guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }
        conversations[index].messages.append(ChatMessage(role: .assistant, content: answer))
        save()
    }

    private func save() {
        let state = SavedState(
            conversations: conversations,
            selectedConversationID: selectedConversationID,
            workingDirectory: workingDirectory?.path
        )
        do {
            try FileManager.default.createDirectory(
                at: persistenceURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let data = try JSONEncoder().encode(state)
            try data.write(to: persistenceURL, options: .atomic)
        } catch {
            NSLog("대화 저장 실패: %@", error.localizedDescription)
        }
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
