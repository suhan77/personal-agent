# Granite 4.2 3B: PyTorch MPS vs MLX

Measured on 2026-10-15, Apple M2 Pro, 32 GB unified memory. Both engines use BF16, thinking disabled, greedy decoding and a maximum of 256 generated tokens. MLX LM 0.32.0 / MLX 0.32.4. Each engine runs in a separate process, loads once, then runs the chat case twice followed by the calendar case twice. No tool is executed, and no existing conversation or API key is used.

| Measurement | PyTorch MPS | MLX BF16 |
| --- | ---: | ---: |
| Model load | 5.04 s | 3.55 s |
| Short greeting, first invocation | 2.04 s | 2.35 s |
| Short greeting, second invocation | 1.37 s | 0.93 s |
| Calendar tool call, first invocation | 9.42 s | 6.19 s |
| Calendar tool call, second invocation | 9.25 s | 6.06 s |
| Calendar decode throughput, second invocation | 16.35 tokens/s | 24.18 tokens/s |

The calendar prompt has 2,157 input tokens and produces 74 output tokens on both engines. Both select `find_calendar_events` with the same 18:00–19:00 interval. The short greeting has 424 input tokens and 7 output tokens on both engines. MLX reduces elapsed time on the second invocation by approximately 33% for the greeting and 35% for the calendar case (approximately 1.5x throughput in wall time). The first greeting is slower on MLX, consistent with first-use initialization overhead.

This is a small smoke benchmark, not a statistical performance study. The calendar timing covers only the initial tool-call generation, not an entire calendar creation workflow, native permissions, approval time, or a final answer. PyTorch throughput is derived from a token streamer; MLX reports its own engine throughput, so the exact timing boundaries differ. App defaults retain sampling at temperature 1.0 / top-p 0.95 and may generate different outputs and latencies. No quantization or persistent prompt caching is enabled.

These results were collected before removing the PyTorch backend. The root README now documents MLX-only measurement; the old PyTorch benchmark is retained here as historical data. Raw results are in [granite-pytorch.json](granite-pytorch.json) and [granite-mlx.json](granite-mlx.json).

## Functional checks

The automated suite covers async generation, shared serialization across tool-bound copies, special-token encoding, thinking disabled, tool-call parsing, summary output limits, stop sequences, truncated tool-call errors, and a LangGraph file proposal interrupted for approval and resumed after rejection. Existing calendar, reminder, file, and OpenAI tests also run unchanged.

Additional real-model checks use a temporary conversation store and simulated native calendar results; they never write to the real calendar. The complete request “내일 오후 6시부터 오후 7시까지 러닝크루 일정 추가해줘” completed the search → create → final-answer flow with the exact title and 18:00–19:00 interval. These checks exposed model-level limitations under greedy decoding: a follow-up end time sometimes results in another question rather than a tool call, and one run misspelled the supplied Korean event title. A successful tool-call round trip therefore does not guarantee semantic accuracy. This engine change does not add prompt rules or change the shared calendar workflow to hide those failures. Verify the proposal before approving writes; The PyTorch implementation has since been removed; the raw measurements remain available for comparison.
