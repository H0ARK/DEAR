// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { nanoid } from "nanoid";
import { toast } from "sonner";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { chatStream, generatePodcast } from "../api";
import type { ToolCall } from "../api/types";
import type { Message } from "../messages";
import { mergeMessage } from "../messages";
import { parseJSON } from "../utils";

import { getChatStreamSettings } from "./settings-store";

const THREAD_ID = nanoid();

export const useStore = create<{
  responding: boolean;
  threadId: string | undefined;
  messageIds: string[];
  messages: Map<string, Message>;
  researchIds: string[];
  researchPlanIds: Map<string, string>;
  researchReportIds: Map<string, string>;
  researchActivityIds: Map<string, string[]>;
  ongoingResearchId: string | null;
  openResearchId: string | null;

  appendMessage: (message: Message) => void;
  updateMessage: (message: Message) => void;
  updateMessages: (messages: Message[]) => void;
  openResearch: (researchId: string | null) => void;
  closeResearch: () => void;
  setOngoingResearch: (researchId: string | null) => void;
}>((set) => ({
  responding: false,
  threadId: THREAD_ID,
  messageIds: [],
  messages: new Map<string, Message>(),
  researchIds: [],
  researchPlanIds: new Map<string, string>(),
  researchReportIds: new Map<string, string>(),
  researchActivityIds: new Map<string, string[]>(),
  ongoingResearchId: null,
  openResearchId: null,

  appendMessage(message: Message) {
    console.log("Appending new message:", message.id, message.agent, message.content?.substring(0, 50) + "...");
    set((state) => ({
      messageIds: [...state.messageIds, message.id],
      messages: new Map(state.messages).set(message.id, message),
    }));
  },
  updateMessage(message: Message) {
    console.log("Updating message:", message.id, message.agent, message.content?.substring(0, 50) + "...");
    set((state) => ({
      messages: new Map(state.messages).set(message.id, message),
    }));
  },
  updateMessages(messages: Message[]) {
    console.log("Batch updating messages:", messages.map(m => m.id));
    set((state) => {
      const newMessages = new Map(state.messages);
      messages.forEach((m) => newMessages.set(m.id, m));
      return { messages: newMessages };
    });
  },
  openResearch(researchId: string | null) {
    set({ openResearchId: researchId });
  },
  closeResearch() {
    set({ openResearchId: null });
  },
  setOngoingResearch(researchId: string | null) {
    set({ ongoingResearchId: researchId });
  },
}));

