// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

export type MessageRole = "user" | "assistant" | "tool";

export type AgentType = 
  | "coordinator"
  | "planner" 
  | "researcher"
  | "coder"
  | "reporter"
  | "podcast"
  | "coordinator_thinking"
  | "ChatGoogleGenerativeAI"
  | "ChatXAI"
  | string; // Allow flexibility for any other agent types

export interface Message {
  id: string;
  threadId: string;
  agent?: AgentType;
  role: MessageRole;
  isStreaming?: boolean;
  content: string;
  contentChunks: string[];
  toolCalls?: ToolCallRuntime[];
  options?: Option[];
  finishReason?: "stop" | "interrupt" | "tool_calls";
  interruptFeedback?: string;
}

export interface Option {
  text: string;
  value: string;
}

export interface ToolCallRuntime {
  id: string;
  name: string;
  args: Record<string, unknown> | string;
  argsChunks?: string[];
  result?: string;
}
