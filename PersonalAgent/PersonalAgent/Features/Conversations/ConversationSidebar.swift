import SwiftUI

struct ConversationSidebar: View {
    @EnvironmentObject private var chatStore: ChatStore

    @State private var showsSettings = false

    var body: some View {
        List(selection: $chatStore.selectedConversationID) {
            Section("대화") {
                ForEach(chatStore.conversations) { conversation in
                    Label(conversation.title, systemImage: "message")
                        .tag(conversation.id)
                        .lineLimit(1)
                        .contextMenu {
                            Button(role: .destructive) {
                                chatStore.deleteConversation(conversation.id)
                            } label: {
                                Label("대화 삭제", systemImage: "trash")
                            }
                        }
                }
                .onDelete { offsets in
                    let conversationIDs = offsets.map { chatStore.conversations[$0].id }
                    for conversationID in conversationIDs {
                        chatStore.deleteConversation(conversationID)
                    }
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                Divider()
                Button {
                    showsSettings = true
                } label: {
                    Label("설정", systemImage: "gearshape")
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help("OpenAI API 키 설정")
            }
            .background(.bar)
        }
        .sheet(isPresented: $showsSettings) {
            APISettingsView()
                .environmentObject(chatStore)
        }
        .navigationTitle("Personal Agent")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(action: chatStore.createConversation) {
                    Label("새 대화", systemImage: "square.and.pencil")
                }
                .help("새 대화")
            }
        }
    }
}

private struct APISettingsView: View {
    @EnvironmentObject private var chatStore: ChatStore
    @Environment(\.dismiss) private var dismiss
    @State private var apiKey = ""
    @State private var hasSavedKey = false
    @State private var feedback: String?
    @State private var hasError = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("설정").font(.title2.bold())
                Spacer()
                Button("닫기") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            Divider()
            Text("OpenAI").font(.headline)
            Label(hasSavedKey ? "API 키가 저장되어 있습니다" : "등록된 API 키가 없습니다",
                  systemImage: hasSavedKey ? "checkmark.circle.fill" : "key")
                .foregroundStyle(.secondary)
            SecureField(hasSavedKey ? "교체할 API 키 입력" : "API 키 입력", text: $apiKey)
                .textFieldStyle(.roundedBorder)
                .disabled(chatStore.isGeneratingReply)
                .onSubmit { if canSave { saveKey() } }
            Text("키는 이 Mac의 키체인에 저장됩니다. GPT-6 Luna 사용 시 대화 내용이 OpenAI로 전송되며 API 사용료가 발생합니다.")
                .font(.callout)
                .foregroundStyle(.secondary)
            if chatStore.isGeneratingReply {
                Text("답변 생성이 끝나면 키를 변경할 수 있습니다.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if let feedback {
                Text(feedback)
                    .font(.callout)
                    .foregroundStyle(hasError ? Color.red : Color.secondary)
                    .textSelection(.enabled)
            }
            HStack {
                Button("키 삭제", role: .destructive) { deleteKey() }
                    .disabled(!hasSavedKey || chatStore.isGeneratingReply)
                Spacer()
                Button(hasSavedKey ? "키 교체" : "저장", action: saveKey)
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSave)
            }
        }
        .padding(24)
        .frame(width: 440)
        .onAppear {
            do { hasSavedKey = try APIKeyStore().containsKey() }
            catch { showError(error) }
        }
        .onDisappear { apiKey = "" }
    }

    private var canSave: Bool {
        !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !chatStore.isGeneratingReply
    }

    private func saveKey() {
        do {
            try chatStore.saveOpenAIKey(apiKey)
            apiKey = ""
            hasSavedKey = true
            hasError = false
            feedback = "저장했습니다. 모델 메뉴에서 GPT-6 Luna를 선택하세요."
        } catch { showError(error) }
    }

    private func deleteKey() {
        do {
            try chatStore.deleteOpenAIKey()
            apiKey = ""
            hasSavedKey = false
            hasError = false
            feedback = "API 키를 삭제했습니다."
        } catch { showError(error) }
    }

    private func showError(_ error: Error) {
        hasError = true
        feedback = error.localizedDescription
    }
}
