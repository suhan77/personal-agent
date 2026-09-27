import EventKit
import Foundation

@MainActor
final class FakeReminderStore: ReminderStoring {
    let eventStore = EKEventStore()
    var granted = true
    var savedReminder: EKReminder?
    var saveCalls = 0
    var fetchedReminders: [EKReminder] = []
    var callbackOnBackground = false
    var existingReminder: EKReminder?
    var shouldFailSave = true
    var shouldFailRemove = false
    var removeCalls = 0
    var removedReminder: EKReminder?
    var defaultList: EKCalendar? { EKCalendar(for: .reminder, eventStore: eventStore) }

    func requestAccess() async throws -> Bool { granted }
    func calendars() -> [EKCalendar] { [] }
    func defaultCalendar() -> EKCalendar? { defaultList }
    func save(_ reminder: EKReminder) throws {
        saveCalls += 1
        savedReminder = reminder
        if shouldFailSave {
            throw NSError(domain: "test", code: 1, userInfo: [NSLocalizedDescriptionKey: "simulated save failure"])
        }
    }
    func reminder(identifier: String) -> EKReminder? { identifier == "test-id" ? existingReminder : nil }
    func remove(_ reminder: EKReminder) throws {
        removeCalls += 1
        removedReminder = reminder
        if shouldFailRemove {
            throw NSError(domain: "test", code: 2, userInfo: [NSLocalizedDescriptionKey: "simulated remove failure"])
        }
        existingReminder = nil
    }
    func fetchReminders(matching predicate: NSPredicate, completion: @escaping @Sendable ([EKReminder]?) -> Void) {
        if callbackOnBackground {
            DispatchQueue.global().async { completion([]) }
        } else {
            completion(fetchedReminders)
        }
    }
}

