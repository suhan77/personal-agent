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
    var reminderProposal: ReminderProposal?

    init(id: UUID = UUID(), role: MessageRole, content: String, createdAt: Date = .now, proposal: FileEditProposal? = nil, reminderProposal: ReminderProposal? = nil) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
        self.proposal = proposal
        self.reminderProposal = reminderProposal
    }
}

struct ReminderProposal: Equatable, Codable {
    let proposalID: String
    let title: String
    let dueDate: String
    let dueTime: String?
    let notes: String?
    let url: String?
    let listName: String?
    let `repeat`: String?
    let priority: String?
    var status: Status = .pending
    var savedIdentifier: String?
    var failureMessage: String?
    var resultDelivered = false

    enum Status: String, Codable { case pending, saving, approved, rejected, failed }

    enum CodingKeys: String, CodingKey {
        case title, notes, url, `repeat`, priority, status, savedIdentifier, failureMessage, resultDelivered
        case proposalID = "proposal_id", dueDate = "due_date", dueTime = "due_time", listName = "list_name"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        proposalID = try values.decodeIfPresent(String.self, forKey: .proposalID) ?? ""
        title = try values.decode(String.self, forKey: .title)
        dueDate = try values.decode(String.self, forKey: .dueDate)
        dueTime = try values.decodeIfPresent(String.self, forKey: .dueTime)
        notes = try values.decodeIfPresent(String.self, forKey: .notes)
        url = try values.decodeIfPresent(String.self, forKey: .url)
        listName = try values.decodeIfPresent(String.self, forKey: .listName)
        `repeat` = try values.decodeIfPresent(String.self, forKey: .repeat)
        priority = try values.decodeIfPresent(String.self, forKey: .priority)
        status = try values.decodeIfPresent(Status.self, forKey: .status) ?? .pending
        savedIdentifier = try values.decodeIfPresent(String.self, forKey: .savedIdentifier)
        failureMessage = try values.decodeIfPresent(String.self, forKey: .failureMessage)
        resultDelivered = try values.decodeIfPresent(Bool.self, forKey: .resultDelivered) ?? false
        if proposalID.isEmpty {
            status = .failed
            failureMessage = "이전 버전의 등록안입니다. 다시 요청해 주세요."
            resultDelivered = true
        }
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
