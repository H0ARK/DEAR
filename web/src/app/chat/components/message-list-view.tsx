// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { LoadingOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { Download, Headphones } from "lucide-react";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";

import { LoadingAnimation } from "~/components/deer-flow/loading-animation";
import { Markdown } from "~/components/deer-flow/markdown";
import { RainbowText } from "~/components/deer-flow/rainbow-text";
import { RollingText } from "~/components/deer-flow/rolling-text";
import {
  ScrollContainer,
  type ScrollContainerRef,
} from "~/components/deer-flow/scroll-container";
import { Tooltip } from "~/components/deer-flow/tooltip";
import { Button } from "~/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card";
import type { Message, Option } from "~/core/messages";
import {
  closeResearch,
  openResearch,
  useLastFeedbackMessageId,
  useLastInterruptMessage,
  useMessage,
  useMessageIds,
  useResearchMessage,
  useStore,
} from "~/core/store";
import { parseJSON } from "~/core/utils";
import { cn } from "~/lib/utils";

export function MessageListView({
  className,
  onFeedback,
  onSendMessage,
}: {
  className?: string;
  onFeedback?: (feedback: { option: Option }) => void;
  onSendMessage?: (
    message: string,
    options?: { interruptFeedback?: string },
  ) => void;
}) {
  const scrollContainerRef = useRef<ScrollContainerRef>(null);
  const messageIds = useMessageIds();
  const interruptMessage = useLastInterruptMessage();
  const waitingForFeedbackMessageId = useLastFeedbackMessageId();
  const responding = useStore((state) => state.responding);
  const noOngoingResearch = useStore(
    (state) => state.ongoingResearchId === null,
  );
  const ongoingResearchIsOpen = useStore(
    (state) => state.ongoingResearchId === state.openResearchId,
  );

  const handleToggleResearch = useCallback(() => {
    // Fix the issue where auto-scrolling to the bottom
    // occasionally fails when toggling research.
    const timer = setTimeout(() => {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollToBottom();
      }
    }, 500);
    return () => {
      clearTimeout(timer);
    };
  }, []);

  return (
    <ScrollContainer
      className={cn("flex h-full w-full flex-col overflow-hidden", className)}
      scrollShadowColor="var(--app-background)"
      autoScrollToBottom
      ref={scrollContainerRef}
    >
      <ul className="flex flex-col">
        {messageIds.map((messageId) => (
          <MessageListItem
            key={messageId}
            messageId={messageId}
            waitForFeedback={waitingForFeedbackMessageId === messageId}
            interruptMessage={interruptMessage}
            onFeedback={onFeedback}
            onSendMessage={onSendMessage}
            onToggleResearch={handleToggleResearch}
          />
        ))}
        <div className="flex h-8 w-full shrink-0"></div>
      </ul>
      {responding && (noOngoingResearch || !ongoingResearchIsOpen) && (
        <LoadingAnimation className="ml-4" />
      )}
    </ScrollContainer>
  );
}

