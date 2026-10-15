import Foundation

// Uses a unique temporary Keychain entry and removes it on completion.
@main
struct APIKeyStoreChecks {
    static func main() {
        let store = APIKeyStore(service: "PersonalAgent.Test." + UUID().uuidString)
        defer { try? store.delete() }
        do {
            guard try !store.containsKey() else { fatalError("Expected empty store") }
            try store.save("  test-placeholder-one  ")
            guard try store.containsKey(), try store.load() == "test-placeholder-one" else { fatalError("Save/read mismatch") }
            try store.save("test-placeholder-two")
            guard try store.load() == "test-placeholder-two" else { fatalError("Update mismatch") }
            do {
                try store.save(" ")
                fatalError("Empty key accepted")
            } catch { }
            guard try store.load() == "test-placeholder-two" else { fatalError("Invalid save replaced key") }
            try store.delete()
            guard try !store.containsKey(), try store.load() == nil else { fatalError("Delete mismatch") }
            try store.delete()
            print("Keychain lifecycle checks passed")
        } catch {
            print("Keychain check failed: \(error.localizedDescription)")
            exit(1)
        }
    }
}
