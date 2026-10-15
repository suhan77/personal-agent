import AppKit
import EventKit
import CryptoKit

struct CalendarToolArguments: Decodable {
    let query: String?
    let due_date: String?
    let list_name: String?
    let include_completed: Bool?
    let identifier: String?
    let revision: String?
    let title: String?
    let start: String?
    let end: String?
    let location: String?
    let notes: String?
    let calendar_name: String?
}

struct CalendarEventItem: Encodable, Equatable {
    let identifier: String
    let revision: String
    let title: String
    let start: String
    let end: String
    let calendar_name: String
    let location: String
    let notes: String
    let is_all_day: Bool
    let is_recurring: Bool
}

struct CalendarToolResult: Encodable {
    var status: String? = nil
    var items: [CalendarEventItem] = []
    var truncated: Bool = false
}

@MainActor
final class CalendarService {
    private let store = EKEventStore()
    // Only identifiers returned by this app's search can be changed.
    private var found: [String: String] = [:]
    private let formatter = ISO8601DateFormatter()

    private func fail(_ message: String) -> NSError {
        NSError(domain: "CalendarService", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
    }

    private func date(_ value: String?) throws -> Date {
        guard let value else { throw fail("시작·종료 시각이 필요합니다") }
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        guard let date = formatter.date(from: value) else { throw fail("시간대가 포함된 ISO 8601 시각이 필요합니다") }
        return date
    }

    private func item(_ event: EKEvent) -> CalendarEventItem {
        formatter.formatOptions = [.withInternetDateTime]
        let values = [event.eventIdentifier ?? "", event.title ?? "", formatter.string(from: event.startDate),
                      formatter.string(from: event.endDate), event.calendar.calendarIdentifier,
                      event.location ?? "", event.notes ?? "", String(event.isAllDay),
                      String(event.hasRecurrenceRules), String(event.lastModifiedDate?.timeIntervalSince1970 ?? 0)]
        let revision = SHA256.hash(data: Data(values.joined(separator: "\u{0}").utf8)).map { String(format: "%02x", $0) }.joined()
        return CalendarEventItem(identifier: values[0], revision: revision, title: values[1],
                                 start: values[2], end: values[3], calendar_name: event.calendar.title,
                                 location: values[5], notes: values[6], is_all_day: event.isAllDay,
                                 is_recurring: event.hasRecurrenceRules)
    }

    func handle(tool: String, arguments a: CalendarToolArguments, isActive: () -> Bool = { true }) async throws -> CalendarToolResult {
        let deadline = Date().addingTimeInterval(110)
        guard try await store.requestFullAccessToEvents() else { throw fail("캘린더 접근 권한이 필요합니다") }
        if tool == "find_calendar_events" {
            let start = try date(a.start), end = try date(a.end)
            guard end > start, end.timeIntervalSince(start) <= 366 * 86400 else { throw fail("조회 기간은 366일 이하여야 합니다") }
            let predicate = store.predicateForEvents(withStart: start, end: end, calendars: nil)
            let matches = store.events(matching: predicate).filter {
                (a.query ?? "").isEmpty || ($0.title ?? "").localizedCaseInsensitiveContains(a.query ?? "")
            }.sorted { $0.startDate < $1.startDate }
            let items = matches.prefix(50).map { item($0) }
            for value in items { found[value.identifier] = value.revision }
            return CalendarToolResult(items: items, truncated: matches.count > 50)
        }
        let updating = tool == "update_calendar_event"
        guard updating || tool == "create_calendar_event" else { throw fail("지원하지 않는 캘린더 도구입니다") }
        let event: EKEvent
        var before: CalendarEventItem?
        if updating {
            guard let id = a.identifier, let revision = a.revision, found[id] == revision,
                  let existing = store.event(withIdentifier: id), item(existing).revision == revision else {
                throw fail("일정이 변경되었거나 조회되지 않았습니다. 다시 조회하세요")
            }
            guard !existing.hasRecurrenceRules, !existing.isAllDay, !existing.hasAttendees,
                  existing.calendar.allowsContentModifications else { throw fail("반복·종일·참석자 일정 또는 읽기 전용 일정은 수정할 수 없습니다") }
            before = item(existing)
            event = EKEvent(eventStore: store)
            event.calendar = existing.calendar
            event.title = existing.title
            event.startDate = existing.startDate
            event.endDate = existing.endDate
            event.location = existing.location
            event.notes = existing.notes
        } else {
            event = EKEvent(eventStore: store)
            if let name = a.calendar_name {
                let calendars = store.calendars(for: .event).filter { $0.title == name && $0.allowsContentModifications }
                guard calendars.count == 1 else { throw fail("쓰기 가능한 캘린더 이름을 정확히 지정하세요") }
                event.calendar = calendars[0]
            } else {
                guard let calendar = store.defaultCalendarForNewEvents, calendar.allowsContentModifications else { throw fail("쓰기 가능한 기본 캘린더가 없습니다") }
                event.calendar = calendar
            }
            guard a.title != nil, a.start != nil, a.end != nil else { throw fail("제목과 시작·종료가 필요합니다") }
        }
        if let title = a.title {
            guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw fail("제목이 필요합니다") }
            event.title = title
        }
        if let start = a.start { event.startDate = try date(start) }
        if let end = a.end { event.endDate = try date(end) }
        if let location = a.location { event.location = location }
        if let notes = a.notes { event.notes = notes }
        guard event.endDate > event.startDate else { throw fail("종료는 시작 이후여야 합니다") }
        let after = item(event)
        func description(_ value: CalendarEventItem) -> String {
            "\(value.title)\n\(value.start) ~ \(value.end)\n캘린더: \(value.calendar_name)\n장소: \(value.location)\n메모: \(value.notes)"
        }
        let alert = NSAlert()
        alert.messageText = updating ? "캘린더 일정을 수정할까요?" : "캘린더 일정을 추가할까요?"
        alert.informativeText = before.map { "변경 전\n\(description($0))\n\n변경 후\n" } .map { $0 + description(after) } ?? description(after)
        alert.addButton(withTitle: "저장")
        alert.addButton(withTitle: "취소")
        alert.buttons.first?.keyEquivalent = ""
        guard alert.runModal() == .alertFirstButtonReturn else {
            store.reset()
            return CalendarToolResult(status: "rejected")
        }
        guard isActive(), Date() < deadline else {
            store.reset()
            throw fail("요청이 만료되었습니다. 다시 요청하세요")
        }
        // Refresh after review so edits made in Calendar while reviewing are detected.
        var target = event
        if let before {
            store.refreshSourcesIfNecessary()
            guard let current = store.event(withIdentifier: before.identifier), item(current).revision == before.revision else {
                store.reset()
                throw fail("승인 중 일정이 변경되었습니다. 다시 조회하세요")
            }
            current.title = event.title
            current.startDate = event.startDate
            current.endDate = event.endDate
            current.location = event.location
            current.notes = event.notes
            target = current
        }
        do { try store.save(target, span: .thisEvent, commit: true) }
        catch { store.reset(); throw error }
        if let before { found.removeValue(forKey: before.identifier) }
        return CalendarToolResult(status: "saved", items: [item(target)])
    }
}
