import Foundation

@main
struct ReminderModelChecks {
    static func main() throws {
        let decoder = JSONDecoder()
        let dateOnly = try decoder.decode(ReminderProposal.self, from: Data("""
        {"proposal_id":"call-1","title":"발표 준비","due_date":"2026-09-29"}
        """.utf8))
        precondition(dateOnly.dueTime == nil && dateOnly.status == .pending)
        precondition(!dateOnly.resultDelivered)

        var detailed = try decoder.decode(ReminderProposal.self, from: Data("""
        {"proposal_id":"call-2","title":"발표 준비","due_date":"2026-09-29",
         "due_time":"15:00:00","notes":"자료 확인","url":"https://example.com",
         "list_name":"스터디","repeat":"weekly","priority":"high"}
        """.utf8))
        precondition(detailed.dueTime == "15:00:00")
        precondition(detailed.repeat == "weekly" && detailed.priority == "high")

        detailed.status = .saving
        let pendingConversation = Conversation(messages: [
            ChatMessage(role: .assistant, content: "승인 대기", reminderProposal: detailed)
        ])
        let restored = try decoder.decode(Conversation.self, from: JSONEncoder().encode(pendingConversation))
        precondition(restored.messages[0].reminderProposal?.status == .saving)
        precondition(restored.messages[0].reminderProposal?.proposalID == "call-2")

        detailed.status = .approved
        detailed.savedIdentifier = "event-id"
        let restoredSaved = try decoder.decode(ReminderProposal.self, from: JSONEncoder().encode(detailed))
        precondition(restoredSaved.savedIdentifier == "event-id")
        precondition(!restoredSaved.resultDelivered)

        let legacy = try decoder.decode(ReminderProposal.self, from: Data("""
        {"title":"이전 등록안","due_date":"2026-09-29"}
        """.utf8))
        precondition(legacy.status == .failed && legacy.resultDelivered)

        let update = try decoder.decode(ReminderUpdateProposal.self, from: Data("""
        {"proposal_id":"update-1","identifier":"event-id","revision":"abc",
         "before":{"identifier":"event-id","title":"발표 준비","due_date":"2026-09-29",
                   "list_name":"기본","notes":"기존 메모","is_completed":false},
         "after":{"identifier":"event-id","title":"새 제목","due_date":"2026-09-29",
                  "list_name":"기본","is_completed":false},
         "set":{"title":"새 제목"},"clear":["notes"]}
        """.utf8))
        precondition(update.before.revision == nil && update.after.notes == nil)
        precondition(update.set.title == "새 제목" && update.clear == ["notes"])
        let restoredUpdate = try decoder.decode(Conversation.self, from: JSONEncoder().encode(Conversation(messages: [
            ChatMessage(role: .assistant, content: "수정 승인 대기", reminderUpdateProposal: update)
        ])))
        precondition(restoredUpdate.messages[0].reminderUpdateProposal?.status == .pending)
        let deletion = try decoder.decode(ReminderUpdateProposal.self, from: Data("""
        {"proposal_id":"delete-1","operation":"delete","identifier":"event-id","revision":"abc",
         "before":{"identifier":"event-id","title":"발표 준비","list_name":"기본","is_completed":false},
         "after":{"identifier":"event-id","title":"발표 준비","list_name":"기본","is_completed":false},
         "set":{},"clear":[]}
        """.utf8))
        precondition(deletion.operation == .delete)
        let restoredDeletion = try decoder.decode(Conversation.self, from: JSONEncoder().encode(Conversation(messages: [
            ChatMessage(role: .assistant, content: "삭제 승인 대기", reminderUpdateProposal: deletion)
        ])))
        precondition(restoredDeletion.messages[0].reminderUpdateProposal?.operation == .delete)
        print("Reminder model checks passed")
    }
}
