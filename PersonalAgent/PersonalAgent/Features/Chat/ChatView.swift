import SwiftUI

struct ChatView: View {
    @EnvironmentObject private var chatStore: ChatStore

    var body: some View {
        VStack(spacing: 0) {
            if let conversation = chatStore.selectedConversation {
                MessageList(messages: conversation.messages, isGenerating: chatStore.isGeneratingReply)
                Divider()
                Composer()
            } else {
                ContentUnavailableView(
                    "대화를 선택하세요",
                    systemImage: "message",
                    description: Text("왼쪽 상단의 새 대화 버튼으로 대화를 시작할 수 있습니다.")
                )
            }
        }
        .navigationTitle(chatStore.selectedConversation?.title ?? "Personal Agent")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                HStack(spacing: 8) {
                    Text(chatStore.workingDirectory?.lastPathComponent ?? "없음")
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)

                    Button(action: chatStore.chooseWorkingDirectory) {
                        Image(systemName: "folder")
                            .frame(width: 28, height: 28)
                    }
                    .buttonStyle(.bordered)
                    .clipShape(Circle())
                }
            }
        }
    }
}

private struct MessageList: View {
    let messages: [ChatMessage]
    let isGenerating: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 18) {
                    ForEach(messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }

                    if isGenerating {
                        HStack(spacing: 8) {
                            ProgressView()
                                .controlSize(.small)
                            Text("로컬 모델이 답변을 준비하고 있습니다…")
                                .foregroundStyle(.secondary)
                            Spacer()
                        }
                        .padding(.horizontal, 24)
                        .id("generating")
                    }
                }
                .padding(.vertical, 24)
            }
            .onChange(of: messages.count) { _, _ in
                scrollToLastMessage(using: proxy)
            }
            .onChange(of: isGenerating) { _, _ in
                scrollToLastMessage(using: proxy)
            }
        }
    }

    private func scrollToLastMessage(using proxy: ScrollViewProxy) {
        withAnimation {
            if isGenerating {
                proxy.scrollTo("generating", anchor: .bottom)
            } else if let lastMessage = messages.last {
                proxy.scrollTo(lastMessage.id, anchor: .bottom)
            }
        }
    }
}

private struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            if message.role == .assistant {
                Image(systemName: "sparkles")
                    .foregroundStyle(.tint)
                    .frame(width: 28, height: 28)
                    .background(.quaternary, in: Circle())
            } else {
                Spacer(minLength: 60)
            }

            Text(message.content)
                .textSelection(.enabled)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(backgroundColor, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

            if message.role == .assistant {
                Spacer(minLength: 60)
            }
        }
        .padding(.horizontal, 24)
    }

    private var backgroundColor: Color {
        message.role == .user ? .accentColor.opacity(0.18) : .secondary.opacity(0.12)
    }
}

private struct Composer: View {
    @EnvironmentObject private var chatStore: ChatStore
    @FocusState private var isFocused: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("메시지를 입력하세요", text: $chatStore.draft, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .submitLabel(.send)
                .focused($isFocused)
                .onKeyPress(.return, phases: .down) { keyPress in
                    if keyPress.modifiers.contains(.shift) {
                        chatStore.draft.append("\n")
                    } else {
                        chatStore.sendDraft()
                    }
                    return .handled
                }

            Button(action: chatStore.sendDraft) {
                Image(systemName: "arrow.up")
                    .fontWeight(.semibold)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.borderedProminent)
            .clipShape(Circle())
            .disabled(chatStore.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || chatStore.isGeneratingReply)
            .help("메시지 보내기")
        }
        .padding(16)
        .background(.bar)
        .onAppear { isFocused = true }
    }
}
