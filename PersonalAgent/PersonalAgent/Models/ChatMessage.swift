import Foundation

enum MessageRole: String, Codable {
    case user
    case assistant
}

struct ChatMessage: Identifiable, Equatable {
    let id: UUID
    let role: MessageRole
    let content: String
    let createdAt: Date

    init(id: UUID = UUID(), role: MessageRole, content: String, createdAt: Date = .now) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
    }
}

struct Conversation: Identifiable, Equatable {
    let id: UUID
    var title: String
    var messages: [ChatMessage]

    init(id: UUID = UUID(), title: String = "새 대화", messages: [ChatMessage] = []) {
        self.id = id
        self.title = title
        self.messages = messages
    }
}
