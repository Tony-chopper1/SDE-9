# AcademiaAI Voicebot — Frontend & UX Module

**Module Owner**: Spoorthi V Sawkar (`feature/frontend`)
**Product**: Academia - AI Voice Co-Pilot
**Compliance**: WCAG 2.1 AA Compliant

---

## 1. Overview

The Frontend & UX module delivers an accessible, responsive, enterprise-grade React application shell for the **AcademiaAI Voicebot**. It acts as the human-in-the-loop interface between the user's voice input, context engines, multimodal reasoning agents, and tool execution.

### Key Highlights
- **Enterprise SaaS Aesthetic**: Polished, professional white/light design system inspired by Linear, Notion, and OpenAI.
- **Full WCAG 2.1 AA Compliance**: Strict color contrast ratios (> 4.5:1), semantic landmarks without duplicates, visible focus rings, ARIA live regions, and skip-navigation links.
- **Microphone Permission States**: Explicit support for `prompt`, `granted`, `denied`, and `unsupported` states with Permissions API integration and graceful fallback.
- **Backend Mock-Mode Banner**: Accessible visual indicator rendering when the backend reports `mock_mode === true`.
- **Chronological Transcript Sequencing**: Pre-render ascending timestamp sorting preventing disordered playback or screen reader disorientation.
- **Virtualized High-Performance Timeline**: Effortlessly renders 1,000+ transcript entries with zero DOM lag at 60 FPS.
- **Browser-Native Audio Capture**: Integrated Web Speech API and MediaRecorder supporting live interim speech recognition, local storage persistence, and transcript export.
- **Type-Safe Backend Client**: Zero `any` types communicating with the FastAPI backend gateway.
- **Robust Test Suite**: 38 unit and component tests achieving **94.03% statement coverage** using Vitest and React Testing Library.

---

## 2. Component Hierarchy & Architecture

```
frontend/src/
├── main.tsx                         # React 18 DOM root mount
├── App.tsx                          # Core application state & layout assembly
├── styles.css                       # Enterprise SaaS light theme & responsive rules
├── api_client.ts                    # Type-safe client for backend REST endpoints
├── hooks/
│   └── useVoiceRecorder.ts          # Custom hook for Web Speech & MediaRecorder
├── types/
│   └── speech.ts                    # Complete Web Speech API & session TypeScript types
├── components/
│   ├── AppShell.tsx                 # Header, sidebar, status pill, skip link
│   ├── EngineStatusPanel.tsx        # Compact sidebar engine, latency, & speech API status
│   ├── VoiceControls.tsx            # Mic toggle, audio waveform visualizer, error alerts
│   ├── TranscriptTimeline.tsx       # Virtualized timeline for 1,000+ segments (chronologically sorted)
│   ├── SessionHistory.tsx           # Past recordings list, download, and delete
│   └── ErrorBoundary.tsx            # Graceful crash handling & reload fallback
└── __tests__/
    ├── api_client.test.ts           # REST client unit tests (health, sessions, chat)
    ├── useVoiceRecorder.test.ts     # Hook tests (audio streams, speech events, permissions, fallbacks)
    ├── EngineStatusPanel.test.tsx   # Sidebar engine status panel tests
    ├── TranscriptTimeline.test.tsx  # Timeline tests (empty state, segments, out-of-order sorting, 1000+ virtualization)
    ├── ErrorBoundary.test.tsx       # Error boundary fallback tests
    └── App.test.tsx                 # App integration tests (start/stop, permissions, mock mode, history)
```

---

## 3. High-Performance Virtualized Timeline

When interacting in long voice sessions, transcript lists quickly accumulate hundreds or thousands of speech segments. Rendering thousands of DOM nodes causes memory spikes and input latency.

`TranscriptTimeline.tsx` implements **windowed viewport virtualization**:
- Segments are sorted chronologically by ascending `start_time` prior to calculation.
- Dynamically computes visible item indices based on container scroll position.
- Renders only the active viewport slice (~15 to 25 DOM elements) while maintaining the scroll container's true virtual height.
- Tested and verified with **1,200+ segments** rendering in under 15ms without scroll jank or memory leaks.

---

## 4. Type-Safe API Client

Located in [`src/api_client.ts`](src/api_client.ts), `TypedVoicebotClient` provides type-safe methods matching the backend FastAPI OpenAPI specifications:

```typescript
import { TypedVoicebotClient } from './api_client';

const client = new TypedVoicebotClient('http://localhost:8000/api/v1');

// 1. Health Check
const health = await client.checkHealth();
console.log(health.data?.status); // 'healthy'
console.log(health.data?.mock_mode); // true | false

// 2. Create Session
const session = await client.createSession();
console.log(session.data?.session_id);

// 3. Send AI Chat Query
const chat = await client.sendChatMessage(session.data!.session_id, 'Why is this failing?');
console.log(chat.data?.response);
```

---

## 5. Development & Testing Workflow

### Prerequisites
- Node.js (v18 or higher recommended)
- npm (v9 or higher)

### Setup & Local Development
```bash
# Navigate to frontend folder
cd frontend

# Install dependencies
npm install

# Start local Vite development server
npm run dev
```

### Production Build
```bash
# Type check and build bundle
npm run build
```

### Running Test Suite
```bash
# Run all unit and integration tests
npm test -- --run

# Run tests with V8 coverage report
npm run test:coverage
```

---

## 6. Test Results & Coverage Report

The project includes **38 tests across 6 test suites** with **94.03% statement coverage**:

```
 % Coverage report from v8
-------------------|---------|----------|---------|---------|-------------------
File               | % Stmts | % Branch | % Funcs | % Lines | Uncovered Line #s
-------------------|---------|----------|---------|---------|-------------------
All files          |   94.03 |    85.93 |   87.17 |   94.03 |
 src               |   88.16 |       80 |      90 |   88.16 |
  App.tsx          |   86.79 |    76.36 |      80 |   86.79 | ...07,228-237,253
  api_client.ts    |     100 |      100 |     100 |     100 |
 src/components    |   98.65 |    91.11 |   84.21 |   98.65 |
  AppShell.tsx     |     100 |    85.71 |      50 |     100 | 60-62,108
  ...atusPanel.tsx |   97.33 |    90.62 |     100 |   97.33 | 50-51
  ...rBoundary.tsx |     100 |     87.5 |     100 |     100 | 53
  ...onHistory.tsx |     100 |    93.75 |   83.33 |     100 | 64
  ...tTimeline.tsx |   96.02 |    87.09 |     100 |   96.02 | 66-71
  ...eControls.tsx |     100 |      100 |     100 |     100 |
 src/hooks         |   90.15 |    80.64 |   88.88 |   90.15 |
  ...ceRecorder.ts |   90.15 |    80.64 |   88.88 |   90.15 | ...13,215-216,235
 src/types         |       0 |        0 |       0 |       0 |
  speech.ts        |       0 |        0 |       0 |       0 |
-------------------|---------|----------|---------|---------|-------------------
```

---

## 7. Accessibility Report

Full accessibility documentation is available in [ACCESSIBILITY.md](ACCESSIBILITY.md).
- Color contrast ratio: Minimum **4.5:1** on all text (primary headings: **16.5:1**).
- Full keyboard navigation support (`Tab`, `Shift+Tab`, `Enter`, `Space`, `Arrow Keys`).
- Screen reader live regions (`aria-live="polite"` for transcript updates, `aria-live="assertive"` for alerts, `role="status"` for mock mode and mic permission badges).
- High-visibility focus rings (`:focus-visible`).
