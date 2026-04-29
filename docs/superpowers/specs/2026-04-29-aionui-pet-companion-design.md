# AionUi Pet Companion Design

Date: 2026-04-29

## Goal

Connect Jarvis to AionUi's desktop pet so the pet acts as the mascot, state mirror, and click-to-talk entry point while Jarvis remains the primary assistant runtime.

The first implementation slice preserves Jarvis's existing voice loop. AionUi does not record or upload audio in this slice. It sends a wake trigger, then Jarvis captures microphone input through the current VAD/STT path.

## Context

Jarvis already has the core pieces needed for this integration:

- `VoiceAssistant.trigger_wake()` can move the assistant into its listening flow.
- `AssistantState` transitions are published through `EventBus`.
- The dashboard bridge already mirrors assistant state and events to UI surfaces.
- The current audio path handles microphone capture, VAD endpointing, transcription, LLM/tool routing, TTS, and follow-up listening.

AionUi's desktop pet supports real-time AI activity reactions and pet-side confirmation bubbles in recent releases, so the integration should drive the pet from Jarvis events instead of moving assistant logic into AionUi.

Reference: https://github.com/iOfficeAI/AionUi/releases

## Non-Goals

- Do not replace Jarvis's microphone, VAD, STT, LLM, memory, tool, or TTS systems.
- Do not make AionUi the primary assistant brain.
- Do not add AionUi-side audio recording/upload in the first slice.
- Do not replace the existing Jarvis orb or dashboard.
- Do not bypass Jarvis safety gates for tool execution or confirmations.

## Architecture

AionUi becomes a companion client for Jarvis.

```text
AionUi pet click
  -> Jarvis companion wake endpoint
  -> VoiceAssistant.trigger_wake()
  -> existing Jarvis LISTENING flow
  -> VAD/STT
  -> LLM, tools, memory, safety gates
  -> TTS response
  -> follow-up listening or IDLE
```

Jarvis remains the source of truth for assistant state. AionUi subscribes to a local event feed and maps Jarvis states to pet animations.

## Companion API

Add a small local companion API surface, either inside the existing API server/dashboard surface or as a thin adapter around the existing `VoiceAssistant` instance.

### `POST /api/companion/wake`

Called when the AionUi pet is clicked or when an AionUi click-to-talk button is pressed.

Expected behavior:

- If Jarvis is idle or otherwise able to enter listening, call `VoiceAssistant.trigger_wake()`.
- Return `accepted: true` and the current or next expected assistant state.
- If Jarvis is already listening, processing, or speaking, do not start an overlapping session.
- Return `accepted: false`, the current state, and a short reason when busy.

Example response:

```json
{
  "accepted": true,
  "state": "LISTENING"
}
```

Busy response:

```json
{
  "accepted": false,
  "state": "SPEAKING",
  "reason": "assistant_busy"
}
```

### `GET /api/companion/state`

Returns the current Jarvis state for AionUi startup, reconnect, and recovery.

Example response:

```json
{
  "state": "IDLE",
  "wake_word_enabled": true,
  "timestamp": "2026-04-29T00:00:00"
}
```

### Event Feed

Expose or reuse a WebSocket/SSE event feed so AionUi can update the pet without polling.

Minimum event payload:

```json
{
  "type": "state",
  "state": "LISTENING",
  "previous": "IDLE",
  "timestamp": "2026-04-29T00:00:00"
}
```

Useful additional events:

- `transcription`: show what Jarvis heard, if desired.
- `response`: show short response text near the pet, if desired.
- `confirmation`: mirror tool confirmation requests to AionUi's pet bubble.
- `error`: show pet error animation and concise failure detail.

## State Mapping

```text
Jarvis IDLE        -> pet idle
Jarvis LISTENING   -> pet attentive/listening
Jarvis PROCESSING  -> pet thinking
Jarvis SPEAKING    -> pet talking/working
ConfirmationEvent  -> pet confirmation bubble
ErrorEvent         -> pet error
Completion         -> pet done, then idle
```

If AionUi exposes a different state vocabulary, keep a single mapping table in the adapter so Jarvis state names do not leak throughout the UI integration.

## Error Handling

- If AionUi calls wake while Jarvis is busy, Jarvis returns `accepted: false` and does not mutate state.
- If the microphone is unavailable, Jarvis emits an error/subsystem event and AionUi shows the pet error state.
- If AionUi disconnects, Jarvis continues normally.
- If Jarvis restarts, AionUi should call `GET /api/companion/state` and resubscribe to the event feed.
- If a tool confirmation is denied or times out, Jarvis remains the authority and AionUi only mirrors the result.

## Testing

Focused tests for the first slice:

- Wake endpoint calls `VoiceAssistant.trigger_wake()` when Jarvis is idle.
- Wake endpoint rejects overlapping activation when Jarvis is listening, processing, or speaking.
- State endpoint returns the current assistant state in a stable JSON shape.
- Event feed emits state changes in the companion payload shape.
- Confirmation and error events can be serialized for pet display.
- Existing voice assistant tests continue to pass for wake, listening, processing, TTS, and safety routing.

## Implementation Notes

Before editing symbols, run GitNexus impact analysis on each function/class/method that will be modified. Likely symbols include the API server endpoint registration, dashboard bridge/event serialization, and `VoiceAssistant.trigger_wake()` consumers.

Prefer a preservation-first implementation:

1. Add tests around the companion contract.
2. Add the minimal API adapter.
3. Reuse existing `EventBus` and dashboard bridge behavior where possible.
4. Keep AionUi-specific naming at the boundary.
5. Do not change the existing voice loop unless a test proves the companion path needs a small hook.

## Open Integration Detail

The exact AionUi call mechanism depends on its available extension/API surface. The Jarvis-side contract should be stable either way:

- If AionUi can call local HTTP directly, point pet click to `POST /api/companion/wake`.
- If AionUi expects an MCP/tool/channel integration, create a small AionUi adapter that calls the same Jarvis endpoint.

This keeps the Jarvis implementation independent from AionUi internals.