export async function sendMessage(
  content?: string,
  {
    interruptFeedback,
  }: {
    interruptFeedback?: string;
  } = {},
  options: { abortSignal?: AbortSignal } = {},
) {
  if (content != null) {
    appendMessage({
      id: nanoid(),
      threadId: THREAD_ID,
      role: "user",
      content: content,
      contentChunks: [content],
    });
  }

  const settings = getChatStreamSettings();
  const stream = chatStream(
    content ?? "[REPLAY]",
    {
      thread_id: THREAD_ID,
      interrupt_feedback: interruptFeedback,
      auto_accepted_plan: settings.autoAcceptedPlan,
      enable_background_investigation: settings.enableBackgroundInvestigation ?? true,
      max_plan_iterations: settings.maxPlanIterations,
      max_step_num: settings.maxStepNum,
      mcp_settings: settings.mcpSettings,
      create_workspace: settings.createWorkspace,
      force_interactive: false
    },
    options,
  );

  setResponding(true);
  let activeStreamingMessageId: string | null = null;
  
  try {
    for await (const event of stream) {
      const { type, data } = event;
      console.log("Received event:", type, data.id || "no event-specific id", data);

      let messageToUpdate: Message | undefined;
      const eventSpecificId = data.id; // ID from the event data itself

      if (activeStreamingMessageId && (type === "message_chunk" || type === "tool_call_chunks")) {
        console.log(`Active stream ${activeStreamingMessageId} exists. Appending chunk (${type}) to it.`);
        messageToUpdate = getMessage(activeStreamingMessageId);
        if (!messageToUpdate) { 
            console.error(`Consistency error: activeStreamingMessageId ${activeStreamingMessageId} has no message! Resetting active stream.`);
            activeStreamingMessageId = null; 
            // Fall through to allow new stream creation based on eventSpecificId or localId
        }
      }
      
      if (!messageToUpdate) { // If not already set by active stream logic
        if (type === "message_chunk" || type === "tool_calls" || type === "tool_call_chunks" || type === "interrupt") {
          if (eventSpecificId) {
            if (!existsMessage(eventSpecificId)) {
              console.log(`No/failed active stream. New message event (${type}) with ID ${eventSpecificId}. Creating.`);
              const newMessage: Message = {
                id: eventSpecificId,
                threadId: data.thread_id || THREAD_ID,
                agent: data.agent || "assistant",
                role: data.role || "assistant",
                content: "",
                contentChunks: [],
                isStreaming: true,
                toolCalls: (type === "tool_calls" && data.tool_calls) ? data.tool_calls.map((tc: ToolCall) => ({
                  id: tc.id,
                  name: tc.name,
                  args: tc.args ? (typeof tc.args === 'string' ? JSON.parse(tc.args) : tc.args) : {},
                  argsChunks: []
                })) : [],
              };
              if (type === "interrupt" && data.options) {
                newMessage.options = data.options;
              }
              appendMessage(newMessage);
              messageToUpdate = newMessage;
              activeStreamingMessageId = eventSpecificId; 
            } else {
              console.log(`No/failed active stream. Event (${type}) with existing ID ${eventSpecificId}. Updating.`);
              messageToUpdate = getMessage(eventSpecificId);
              activeStreamingMessageId = eventSpecificId; 
            }
          } else {
            if (type === "message_chunk" || type === "tool_calls" || type === "interrupt") {
              const localId = nanoid();
              console.log(`No/failed active stream. New initial event (${type}) without ID. Creating local ID ${localId}.`);
              const newMessage: Message = {
                id: localId,
                threadId: data.thread_id || THREAD_ID,
                agent: data.agent || "assistant",
                role: data.role || "assistant",
                content: "",
                contentChunks: [],
                isStreaming: true,
                toolCalls: (type === "tool_calls" && data.tool_calls) ? data.tool_calls.map((tc: ToolCall) => ({
                  id: tc.id,
                  name: tc.name,
                  args: tc.args ? (typeof tc.args === 'string' ? JSON.parse(tc.args) : tc.args) : {},
                  argsChunks: []
                })) : [],
              };
              if (type === "interrupt" && data.options) {
                newMessage.options = data.options;
              }
              appendMessage(newMessage);
              messageToUpdate = newMessage;
              activeStreamingMessageId = localId; 
            } else {
              console.warn("No/failed active stream and event without ID couldn't start a new message:", event);
              continue;
            }
          }
        } else if (type === "tool_call_result") {
          messageToUpdate = findMessageByToolCallId(data.tool_call_id);
          if (messageToUpdate) {
              activeStreamingMessageId = messageToUpdate.id; 
          } else {
              console.warn("No message found for tool_call_result:", event);
              continue;
          }
        } else {
          console.warn("Unhandled event type in stream:", type);
          continue;
        }
      }

      if (messageToUpdate) {
        const updatedMessage = mergeMessage(messageToUpdate, event);
        updateMessage(updatedMessage);

        if (event.data.finish_reason || (type === "interrupt")) {
          console.log(`Stream finished for message ${messageToUpdate.id}, reason: ${event.data.finish_reason ?? 'interrupt'}`);
          activeStreamingMessageId = null;
        }
      }
    }
  } catch (e) {
    console.error("Error in chat stream:", e);
    toast("An error occurred while generating the response. Please try again.");
    
    if (activeStreamingMessageId) {
      const message = getMessage(activeStreamingMessageId);
      if (message?.isStreaming) {
        message.isStreaming = false;
        updateMessage(message);
      }
    }
    
    useStore.getState().setOngoingResearch(null);
  } finally {
    setResponding(false);
  }
}

function setResponding(value: boolean) {
  useStore.setState({ responding: value });
}

function existsMessage(id: string) {
  return useStore.getState().messageIds.includes(id);
}

function getMessage(id: string) {
  return useStore.getState().messages.get(id);
}

function findMessageByToolCallId(toolCallId: string) {
  return Array.from(useStore.getState().messages.values())
    .reverse()
    .find((message) => {
      if (message.toolCalls) {
        return message.toolCalls.some((toolCall) => toolCall.id === toolCallId);
      }
      return false;
    });
}

function appendMessage(message: Message) {
  if (
    message.agent === "coder" ||
    message.agent === "reporter" ||
    message.agent === "researcher"
  ) {
    if (!getOngoingResearchId()) {
      const id = message.id;
      appendResearch(id);
      openResearch(id);
    }
    appendResearchActivity(message);
  }
  useStore.getState().appendMessage(message);
}

function updateMessage(message: Message) {
  if (
    getOngoingResearchId() &&
    message.agent === "reporter" &&
    !message.isStreaming
  ) {
    useStore.getState().setOngoingResearch(null);
  }
  useStore.getState().updateMessage(message);
}

function getOngoingResearchId() {
  return useStore.getState().ongoingResearchId;
}

