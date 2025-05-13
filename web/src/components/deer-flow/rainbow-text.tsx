// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { ReactNode } from "react";

import { cn } from "~/lib/utils";

import styles from "./rainbow-text.module.css";

export function RainbowText({
  animated,
  className,
  children,
}: {
  animated?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <span className={cn(animated && styles.animated, className)}>
      {children}
    </span>
  );
}
