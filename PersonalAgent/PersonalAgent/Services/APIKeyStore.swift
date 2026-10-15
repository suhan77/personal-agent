import Foundation
import Security

/// Credentials stay in Keychain; only the worker receives the value at launch.
struct APIKeyStore {
    private let service: String
    private let account = "openai-api-key"

    init(service: String = (Bundle.main.bundleIdentifier ?? "PersonalAgent") + ".credentials") {
        self.service = service
    }

    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    private func check(_ status: OSStatus) throws {
        guard status == errSecSuccess else {
            let detail = SecCopyErrorMessageString(status, nil) as String? ?? "오류 코드 \(status)"
            throw NSError(domain: "APIKeyStore", code: Int(status),
                          userInfo: [NSLocalizedDescriptionKey: "키체인에 접근하지 못했습니다: \(detail)"])
        }
    }

    func containsKey() throws -> Bool {
        var attributes = query
        attributes[kSecReturnAttributes as String] = true
        attributes[kSecMatchLimit as String] = kSecMatchLimitOne
        let status = SecItemCopyMatching(attributes as CFDictionary, nil)
        if status == errSecItemNotFound { return false }
        try check(status)
        return true
    }

    func load() throws -> String? {
        var attributes = query
        attributes[kSecReturnData as String] = true
        attributes[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(attributes as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        try check(status)
        guard let data = result as? Data, let key = String(data: data, encoding: .utf8) else {
            throw NSError(domain: "APIKeyStore", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "저장된 API 키를 읽을 수 없습니다."])
        }
        return key
    }

    func save(_ value: String) throws {
        let key = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty, !key.contains(where: { $0.isWhitespace }) else {
            throw NSError(domain: "APIKeyStore", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "공백이 없는 API 키를 입력하세요."])
        }
        let data = Data(key.utf8)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var attributes = query
            attributes[kSecValueData as String] = data
            attributes[kSecAttrLabel as String] = "Personal Agent OpenAI API Key"
            attributes[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            try check(SecItemAdd(attributes as CFDictionary, nil))
        } else {
            try check(status)
        }
    }

    func delete() throws {
        let status = SecItemDelete(query as CFDictionary)
        if status != errSecItemNotFound { try check(status) }
    }
}
