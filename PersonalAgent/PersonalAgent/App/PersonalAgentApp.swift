import SwiftUI

@main
struct PersonalAgentApp: App {
    @StateObject private var chatStore = ChatStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(chatStore)
        }
        .defaultSize(width: 1_100, height: 720)
    }
}
