import EventKit
import Foundation
import CryptoKit

@MainActor
protocol ReminderStoring {
    var eventStore: EKEventStore { get }
    func requestAccess() async throws -> Bool
    func calendars() -> [EKCalendar]
    func defaultCalendar() -> EKCalendar?
    func save(_ reminder: EKReminder) throws
    func remove(_ reminder: EKReminder) throws
    func fetchReminders(matching predicate: NSPredicate, completion: @escaping @Sendable ([EKReminder]?) -> Void)
    func reminder(identifier: String) -> EKReminder?
}

@MainActor
final class EventKitReminderStore: ReminderStoring {
    let eventStore = EKEventStore()

    func requestAccess() async throws -> Bool { try await eventStore.requestFullAccessToReminders() }
    func calendars() -> [EKCalendar] { eventStore.calendars(for: .reminder) }
    func defaultCalendar() -> EKCalendar? { eventStore.defaultCalendarForNewReminders() }
    func save(_ reminder: EKReminder) throws { try eventStore.save(reminder, commit: true) }
    func remove(_ reminder: EKReminder) throws { try eventStore.remove(reminder, commit: true) }
    func fetchReminders(matching predicate: NSPredicate, completion: @escaping @Sendable ([EKReminder]?) -> Void) {
        eventStore.fetchReminders(matching: predicate, completion: completion)
    }
    func reminder(identifier: String) -> EKReminder? { eventStore.calendarItem(withIdentifier: identifier) as? EKReminder }
}

struct ReminderSnapshot: Codable, Equatable, Sendable {
    let identifier: String
    let title: String
    let dueDate: String?
    let dueTime: String?
    let listName: String
    let notes: String?
    let url: String?
    let `repeat`: String?
    let priority: String?
    let isCompleted: Bool
    let revision: String?

    enum CodingKeys: String, CodingKey {
        case identifier, title, notes, url, `repeat`, priority, revision
        case dueDate = "due_date", dueTime = "due_time", listName = "list_name", isCompleted = "is_completed"
    }
}

struct ReminderLookupItem: Encodable, Sendable {
    let identifier: String
    let title: String
    let dueDate: String?
    let dueTime: String?
    let listName: String
    let notes: String?
    let url: String?
    let isCompleted: Bool

    enum CodingKeys: String, CodingKey {
        case identifier, title, notes, url
        case dueDate = "due_date", dueTime = "due_time"
        case listName = "list_name", isCompleted = "is_completed"
    }
}

struct ReminderSearchResult: Encodable, Sendable {
    let items: [ReminderLookupItem]
    let truncated: Bool
}

@MainActor
final class ReminderService {
    private let store: any ReminderStoring

    convenience init() {
        self.init(store: EventKitReminderStore())
    }

    init(store: any ReminderStoring) {
        self.store = store
    }

    enum SaveError: LocalizedError {
        case permission, date, list, url, repeatRule, priority, missing, stale, invalidChange, uncertain(String)

        var errorDescription: String? {
            switch self {
            case .permission: "미리 알림 접근 권한이 없습니다. 시스템 설정에서 권한을 허용해 주세요."
            case .date: "미리 알림 날짜 또는 시간이 올바르지 않습니다."
            case .list: "지정한 미리 알림 목록을 하나로 찾을 수 없습니다."
            case .url: "미리 알림 URL이 올바르지 않습니다."
            case .repeatRule: "지원하지 않는 반복 주기입니다."
            case .priority: "지원하지 않는 우선순위입니다."
            case .missing: "대상 미리 알림을 찾을 수 없습니다. 다시 조회해 주세요."
            case .stale: "승인 대기 중 미리 알림이 변경되었습니다. 다시 조회해 주세요."
            case .invalidChange: "미리 알림 수정 내용이 올바르지 않습니다."
            case .uncertain(let detail): "저장 결과를 확인할 수 없습니다. 미리 알림 앱에서 직접 확인해 주세요. \(detail)"
            }
        }
    }