@main
struct ReminderServiceChecks {
    @MainActor
    static func main() async throws {
        let proposal = try JSONDecoder().decode(ReminderProposal.self, from: Data("""
        {"proposal_id":"r-1","title":"발표 준비","due_date":"2026-09-29"}
        """.utf8))

        let denied = FakeReminderStore()
        denied.granted = false
        do {
            _ = try await ReminderService(store: denied).save(proposal)
            preconditionFailure("permission denial was ignored")
        } catch ReminderService.SaveError.permission {
            precondition(denied.saveCalls == 0)
        }

        let impossibleDate = try JSONDecoder().decode(ReminderProposal.self, from: Data("""
        {"proposal_id":"invalid","title":"잘못된 날짜","due_date":"2026-02-30"}
        """.utf8))
        let dateStore = FakeReminderStore()
        do {
            _ = try await ReminderService(store: dateStore).save(impossibleDate)
            preconditionFailure("invalid date was accepted")
        } catch ReminderService.SaveError.date {
            precondition(dateStore.saveCalls == 0)
        }

        let missingList = try JSONDecoder().decode(ReminderProposal.self, from: Data("""
        {"proposal_id":"missing-list","title":"발표 준비","due_date":"2026-09-29","list_name":"없는 목록"}
        """.utf8))
        let listStore = FakeReminderStore()
        do {
            _ = try await ReminderService(store: listStore).save(missingList)
            preconditionFailure("missing list was accepted")
        } catch ReminderService.SaveError.list {
            precondition(listStore.saveCalls == 0)
        }

        let failing = FakeReminderStore()
        do {
            _ = try await ReminderService(store: failing).save(proposal)
            preconditionFailure("save failure was ignored")
        } catch ReminderService.SaveError.uncertain {
            precondition(failing.saveCalls == 1)
            precondition(failing.savedReminder?.title == "발표 준비")
            precondition(failing.savedReminder?.dueDateComponents?.hour == nil)
        }

        let detailed = try JSONDecoder().decode(ReminderProposal.self, from: Data("""
        {"proposal_id":"r-2","title":"발표 준비","due_date":"2026-09-29",
         "due_time":"15:00:00","notes":"자료 확인","url":"https://example.com",
         "repeat":"weekly","priority":"high"}
        """.utf8))
        let detailedStore = FakeReminderStore()
        do {
            _ = try await ReminderService(store: detailedStore).save(detailed)
            preconditionFailure("save failure was ignored")
        } catch ReminderService.SaveError.uncertain {
            let saved = detailedStore.savedReminder
            precondition(saved?.dueDateComponents?.hour == 15)
            precondition(saved?.dueDateComponents?.minute == 0)
            precondition(saved?.notes == "자료 확인")
            precondition(saved?.url?.absoluteString == "https://example.com")
            precondition(saved?.priority == 1)
            precondition(saved?.recurrenceRules?.first?.frequency == .weekly)
        }

        let searchStore = FakeReminderStore()
        let matching = EKReminder(eventStore: searchStore.eventStore)
        matching.calendar = searchStore.defaultList
        matching.title = "발표 준비"
        matching.dueDateComponents = DateComponents(year: 2026, month: 9, day: 29)
        let completed = EKReminder(eventStore: searchStore.eventStore)
        completed.calendar = searchStore.defaultList
        completed.title = "발표 완료"
        completed.isCompleted = true
        completed.dueDateComponents = DateComponents(year: 2026, month: 9, day: 29)
        let unrelated = EKReminder(eventStore: searchStore.eventStore)
        unrelated.calendar = searchStore.defaultList
        unrelated.title = "장보기"
        searchStore.fetchedReminders = [matching, completed, unrelated]
        let found = try await ReminderService(store: searchStore).find(
            query: "발표", dueDate: "2026-09-29", listName: nil, includeCompleted: false
        )
        precondition(found.items.count == 1 && !found.truncated)
        precondition(found.items[0].title == "발표 준비")
        precondition(found.items[0].dueDate == "2026-09-29")
        let all = try await ReminderService(store: searchStore).find(
            query: "발표", dueDate: nil, listName: nil, includeCompleted: true
        )
        precondition(all.items.count == 2)
        do {
            _ = try await ReminderService(store: searchStore).find(
                query: "발표", dueDate: nil, listName: "없는 목록", includeCompleted: false
            )
            preconditionFailure("missing list was reported as empty search")
        } catch ReminderService.SaveError.list {}
        let backgroundStore = FakeReminderStore()
        backgroundStore.callbackOnBackground = true
        let backgroundResult = try await ReminderService(store: backgroundStore).find(
            query: "발표", dueDate: nil, listName: nil, includeCompleted: false
        )
        precondition(backgroundResult.items.isEmpty)

        let updateStore = FakeReminderStore()
        let existing = EKReminder(eventStore: updateStore.eventStore)
        existing.calendar = updateStore.defaultList
        existing.title = "발표 준비"
        existing.notes = "기존 메모"
        existing.dueDateComponents = DateComponents(year: 2026, month: 9, day: 29)
        updateStore.existingReminder = existing
        let updateService = ReminderService(store: updateStore)
        let snapshot = try await updateService.snapshot(identifier: "test-id")
        let updateJSON = """
        {"proposal_id":"update-1","identifier":"test-id","revision":"\(snapshot.revision ?? "")",
         "before":{},"after":{},"set":{"title":"새 제목"},"clear":["notes"]}
        """
        // The service only needs the revision and patch; the UI receives full before/after snapshots.
        let beforeJSON = try String(data: JSONEncoder().encode(snapshot), encoding: .utf8)!
        let updateData = updateJSON.replacingOccurrences(of: "\"before\":{}", with: "\"before\":\(beforeJSON)")
            .replacingOccurrences(of: "\"after\":{}", with: "\"after\":\(beforeJSON)")
        let updateProposal = try JSONDecoder().decode(ReminderUpdateProposal.self, from: Data(updateData.utf8))
        updateStore.shouldFailSave = false
        _ = try await updateService.update(updateProposal)
        precondition(updateStore.saveCalls == 1)
        precondition(existing.title == "새 제목")
        precondition(existing.notes == nil)
        precondition(existing.dueDateComponents?.day == 29)
        do {
            _ = try await updateService.update(updateProposal)
            preconditionFailure("stale update was accepted")
        } catch ReminderService.SaveError.stale {
            precondition(updateStore.saveCalls == 1)
        }

        let deniedUpdate = FakeReminderStore()
        deniedUpdate.existingReminder = existing
        deniedUpdate.granted = false
        do {
            _ = try await ReminderService(store: deniedUpdate).update(updateProposal)
            preconditionFailure("update permission denial was ignored")
        } catch ReminderService.SaveError.permission {
            precondition(deniedUpdate.saveCalls == 0)
        }

        let deleteStore = FakeReminderStore()
        let toDelete = EKReminder(eventStore: deleteStore.eventStore)
        toDelete.calendar = deleteStore.defaultList
        toDelete.title = "삭제 대상"
        toDelete.dueDateComponents = DateComponents(year: 2026, month: 9, day: 29)
        deleteStore.existingReminder = toDelete
        let deleteService = ReminderService(store: deleteStore)
        let deleteSnapshot = try await deleteService.snapshot(identifier: "test-id")
        let deleteBefore = try String(data: JSONEncoder().encode(deleteSnapshot), encoding: .utf8)!
        let deleteJSON = """
        {"proposal_id":"delete-1","operation":"delete","identifier":"test-id","revision":"\(deleteSnapshot.revision ?? "")",
         "before":\(deleteBefore),"after":\(deleteBefore),"set":{},"clear":[]}
        """
        let deleteProposal = try JSONDecoder().decode(ReminderUpdateProposal.self, from: Data(deleteJSON.utf8))
        let staleJSON = deleteJSON.replacingOccurrences(of: deleteSnapshot.revision ?? "", with: "old-revision")
        let staleProposal = try JSONDecoder().decode(ReminderUpdateProposal.self, from: Data(staleJSON.utf8))
        do {
            _ = try await deleteService.delete(staleProposal)
            preconditionFailure("stale deletion was accepted")
        } catch ReminderService.SaveError.stale { precondition(deleteStore.removeCalls == 0) }
        let deniedDelete = FakeReminderStore()
        deniedDelete.existingReminder = toDelete
        deniedDelete.granted = false
        do {
            _ = try await ReminderService(store: deniedDelete).delete(deleteProposal)
            preconditionFailure("delete permission denial was ignored")
        } catch ReminderService.SaveError.permission { precondition(deniedDelete.removeCalls == 0) }
        deleteStore.shouldFailRemove = true
        do {
            _ = try await deleteService.delete(deleteProposal)
            preconditionFailure("uncertain deletion was ignored")
        } catch ReminderService.SaveError.uncertain { precondition(deleteStore.removeCalls == 1) }
        deleteStore.shouldFailRemove = false
        _ = try await deleteService.delete(deleteProposal)
        precondition(deleteStore.removeCalls == 2 && deleteStore.existingReminder == nil)
        precondition(deleteStore.removedReminder === toDelete)
        do {
            _ = try await deleteService.delete(deleteProposal)
            preconditionFailure("duplicate deletion was accepted")
        } catch ReminderService.SaveError.missing { precondition(deleteStore.removeCalls == 2) }
        print("Reminder service checks passed")
    }
}
