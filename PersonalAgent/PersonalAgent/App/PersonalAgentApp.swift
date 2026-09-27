import SwiftUI

@main
struct PersonalAgentApp: App {
    @StateObject private var chatStore = ChatStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(chatStore)
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                    chatStore.shutdown()
                }
        }
        .defaultSize(width: 1_100, height: 720)
    }
}
