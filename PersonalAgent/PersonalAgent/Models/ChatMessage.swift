import Foundation

enum MessageRole: String, Codable {
    case user
    case assistant
}

struct ChatMessage: Identifiable, Equatable, Codable {
    let id: UUID
    let role: MessageRole
    let content: String
    let createdAt: Date
    var proposal: FileEditProposal?

    init(id: UUID = UUID(), role: MessageRole, content: String, createdAt: Date = .now, proposal: FileEditProposal? = nil) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
        self.proposal = proposal
    }
}

struct FileEditProposal: Equatable, Codable {
    let path: String
    let diff: String
    let operation: String
    var status: Status = .pending

    enum Status: String, Codable { case pending, approved, rejected, failed }
}

struct Conversation: Identifiable, Equatable, Codable {
    let id: UUID
    var title: String
    var messages: [ChatMessage]

    init(id: UUID = UUID(), title: String = "새 대화", messages: [ChatMessage] = []) {
        self.id = id
        self.title = title
        self.messages = messages
    }
}
