import Foundation

@MainActor
final class ChatStore: ObservableObject {
    @Published private(set) var conversations: [Conversation]
    @Published var selectedConversationID: Conversation.ID?
    @Published var draft = ""
    @Published private(set) var isGeneratingReply = false

    init() {
        let welcomeConversation = Conversation(
            title: "새 대화",
            messages: [
                ChatMessage(
                    role: .assistant,
                    content: "안녕하세요. 아직은 Mock Agent지만, 무엇이든 입력해 보세요."
                )
            ]
        )
        conversations = [welcomeConversation]
        selectedConversationID = welcomeConversation.id
    }

    var selectedConversation: Conversation? {
        conversations.first { $0.id == selectedConversationID }
    }

    func createConversation() {
        let conversation = Conversation()
        conversations.insert(conversation, at: 0)
        selectedConversationID = conversation.id
        draft = ""
    }

    func sendDraft() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isGeneratingReply else { return }
        guard let conversationID = selectedConversationID,
              let index = conversations.firstIndex(where: { $0.id == conversationID }) else { return }

        let userMessage = ChatMessage(role: .user, content: text)
        conversations[index].messages.append(userMessage)
        if conversations[index].title == "새 대화" {
            conversations[index].title = String(text.prefix(28))
        }
        draft = ""
        isGeneratingReply = true

        Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            guard !Task.isCancelled else { return }
            self?.appendMockReply(to: conversationID, for: text)
        }
    }

    private func appendMockReply(to conversationID: Conversation.ID, for text: String) {
        guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else {
            isGeneratingReply = false
            return
        }

        conversations[index].messages.append(
            ChatMessage(
                role: .assistant,
                content: "Mock Agent 응답입니다. 방금 ‘\(text)’라고 말했어요."
            )
        )
        isGeneratingReply = false
    }
}
