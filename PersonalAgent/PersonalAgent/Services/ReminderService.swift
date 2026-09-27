import EventKit
import Foundation

@MainActor
protocol ReminderStoring {
    var eventStore: EKEventStore { get }
    func requestAccess() async throws -> Bool
    func calendars() -> [EKCalendar]
    func defaultCalendar() -> EKCalendar?
    func save(_ reminder: EKReminder) throws
    func fetchReminders(matching predicate: NSPredicate, completion: @escaping @Sendable ([EKReminder]?) -> Void)
}

@MainActor
final class EventKitReminderStore: ReminderStoring {
    let eventStore = EKEventStore()

    func requestAccess() async throws -> Bool { try await eventStore.requestFullAccessToReminders() }
    func calendars() -> [EKCalendar] { eventStore.calendars(for: .reminder) }
    func defaultCalendar() -> EKCalendar? { eventStore.defaultCalendarForNewReminders() }
    func save(_ reminder: EKReminder) throws { try eventStore.save(reminder, commit: true) }
    func fetchReminders(matching predicate: NSPredicate, completion: @escaping @Sendable ([EKReminder]?) -> Void) {
        eventStore.fetchReminders(matching: predicate, completion: completion)
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
        case permission, date, list, url, repeatRule, priority, uncertain(String)

        var errorDescription: String? {
            switch self {
            case .permission: "미리 알림 접근 권한이 없습니다. 시스템 설정에서 권한을 허용해 주세요."
            case .date: "미리 알림 날짜 또는 시간이 올바르지 않습니다."
            case .list: "지정한 미리 알림 목록을 하나로 찾을 수 없습니다."
            case .url: "미리 알림 URL이 올바르지 않습니다."
            case .repeatRule: "지원하지 않는 반복 주기입니다."
            case .priority: "지원하지 않는 우선순위입니다."
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