function MessageListItem({
  className,
  messageId,
  waitForFeedback,
  interruptMessage,
  onFeedback,
  onSendMessage,
  onToggleResearch,
}: {
  className?: string;
  messageId: string;
  waitForFeedback?: boolean;
  onFeedback?: (feedback: { option: Option }) => void;
  interruptMessage?: Message | null;
  onSendMessage?: (
    message: string,
    options?: { interruptFeedback?: string },
  ) => void;
  onToggleResearch?: () => void;
}) {
  const message = useMessage(messageId);
  const researchIds = useStore((state) => state.researchIds);
  const startOfResearch = useMemo(() => {
    return researchIds.includes(messageId);
  }, [researchIds, messageId]);
  
  // TODO: Replace this with a real setting from settings-store.ts
  const showDetailedAgentActivity = true; // Default to true for now

  if (message) {
    let content: ReactNode = null;

    if (message.agent === "planner") {
      content = (
        <div className="w-full px-4">
          <PlanCard
            message={message}
            waitForFeedback={waitForFeedback}
            interruptMessage={interruptMessage}
            onFeedback={onFeedback}
            onSendMessage={onSendMessage}
          />
        </div>
      );
    } else if (message.agent === "podcast") {
      content = (
        <div className="w-full px-4">
          <PodcastCard message={message} />
        </div>
      );
    } else if (startOfResearch) {
      content = (
        <div className="w-full px-4">
          <ResearchCard
            researchId={message.id}
            onToggleResearch={onToggleResearch}
          />
        </div>
      );
    } else if (message.role === "user") {
      content = (
        <div
          className={cn(
            "flex w-full px-4 justify-end",
            className,
          )}
        >
          <MessageBubble message={message}>
            <div className="flex w-full flex-col">
              <Markdown animated={message.isStreaming}>{message?.content}</Markdown>
            </div>
          </MessageBubble>
        </div>
      );
    } else if (message.role === "assistant") {
      const isThinkingProcess = typeof message.content === 'string' &&
        message.content.startsWith('🤔 THINKING PROCESS 🤔');

      if (showDetailedAgentActivity) {
        if (isThinkingProcess) {
          content = (
            <div className="flex w-full px-4">
              <div className="w-full">
                <ThinkingBubble content={message.content} />
              </div>
            </div>
          );
        } else {
          // Use new AgentRoleBubble for other assistant messages when detailed view is on
          content = (
            <div className="flex w-full px-4">
              <div className="w-full">
                <AgentRoleBubble agentName={message.agent ?? "assistant"} content={message.content} />
              </div>
            </div>
          );
        }
      } else {
        // Fallback to simple MessageBubble if detailed view is off
        content = (
          <div
            className={cn(
              "flex w-full px-4",
              className,
            )}
          >
            <MessageBubble message={message}>
              <div className="flex w-full flex-col">
                <Markdown animated={message.isStreaming}>{message?.content}</Markdown>
              </div>
            </MessageBubble>
          </div>
        );
      }
    }

    if (content) {
      return (
        <motion.li
          className="mt-10"
          key={messageId}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ transition: "all 0.2s ease-out" }}
          transition={{
            duration: 0.2,
            ease: "easeOut",
          }}
        >
          {content}
        </motion.li>
      );
    }
  }
  return null;
}

function MessageBubble({
  className,
  message,
  children,
}: {
  className?: string;
  message: Message;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        `flex w-fit max-w-[85%] flex-col rounded-2xl px-4 py-3 shadow`,
        message.role === "user" &&
          "text-primary-foreground bg-brand rounded-ee-none",
        message.role === "assistant" && "bg-card rounded-es-none",
        className,
      )}
    >
      {children}
    </div>
  );
}

