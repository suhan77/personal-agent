import SwiftUI

struct ConversationSidebar: View {
    @EnvironmentObject private var chatStore: ChatStore

    var body: some View {
        List(selection: $chatStore.selectedConversationID) {
            Section("대화") {
                ForEach(chatStore.conversations) { conversation in
                    Label(conversation.title, systemImage: "message")
                        .tag(conversation.id)
                        .lineLimit(1)
                }
            }
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
