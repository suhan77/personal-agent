import SwiftUI

struct ContentView: View {
    var body: some View {
        NavigationSplitView {
            ConversationSidebar()
                .navigationSplitViewColumnWidth(min: 220, ideal: 260)
        } detail: {
            ChatView()
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(ChatStore())
}
