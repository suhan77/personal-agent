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
    @EnvironmentObject private var chatStore: ChatStore
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

            VStack(alignment: .leading, spacing: 10) {
                Text(message.content).textSelection(.enabled)
                if let proposal = message.proposal {
                    Text(proposal.path).font(.headline)
                    ScrollView(.horizontal) {
                        Text(proposal.diff).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    }
                    .frame(maxHeight: 300)
                    if proposal.status == .pending {
                        HStack {
                            Button("승인") { chatStore.reviewProposal(message.id, approve: true) }
                            Button("거부") { chatStore.reviewProposal(message.id, approve: false) }
                        }
                        .disabled(chatStore.isGeneratingReply)
                    } else {
                        Text(proposal.status == .approved ? "적용됨" : proposal.status == .rejected ? "거부됨" : "실패")
                            .foregroundStyle(.secondary)
                    }
                }
                if let reminder = message.reminderProposal {
                    Text(reminder.title).font(.headline)
                    Text("날짜: \(reminder.dueDate)" + (reminder.dueTime.map { " \($0) (\(TimeZone.current.identifier))" } ?? " (종일)"))
                    if let notes = reminder.notes { Text("메모: \(notes)") }
                    if let url = reminder.url { Text("URL: \(url)") }
                    Text("목록: \(reminder.listName ?? "기본 목록")")
                    if let frequency = reminder.repeat {
                        Text("반복: \(["daily": "매일", "weekly": "매주", "monthly": "매월", "yearly": "매년"][frequency] ?? frequency)")
                    }
                    if let priority = reminder.priority {
                        Text("우선순위: \(["low": "낮음", "medium": "보통", "high": "높음"][priority] ?? priority)")
                    }
                    if reminder.status == .pending {
                        HStack {
                            Button("승인") { chatStore.reviewReminderProposal(message.id, approve: true) }
                            Button("거부") { chatStore.reviewReminderProposal(message.id, approve: false) }
                        }
                        .disabled(chatStore.isGeneratingReply)
                    } else if reminder.status == .saving {
                        Text("저장 결과 확인 필요 · 자동 재저장 안 함")
                            .foregroundStyle(.orange)
                        Text("미리 알림 앱에서 이 항목이 실제 등록됐는지 확인한 후 선택하세요.")
                            .foregroundStyle(.secondary)
                        if let detail = reminder.failureMessage { Text(detail).foregroundStyle(.secondary) }
                        HStack {
                            Button("등록됨 확인") { chatStore.resolveUncertainReminder(message.id, wasSaved: true) }
                            Button("등록 안 됨 확인") { chatStore.resolveUncertainReminder(message.id, wasSaved: false) }
                        }
                        .disabled(chatStore.isGeneratingReply)
                    } else {
                        Text(reminder.status == .approved ? "등록됨" : reminder.status == .rejected ? "거부됨" : "등록 실패")
                            .foregroundStyle(.secondary)
                        if let detail = reminder.failureMessage, reminder.status == .failed { Text(detail).foregroundStyle(.secondary) }
                        if !reminder.resultDelivered {
                            Button("결과 전달 재시도") { chatStore.retryReminderResult(message.id) }
                                .disabled(chatStore.isGeneratingReply)
                        }
                    }
                }
            }
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