    func find(query: String, dueDate: String?, listName: String?, includeCompleted: Bool) async throws -> ReminderSearchResult {
        let search = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !search.isEmpty else { throw SearchError.query }
        NSLog("미리 알림 조회 권한 확인 시작")
        guard try await store.requestAccess() else { throw SaveError.permission }
        NSLog("미리 알림 조회 권한 확인 완료")
        if let dueDate {
            let fields = dueDate.split(separator: "-").compactMap { Int($0) }
            guard fields.count == 3, dueDate.count == 10 else { throw SaveError.date }
        }
        let calendars: [EKCalendar]
        if let listName {
            calendars = store.calendars().filter { $0.title == listName }
            if calendars.isEmpty { throw SaveError.list }
        } else {
            calendars = store.calendars()
        }
        let predicate = store.eventStore.predicateForReminders(in: listName == nil ? nil : calendars)
        NSLog("EventKit 미리 알림 검색 시작")
        return try await withCheckedThrowingContinuation { continuation in
            store.fetchReminders(matching: predicate) { @Sendable reminders in
                guard let reminders else {
                    continuation.resume(throwing: SearchError.fetch)
                    return
                }
                let matches = reminders.filter { reminder in
                    guard reminder.title.localizedCaseInsensitiveContains(search),
                          includeCompleted || !reminder.isCompleted else { return false }
                    if let dueDate {
                        let parts = reminder.dueDateComponents
                        guard let year = parts?.year, let month = parts?.month, let day = parts?.day else { return false }
                        return String(format: "%04d-%02d-%02d", year, month, day) == dueDate
                    }
                    return true
                }
                let items = matches.prefix(10).map { reminder in
                    let parts = reminder.dueDateComponents
                    let date: String?
                    if let year = parts?.year, let month = parts?.month, let day = parts?.day {
                        date = String(format: "%04d-%02d-%02d", year, month, day)
                    } else {
                        date = nil
                    }
                    let time: String?
                    if let hour = parts?.hour, let minute = parts?.minute {
                        time = String(format: "%02d:%02d", hour, minute)
                    } else {
                        time = nil
                    }
                    return ReminderLookupItem(identifier: reminder.calendarItemIdentifier,
                                              title: reminder.title, dueDate: date, dueTime: time,
                                              listName: reminder.calendar.title, notes: reminder.notes,
                                              url: reminder.url?.absoluteString, isCompleted: reminder.isCompleted)
                }
                continuation.resume(returning: ReminderSearchResult(items: items, truncated: matches.count > 10))
            }
        }
    }

    enum SearchError: LocalizedError {
        case query, fetch

        var errorDescription: String? {
            switch self {
            case .query: "검색어를 입력해 주세요."
            case .fetch: "미리 알림 목록을 불러오지 못했습니다."
            }
        }
    }

    func snapshot(identifier: String) async throws -> ReminderSnapshot {
        guard try await store.requestAccess() else { throw SaveError.permission }
        guard let reminder = store.reminder(identifier: identifier) else { throw SaveError.missing }
        return try snapshot(of: reminder, identifier: identifier)
    }