function appendResearch(researchId: string) {
  let planMessage: Message | undefined;
  const reversedMessageIds = [...useStore.getState().messageIds].reverse();
  for (const messageId of reversedMessageIds) {
    const message = getMessage(messageId);
    if (message?.agent === "planner") {
      planMessage = message;
      break;
    }
  }
  const messageIds = [researchId];
  messageIds.unshift(planMessage!.id);
  useStore.setState({
    ongoingResearchId: researchId,
    researchIds: [...useStore.getState().researchIds, researchId],
    researchPlanIds: new Map(useStore.getState().researchPlanIds).set(
      researchId,
      planMessage!.id,
    ),
    researchActivityIds: new Map(useStore.getState().researchActivityIds).set(
      researchId,
      messageIds,
    ),
  });
}

function appendResearchActivity(message: Message) {
  const researchId = getOngoingResearchId();
  if (researchId) {
    const researchActivityIds = useStore.getState().researchActivityIds;
    const current = researchActivityIds.get(researchId)!;
    if (!current.includes(message.id)) {
      useStore.setState({
        researchActivityIds: new Map(researchActivityIds).set(researchId, [
          ...current,
          message.id,
        ]),
      });
    }
    if (message.agent === "reporter") {
      useStore.setState({
        researchReportIds: new Map(useStore.getState().researchReportIds).set(
          researchId,
          message.id,
        ),
      });
    }
  }
}

export function openResearch(researchId: string | null) {
  useStore.getState().openResearch(researchId);
}

export function closeResearch() {
  useStore.getState().closeResearch();
}

export async function listenToPodcast(researchId: string) {
  const planMessageId = useStore.getState().researchPlanIds.get(researchId);
  const reportMessageId = useStore.getState().researchReportIds.get(researchId);
  if (planMessageId && reportMessageId) {
    const planMessage = getMessage(planMessageId)!;
    const title = parseJSON(planMessage.content, { title: "Untitled" }).title;
    const reportMessage = getMessage(reportMessageId);
    if (reportMessage?.content) {
      appendMessage({
        id: nanoid(),
        threadId: THREAD_ID,
        role: "user",
        content: "Please generate a podcast for the above research.",
        contentChunks: [],
      });
      const podCastMessageId = nanoid();
      const podcastObject = { title, researchId };
      const podcastMessage: Message = {
        id: podCastMessageId,
        threadId: THREAD_ID,
        role: "assistant",
        agent: "podcast",
        content: JSON.stringify(podcastObject),
        contentChunks: [],
        isStreaming: true,
      };
      appendMessage(podcastMessage);
      // Generating podcast...
      let audioUrl: string | undefined;
      try {
        audioUrl = await generatePodcast(reportMessage.content);
      } catch (e) {
        useStore.setState((state) => ({
          messages: new Map(useStore.getState().messages).set(
            podCastMessageId,
            {
              ...state.messages.get(podCastMessageId)!,
              content: JSON.stringify({
                ...podcastObject,
                error: e instanceof Error ? e.message : "Unknown error",
              }),
              isStreaming: false,
            },
          ),
        }));
        toast("An error occurred while generating podcast. Please try again.");
        return;
      }
      useStore.setState((state) => ({
        messages: new Map(useStore.getState().messages).set(podCastMessageId, {
          ...state.messages.get(podCastMessageId)!,
          content: JSON.stringify({ ...podcastObject, audioUrl }),
          isStreaming: false,
        }),
      }));
    }
  }
}

export function useResearchMessage(researchId: string) {
  return useStore(
    useShallow((state) => {
      const messageId = state.researchPlanIds.get(researchId);
      return messageId ? state.messages.get(messageId) : undefined;
    }),
  );
}

export function useMessage(messageId: string | null | undefined) {
  return useStore(
    useShallow((state) =>
      messageId ? state.messages.get(messageId) : undefined,
    ),
  );
}

export function useMessageIds() {
  return useStore(useShallow((state) => state.messageIds));
}

export function useLastInterruptMessage() {
  return useStore(
    useShallow((state) => {
      if (state.messageIds.length >= 2) {
        const lastMessage = state.messages.get(
          state.messageIds[state.messageIds.length - 1]!,
        );
        return lastMessage?.finishReason === "interrupt" ? lastMessage : null;
      }
      return null;
    }),
  );
}

export function useLastFeedbackMessageId() {
  const waitingForFeedbackMessageId = useStore(
    useShallow((state) => {
      if (state.messageIds.length >= 2) {
        const lastMessage = state.messages.get(
          state.messageIds[state.messageIds.length - 1]!,
        );
        if (lastMessage && lastMessage.finishReason === "interrupt") {
          return state.messageIds[state.messageIds.length - 2];
        }
      }
      return null;
    }),
  );
  return waitingForFeedbackMessageId;
}