function ResearchCard({
  className,
  researchId,
  onToggleResearch,
}: {
  className?: string;
  researchId: string;
  onToggleResearch?: () => void;
}) {
  const reportId = useStore((state) => state.researchReportIds.get(researchId));
  const hasReport = reportId !== undefined;
  const reportGenerating = useStore(
    (state) => hasReport && state.messages.get(reportId)!.isStreaming,
  );
  const openResearchId = useStore((state) => state.openResearchId);
  const state = useMemo(() => {
    if (hasReport) {
      return reportGenerating ? "Generating report..." : "Report generated";
    }
    return "Researching...";
  }, [hasReport, reportGenerating]);
  const msg = useResearchMessage(researchId);
  const title = useMemo(() => {
    if (msg) {
      return parseJSON(msg.content ?? "", { title: "" }).title;
    }
    return undefined;
  }, [msg]);
  const handleOpen = useCallback(() => {
    if (openResearchId === researchId) {
      closeResearch();
    } else {
      openResearch(researchId);
    }
    onToggleResearch?.();
  }, [openResearchId, researchId, onToggleResearch]);
  return (
    <Card className={cn("w-full", className)}>
      <CardHeader>
        <CardTitle>
          <RainbowText animated={state !== "Report generated"}>
            {title !== undefined && title !== "" ? title : "Deep Research"}
          </RainbowText>
        </CardTitle>
      </CardHeader>
      <CardFooter>
        <div className="flex w-full">
          <RollingText className="text-muted-foreground flex-grow text-sm">
            {state}
          </RollingText>
          <Button
            variant={!openResearchId ? "default" : "outline"}
            onClick={handleOpen}
          >
            {researchId !== openResearchId ? "Open" : "Close"}
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
}

const GREETINGS = ["Cool", "Sounds great", "Looks good", "Great", "Awesome"];
function PlanCard({
  className,
  message,
  interruptMessage,
  onFeedback,
  waitForFeedback,
  onSendMessage,
}: {
  className?: string;
  message: Message;
  interruptMessage?: Message | null;
  onFeedback?: (feedback: { option: Option }) => void;
  onSendMessage?: (
    message: string,
    options?: { interruptFeedback?: string },
  ) => void;
  waitForFeedback?: boolean;
}) {
  const plan = useMemo<{
    title?: string;
    thought?: string;
    steps?: { title?: string; description?: string }[];
  }>(() => {
    return parseJSON(message.content ?? "", {});
  }, [message.content]);
  const handleAccept = useCallback(async () => {
    if (onSendMessage) {
      onSendMessage(
        `${GREETINGS[Math.floor(Math.random() * GREETINGS.length)]}! ${Math.random() > 0.5 ? "Let's get started." : "Let's start."}`,
        {
          interruptFeedback: "accepted",
        },
      );
    }
  }, [onSendMessage]);
  return (
    <Card className={cn("w-full", className)}>
      <CardHeader>
        <CardTitle>
          <Markdown animated>
            {`### ${
              plan.title !== undefined && plan.title !== ""
                ? plan.title
                : "Deep Research"
            }`}
          </Markdown>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Markdown className="opacity-80" animated>
          {plan.thought}
        </Markdown>
        {plan.steps && (
          <ul className="my-2 flex list-decimal flex-col gap-4 border-l-[2px] pl-8">
            {plan.steps.map((step, i) => (
              <li key={`step-${i}`}>
                <h3 className="mb text-lg font-medium">
                  <Markdown animated>{step.title}</Markdown>
                </h3>
                <div className="text-muted-foreground text-sm">
                  <Markdown animated>{step.description}</Markdown>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      <CardFooter className="flex justify-end">
        {!message.isStreaming && interruptMessage?.options?.length && (
          <motion.div
            className="flex gap-2"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.3 }}
          >
            {interruptMessage?.options.map((option) => (
              <Button
                key={option.value}
                variant={option.value === "accepted" ? "default" : "outline"}
                disabled={!waitForFeedback}
                onClick={() => {
                  if (option.value === "accepted") {
                    void handleAccept();
                  } else {
                    onFeedback?.({
                      option,
                    });
                  }
                }}
              >
                {option.text}
              </Button>
            ))}
          </motion.div>
        )}
      </CardFooter>
    </Card>
  );
}

function PodcastCard({
  className,
  message,
}: {
  className?: string;
  message: Message;
}) {
  const data = useMemo(() => {
    return JSON.parse(message.content ?? "");
  }, [message.content]);
  const title = useMemo<string | undefined>(() => data?.title, [data]);
  const audioUrl = useMemo<string | undefined>(() => data?.audioUrl, [data]);
  const isGenerating = useMemo(() => {
    return message.isStreaming;
  }, [message.isStreaming]);
  const hasError = useMemo(() => {
    return data?.error !== undefined;
  }, [data]);
  const [isPlaying, setIsPlaying] = useState(false);
  return (
    <Card className={cn("w-[508px]", className)}>
      <CardHeader>
        <div className="text-muted-foreground flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            {isGenerating ? <LoadingOutlined /> : <Headphones size={16} />}
            {!hasError ? (
              <RainbowText animated={isGenerating}>
                {isGenerating
                  ? "Generating podcast..."
                  : isPlaying
                    ? "Now playing podcast..."
                    : "Podcast"}
              </RainbowText>
            ) : (
              <div className="text-red-500">
                Error when generating podcast. Please try again.
              </div>
            )}
          </div>
          {!hasError && !isGenerating && (
            <div className="flex">
              <Tooltip title="Download podcast">
                <Button variant="ghost" size="icon" asChild>
                  <a
                    href={audioUrl}
                    download={`${(title ?? "podcast").replaceAll(" ", "-")}.mp3`}
                  >
                    <Download size={16} />
                  </a>
                </Button>
              </Tooltip>
            </div>
          )}
        </div>
        <CardTitle>
          <div className="text-lg font-medium">
            <RainbowText animated={isGenerating}>{title}</RainbowText>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {audioUrl ? (
          <audio
            className="w-full"
            src={audioUrl}
            controls
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
          />
        ) : (
          <div className="w-full"></div>
        )}
      </CardContent>
    </Card>
  );
}

function AgentRoleBubble({ agentName, content }: { agentName: string, content: string }) {
  const [isCollapsed, setIsCollapsed] = useState(true);

  // Get a preview of the thinking content (first few lines)
  const previewContent = useMemo(() => {
    if (!content) return "";
    const lines = content.split('\n');
    const previewLines = lines.slice(0, 3);
    return previewLines.join('\n') + (lines.length > 3 ? '...' : '');
  }, [content]);

  const capitalizedAgentName = agentName.charAt(0).toUpperCase() + agentName.slice(1);

  return (
    <div className="bg-sky-900/20 border border-sky-700/30 rounded-md text-sky-200 p-3">
      <div
        className="text-xs text-sky-300 mb-2 font-medium flex justify-between cursor-pointer"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <span>Agent Activity: {capitalizedAgentName}</span>
        <span>{isCollapsed ? "⬇️ Show details" : "⬆️ Hide details"}</span>
      </div>

      {isCollapsed ? (
        <div className="text-sm opacity-80">
          <Markdown>{previewContent}</Markdown>
          {content && content.split('\n').length > 3 && (
            <button
              className="text-sm text-sky-400 hover:text-sky-300 mt-1"
              onClick={(e) => {
                e.stopPropagation();
                setIsCollapsed(false);
              }}
            >
              Show more...
            </button>
          )}
        </div>
      ) : (
        <>
          <Markdown animated>{content}</Markdown>
          <button
            className="text-sm text-sky-400 hover:text-sky-300 mt-2"
            onClick={(e) => {
              e.stopPropagation();
              setIsCollapsed(true);
            }}
          >
            Show less
          </button>
        </>
      )}
    </div>
  );
}

function ThinkingBubble({ content }: { content: string }) {
  const [isCollapsed, setIsCollapsed] = useState(true);

  // Extract the thinking content after the marker
  const thinkingContent = useMemo(() => {
    const headerIndex = content.indexOf('\n\n');
    if (headerIndex === -1) return content;
    return content.substring(headerIndex + 2);
  }, [content]);

  // Get a preview of the thinking content (first few lines)
  const previewContent = useMemo(() => {
    const lines = thinkingContent.split('\n');
    const previewLines = lines.slice(0, 3);
    return previewLines.join('\n') + (lines.length > 3 ? '...' : '');
  }, [thinkingContent]);

  return (
    <div className="bg-slate-700/20 border border-slate-500/30 rounded-md text-slate-300 italic p-3">
      <div 
        className="text-xs text-slate-400 mb-2 font-medium flex justify-between cursor-pointer" 
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <span>AI&apos;s Thinking Process</span>
        <span>{isCollapsed ? "⬇️ Show details" : "⬆️ Hide details"}</span>
      </div>
      
      {isCollapsed ? (
        <div className="text-sm opacity-80">
          <Markdown>{previewContent}</Markdown>
          <button 
            className="text-sm text-blue-400 hover:text-blue-300 mt-1"
            onClick={(e) => {
              e.stopPropagation();
              setIsCollapsed(false);
            }}
          >
            Show more...
          </button>
        </div>
      ) : (
        <>
          <Markdown animated>{thinkingContent}</Markdown>
          <button 
            className="text-sm text-blue-400 hover:text-blue-300 mt-2"
            onClick={(e) => {
              e.stopPropagation();
              setIsCollapsed(true);
            }}
          >
            Show less
          </button>
        </>
      )}
    </div>
  );
}
