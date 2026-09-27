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
    var reminderUpdateProposal: ReminderUpdateProposal?

    init(id: UUID = UUID(), role: MessageRole, content: String, createdAt: Date = .now, proposal: FileEditProposal? = nil, reminderProposal: ReminderProposal? = nil, reminderUpdateProposal: ReminderUpdateProposal? = nil) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
        self.proposal = proposal
        self.reminderProposal = reminderProposal
        self.reminderUpdateProposal = reminderUpdateProposal
    }
}

struct ReminderUpdateFields: Codable, Equatable {
    let title: String?
    let dueDate: String?
    let dueTime: String?
    let notes: String?
    let url: String?
    let listName: String?
    let `repeat`: String?
    let priority: String?

    enum CodingKeys: String, CodingKey {
        case title, notes, url, `repeat`, priority
        case dueDate = "due_date", dueTime = "due_time", listName = "list_name"
    }

    var hasChanges: Bool {
        title != nil || dueDate != nil || dueTime != nil || notes != nil || url != nil ||
        listName != nil || `repeat` != nil || priority != nil
    }

    func contains(_ key: String) -> Bool {
        switch key {
        case "due_time": dueTime != nil
        case "notes": notes != nil
        case "url": url != nil
        case "repeat": `repeat` != nil
        case "priority": priority != nil
        default: false
        }
    }
}

struct ReminderUpdateProposal: Codable, Equatable {
    enum Operation: String, Codable { case update, delete }

    let proposalID: String
    let operation: Operation
    let identifier: String
    let revision: String
    let before: ReminderSnapshot
    let after: ReminderSnapshot
    let set: ReminderUpdateFields
    let clear: [String]
    var status: ReminderProposal.Status = .pending
    var failureMessage: String?
    var resultDelivered = false

    enum CodingKeys: String, CodingKey {
        case operation, identifier, revision, before, after, set, clear, status, failureMessage, resultDelivered
        case proposalID = "proposal_id"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        proposalID = try values.decode(String.self, forKey: .proposalID)
        operation = try values.decodeIfPresent(Operation.self, forKey: .operation) ?? .update
        identifier = try values.decode(String.self, forKey: .identifier)
        revision = try values.decode(String.self, forKey: .revision)
        before = try values.decode(ReminderSnapshot.self, forKey: .before)
        after = try values.decode(ReminderSnapshot.self, forKey: .after)
        set = try values.decode(ReminderUpdateFields.self, forKey: .set)
        clear = try values.decode([String].self, forKey: .clear)
        status = try values.decodeIfPresent(ReminderProposal.Status.self, forKey: .status) ?? .pending
        failureMessage = try values.decodeIfPresent(String.self, forKey: .failureMessage)
        resultDelivered = try values.decodeIfPresent(Bool.self, forKey: .resultDelivered) ?? false
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
