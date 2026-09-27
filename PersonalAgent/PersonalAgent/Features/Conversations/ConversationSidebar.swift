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
