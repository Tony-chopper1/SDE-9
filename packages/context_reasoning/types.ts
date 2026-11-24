/**
 * Context & Reasoning Module Type Definitions
 * 
 * Defines typed contracts for application state tracking, screen frames,
 * context items, source references, conversation turns, versioned prompt
 * templates, and structured reasoning requests/results.
 */

export type AppType = 'ide' | 'browser' | 'terminal' | 'document' | 'other';

export type TurnRole = 'user' | 'assistant' | 'system';

export type SourceType = 'window' | 'screen' | 'file' | 'url' | 'conversation' | 'system' | 'tool' | 'custom';

export type ContextItemType = 'window' | 'screen' | 'snippet' | 'turn' | 'file' | 'system' | 'custom';

export interface SourceReference {
  sourceId: string;
  sourceType: SourceType;
  title?: string;
  uri?: string;
  isTrusted: boolean;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ContextItem {
  itemId: string;
  itemType: ContextItemType;
  content: string;
  source?: SourceReference;
  isTrusted: boolean;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface WindowContext {
  appName: string;
  windowTitle: string;
  appType: AppType;
  visibleSnippet?: string;
  url?: string;
  metadata?: Record<string, unknown>;
}

export interface ScreenContext {
  captureEnabled: boolean;
  frameId?: string;
  timestamp: number;
  width: number;
  height: number;
  format: string;
  imageData?: Uint8Array | string;
  isSynthetic: boolean;
  visibleText?: string;
  activeWindow?: WindowContext;
  metadata?: Record<string, unknown>;
}

export interface ConversationTurn {
  id: string;
  role: TurnRole;
  content: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ConversationContext {
  sessionId: string;
  activeWindow: WindowContext;
  history: ConversationTurn[];
  userQuery: string;
  screenContext?: ScreenContext;
  contextItems?: ContextItem[];
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface VersionedPromptTemplate {
  version: string;
  template: string;
  variables: string[];
  description?: string;
  createdAt: number;
}

export interface ReasoningRequest {
  requestId: string;
  sessionId: string;
  query: string;
  context?: ConversationContext;
  contextItems?: ContextItem[];
  screenContext?: ScreenContext;
  promptVersion?: string;
  temperature?: number;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ReasoningResult {
  intent: string;
  requiresTool: boolean;
  plannedToolName?: string;
  toolParameters?: Record<string, unknown>;
  directResponse?: string;
  confidence: number;
  reasoningSteps?: string[];
  metadata?: Record<string, unknown>;
}

export interface VisionRegion {
  regionId: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  textContent?: string;
}

export interface VisionResult {
  frameId: string;
  extractedText: string;
  regions: VisionRegion[];
  confidence: number;
  processingTimeMs: number;
  metadata?: Record<string, unknown>;
}

export interface LLMResponse {
  content: string;
  rawJson?: Record<string, unknown>;
  structuredData?: unknown;
  modelName: string;
  latencyMs: number;
  retriesUsed: number;
  metadata?: Record<string, unknown>;
}

export interface CaptureConfig {
  captureEnabled: boolean;
  maxFps: number;
  maxWidth: number;
  maxHeight: number;
  maxBytes: number;
  downscaleOnOverflow: boolean;
}

export interface ContextBuilderConfig {
  tokenBudget: number;
  maxHistoryTurns: number;
  staleThresholdSeconds: number;
  screenStaleSeconds: number;
  relevanceThreshold: number;
}
