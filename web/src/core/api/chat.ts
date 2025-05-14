// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { nanoid } from "nanoid";

import { env } from "~/env";

import type { MCPServerMetadata } from "../mcp";
import { extractReplayIdFromSearchParams } from "../replay/get-replay-id";
import { fetchStream } from "../sse";
import { sleep } from "../utils";

import { resolveServiceURL } from "./resolve-service-url";
import type { ChatEvent } from "./types";

export async function* chatStream(
  userMessage: string,
  params: {
    thread_id: string;
    auto_accepted_plan: boolean;
    force_interactive: boolean;
    max_plan_iterations: number;
    max_step_num: number;
    interrupt_feedback?: string;
    enable_background_investigation: boolean;
    mcp_settings?: {
      servers: Record<
        string,
        MCPServerMetadata & {
          enabled_tools: string[];
          add_to_agents: string[];
        }
      >;
    };
    create_workspace: boolean;
  },
  options: { abortSignal?: AbortSignal } = {},
) {
  if (
    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY ||
    location.search.includes("mock") ||
    location.search.includes("replay=")
  ) {
    return yield* chatReplayStream(userMessage, params, options);
  }
  
  const stream = fetchStream(resolveServiceURL("chat/stream"), {
    body: JSON.stringify({
      messages: [{ role: "user", content: userMessage }],
      ...params,
    }),
    signal: options.abortSignal,
  });
  
  try {
    for await (const event of stream) {
      try {
        const chatEvent = {
          type: event.event,
          data: JSON.parse(event.data),
        } as ChatEvent;
        
        yield chatEvent;
      } catch (e) {
        console.error("Error parsing SSE event:", e, event);
      }
    }
  } catch (e) {
    throw e;
  }
}

async function* chatReplayStream(
  userMessage: string,
  params: {
    thread_id: string;
    auto_accepted_plan: boolean;
    max_plan_iterations: number;
    max_step_num: number;
    interrupt_feedback?: string;
  } = {
    thread_id: "__mock__",
    auto_accepted_plan: false,
    max_plan_iterations: 3,
    max_step_num: 1,
    interrupt_feedback: undefined,
  },
  options: { abortSignal?: AbortSignal } = {},
) {
  // Default to 1x speed if not specified
  const speedFactor = 1;
  const sleepInReplay = async (duration: number): Promise<void> => {
    await sleep(duration / speedFactor);
  };

  const replayId = extractReplayIdFromSearchParams(window.location.search);

  if (!replayId) {
    const text = `event: message_chunk
data: {"id":"${nanoid()}","thread_id":"${params.thread_id}","role":"assistant","agent":"coordinator","content":"In replay mode, I need a replay id to know what to replay. Include ?replay=XXX or make sure you are correctly loading a replay from the replay directory."}

event: end
data: {"thread_id":"${params.thread_id}"}
`;
    const chunks = text.split("\n\n");
    for (const chunk of chunks) {
      const [eventRaw, dataRaw] = chunk.split("\n") as [string, string];
      const [, event] = eventRaw.split("event: ", 2) as [string, string];
      const [, data] = dataRaw.split("data: ", 2) as [string, string];
      yield {
        type: event,
        data: JSON.parse(data),
      } as ChatEvent;
      await sleepInReplay(500);
    }
    return;
  }

  const replayFilePath = `/replay/${replayId}.json`;
  // Use RequestInit instead of custom options type
  const fetchOptions: RequestInit = {
    signal: options.abortSignal
  };
  
  const text = await (await fetch(replayFilePath, fetchOptions)).text();
  const chunks = text.split("\n\n");
  for (const chunk of chunks) {
    const [eventRaw, dataRaw] = chunk.split("\n") as [string, string];
    const [, event] = eventRaw.split("event: ", 2) as [string, string];
    const [, data] = dataRaw.split("data: ", 2) as [string, string];

    try {
      const chatEvent = {
        type: event,
        data: JSON.parse(data),
      } as ChatEvent;
      if (chatEvent.type === "message_chunk") {
        if (!chatEvent.data.finish_reason) {
          await sleepInReplay(50);
        }
      } else if (chatEvent.type === "tool_call_result") {
        await sleepInReplay(500);
      }
      yield chatEvent;
      if (chatEvent.type === "tool_call_result") {
        await sleepInReplay(800);
      } else if (chatEvent.type === "message_chunk") {
        if (chatEvent.data.role === "user") {
          await sleepInReplay(500);
        }
      }
    } catch (e) {
      console.error("Failed to parse chunk", e, chunk);
    }
  }
}

const replayCache = new Map<string, string>();
export async function fetchReplay(
  url: string,
  options: { abortSignal?: AbortSignal } = {},
) {
  if (replayCache.has(url)) {
    return replayCache.get(url)!;
  }
  const res = await fetch(url, {
    signal: options.abortSignal,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch replay: ${res.statusText}`);
  }
  const text = await res.text();
  replayCache.set(url, text);
  return text;
}

export async function fetchReplayTitle() {
  const res = chatReplayStream(
    "",
    {
      thread_id: "__mock__",
      auto_accepted_plan: false,
      max_plan_iterations: 3,
      max_step_num: 1,
    },
    {},
  );
  for await (const event of res) {
    if (event.type === "message_chunk") {
      return event.data.content;
    }
  }
}

export async function sleepInReplay(ms: number) {
  if (fastForwardReplaying) {
    await sleep(0);
  } else {
    await sleep(ms);
  }
}

let fastForwardReplaying = false;
export function fastForwardReplay(value: boolean) {
  fastForwardReplaying = value;
}
