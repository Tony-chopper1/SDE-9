/**
 * Context & Reasoning Module Type Definitions
 * 
 * Defines typed contracts for application state tracking, conversation turns,
 * versioned prompt templates, and structured decision results.
 */

export type AppType = 'ide' | 'browser' | 'terminal' | 'document' | 'other';

export type TurnRole = 'user' | 'assistant' | 'system';

export interface WindowContext {
  appName: string;
  windowTitle: string;
  appType: AppType;
  visibleSnippet?: string;
  url?: string;
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