    func update(_ proposal: ReminderUpdateProposal) async throws -> String {
        guard proposal.operation == .update else { throw SaveError.invalidChange }
        guard try await store.requestAccess() else { throw SaveError.permission }
        guard let reminder = store.reminder(identifier: proposal.identifier) else { throw SaveError.missing }
        guard try snapshot(of: reminder, identifier: proposal.identifier).revision == proposal.revision else {
            throw SaveError.stale
        }
        let changes = proposal.set
        let clearable: Set<String> = ["due_time", "notes", "url", "repeat", "priority"]
        guard changes.hasChanges || !proposal.clear.isEmpty,
              Set(proposal.clear).count == proposal.clear.count,
              Set(proposal.clear).isSubset(of: clearable),
              !proposal.clear.contains(where: { changes.contains($0) }) else { throw SaveError.invalidChange }
        if let title = changes.title {
            guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw SaveError.invalidChange }
            reminder.title = title
        }
        if let listName = changes.listName {
            let matches = store.calendars().filter { $0.title == listName }
            guard matches.count == 1 else { throw SaveError.list }
            reminder.calendar = matches[0]
        }
        if changes.dueDate != nil || changes.dueTime != nil || proposal.clear.contains("due_time") {
            let old = reminder.dueDateComponents
            let dateText = changes.dueDate ?? old.flatMap { components -> String? in
                guard let year = components.year, let month = components.month, let day = components.day else { return nil }
                return String(format: "%04d-%02d-%02d", year, month, day)
            }
            guard let dateText else { throw SaveError.date }
            let dateParts = dateText.split(separator: "-").compactMap { Int($0) }
            guard dateParts.count == 3, dateText.count == 10 else { throw SaveError.date }
            var components = DateComponents(calendar: Calendar(identifier: .gregorian), timeZone: .current)
            components.year = dateParts[0]
            components.month = dateParts[1]
            components.day = dateParts[2]
            if !proposal.clear.contains("due_time") {
                if let timeText = changes.dueTime {
                    let timeParts = timeText.split(separator: ":").compactMap { Int($0) }
                    guard timeParts.count >= 2, timeParts.count <= 3 else { throw SaveError.date }
                    components.hour = timeParts[0]
                    components.minute = timeParts[1]
                    if timeParts.count == 3 { components.second = timeParts[2] }
                } else {
                    components.hour = old?.hour
                    components.minute = old?.minute
                    components.second = old?.second
                }
            }
            let calendar = Calendar(identifier: .gregorian)
            guard let date = calendar.date(from: components) else { throw SaveError.date }
            let check = calendar.dateComponents(in: .current, from: date)
            guard check.year == components.year, check.month == components.month, check.day == components.day,
                  components.hour == nil || (check.hour == components.hour && check.minute == components.minute) else { throw SaveError.date }
            reminder.dueDateComponents = components
        }
        if let notes = changes.notes { reminder.notes = notes }
        if proposal.clear.contains("notes") { reminder.notes = nil }
        if let address = changes.url {
            guard let url = URL(string: address), ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil else { throw SaveError.url }
            reminder.url = url
        }
        if proposal.clear.contains("url") { reminder.url = nil }
        if changes.repeat != nil || proposal.clear.contains("repeat") {
            reminder.recurrenceRules = nil
            if let frequency = changes.repeat {
                let value: EKRecurrenceFrequency
                switch frequency {
                case "daily": value = .daily
                case "weekly": value = .weekly
                case "monthly": value = .monthly
                case "yearly": value = .yearly
                default: throw SaveError.repeatRule
                }
                reminder.addRecurrenceRule(EKRecurrenceRule(recurrenceWith: value, interval: 1, end: nil))
            }
        }
        if let priority = changes.priority {
            switch priority {
            case "high": reminder.priority = 1
            case "medium": reminder.priority = 5
            case "low": reminder.priority = 9
            default: throw SaveError.priority
            }
        }
        if proposal.clear.contains("priority") { reminder.priority = 0 }
        do { try store.save(reminder) }
        catch { throw SaveError.uncertain(error.localizedDescription) }
        return proposal.identifier
    }

    func delete(_ proposal: ReminderUpdateProposal) async throws -> String {
        guard proposal.operation == .delete else { throw SaveError.invalidChange }
        guard try await store.requestAccess() else { throw SaveError.permission }
        guard let reminder = store.reminder(identifier: proposal.identifier) else { throw SaveError.missing }
        guard try snapshot(of: reminder, identifier: proposal.identifier).revision == proposal.revision else {
            throw SaveError.stale
        }
        do { try store.remove(reminder) }
        catch { throw SaveError.uncertain(error.localizedDescription) }
        return proposal.identifier
    }

    private func snapshot(of reminder: EKReminder, identifier: String) throws -> ReminderSnapshot {
        let parts = reminder.dueDateComponents
        let dueDate = parts.flatMap { value -> String? in
            guard let year = value.year, let month = value.month, let day = value.day else { return nil }
            return String(format: "%04d-%02d-%02d", year, month, day)
        }
        let dueTime = parts.flatMap { value -> String? in
            guard let hour = value.hour, let minute = value.minute else { return nil }
            return String(format: "%02d:%02d", hour, minute)
        }
        let frequency: String?
        switch reminder.recurrenceRules?.first?.frequency {
        case .daily: frequency = "daily"
        case .weekly: frequency = "weekly"
        case .monthly: frequency = "monthly"
        case .yearly: frequency = "yearly"
        default: frequency = nil
        }
        let priority: String?
        switch reminder.priority {
        case 1...4: priority = "high"
        case 5: priority = "medium"
        case 6...9: priority = "low"
        default: priority = nil
        }
        let fields = [identifier, reminder.title ?? "", dueDate ?? "", dueTime ?? "", reminder.calendar.title,
                      reminder.calendar.calendarIdentifier, reminder.notes ?? "", reminder.url?.absoluteString ?? "",
                      frequency ?? "", priority ?? "", String(reminder.isCompleted),
                      String(reminder.priority), String(reminder.lastModifiedDate?.timeIntervalSince1970 ?? 0),
                      String(reminder.recurrenceRules?.count ?? 0)]
        let digest = SHA256.hash(data: Data(fields.joined(separator: "\u{001f}").utf8))
        let revision = digest.map { String(format: "%02x", $0) }.joined()
        return ReminderSnapshot(identifier: identifier, title: reminder.title, dueDate: dueDate, dueTime: dueTime,
                                listName: reminder.calendar.title, notes: reminder.notes, url: reminder.url?.absoluteString,
                                repeat: frequency, priority: priority, isCompleted: reminder.isCompleted, revision: revision)
    }

    func save(_ proposal: ReminderProposal) async throws -> String {
        guard try await store.requestAccess() else { throw SaveError.permission }
        let calendar: EKCalendar
        if let name = proposal.listName {
            let matches = store.calendars().filter { $0.title == name }
            guard matches.count == 1 else { throw SaveError.list }
            calendar = matches[0]
        } else {
            guard let fallback = store.defaultCalendar() else { throw SaveError.list }
            calendar = fallback
        }

        let dateParts = proposal.dueDate.split(separator: "-").compactMap { Int($0) }
        guard dateParts.count == 3 else { throw SaveError.date }
        var components = DateComponents(calendar: Calendar(identifier: .gregorian), timeZone: .current)
        components.year = dateParts[0]
        components.month = dateParts[1]
        components.day = dateParts[2]
        if let time = proposal.dueTime {
            let timeParts = time.split(separator: ":").compactMap { Int($0) }
            guard timeParts.count >= 2, timeParts.count <= 3 else { throw SaveError.date }
            components.hour = timeParts[0]
            components.minute = timeParts[1]
            if timeParts.count == 3 { components.second = timeParts[2] }
        }
        let gregorian = Calendar(identifier: .gregorian)
        guard let date = gregorian.date(from: components) else { throw SaveError.date }
        let roundTrip = gregorian.dateComponents(in: .current, from: date)
        guard roundTrip.year == components.year, roundTrip.month == components.month,
              roundTrip.day == components.day,
              components.hour == nil || (roundTrip.hour == components.hour && roundTrip.minute == components.minute) else { throw SaveError.date }

        let reminder = EKReminder(eventStore: store.eventStore)
        reminder.title = proposal.title
        reminder.calendar = calendar
        reminder.dueDateComponents = components
        reminder.notes = proposal.notes
        if let address = proposal.url {
            guard let url = URL(string: address), ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil else { throw SaveError.url }
            reminder.url = url
        }
        if let frequency = proposal.repeat {
            let value: EKRecurrenceFrequency
            switch frequency {
            case "daily": value = .daily
            case "weekly": value = .weekly
            case "monthly": value = .monthly
            case "yearly": value = .yearly
            default: throw SaveError.repeatRule
            }
            reminder.addRecurrenceRule(EKRecurrenceRule(recurrenceWith: value, interval: 1, end: nil))
        }
        if let priority = proposal.priority {
            switch priority {
            case "high": reminder.priority = 1
            case "medium": reminder.priority = 5
            case "low": reminder.priority = 9
            default: throw SaveError.priority
            }
        }
        do {
            try store.save(reminder)
        } catch {
            throw SaveError.uncertain(error.localizedDescription)
        }
        let identifier = reminder.calendarItemIdentifier
        guard !identifier.isEmpty else {
            throw SaveError.uncertain("저장 후 식별자를 받지 못했습니다.")
        }
        return identifier
    }
}
