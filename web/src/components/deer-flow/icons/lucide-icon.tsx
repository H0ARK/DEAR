// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import * as LucideIcons from "lucide-react";
import { type LucideProps } from "lucide-react";
import { type ComponentType, type ElementType } from "react";

import { cn } from "~/lib/utils";

// Define a mapping of icon names to their components
const iconComponents: Record<string, ElementType> = {
  // Add lowercase mappings for common icons
  // We'll dynamically look up icons by capitalizing the first letter
};

// For TypeScript type checking
export type LucideIconName = keyof typeof iconComponents | keyof typeof LucideIcons;

export interface LucideIconProps extends Omit<LucideProps, "ref"> {
  name: LucideIconName;
  className?: string;
}

export type LucideIcon = LucideIconName | ComponentType<LucideProps>;

export function LucideIcon({ name, className, ...props }: LucideIconProps) {
  // First check our custom mapping
  let IconComponent = iconComponents[name as string];

  // If not found in custom mapping, try to get it from LucideIcons
  if (!IconComponent) {
    // Try with the exact name
    IconComponent = LucideIcons[name as keyof typeof LucideIcons] as ElementType;

    // If not found, try with capitalized first letter (common naming convention)
    if (!IconComponent && typeof name === 'string') {
      const capitalizedName = name.charAt(0).toUpperCase() + name.slice(1);
      IconComponent = LucideIcons[capitalizedName as keyof typeof LucideIcons] as ElementType;
    }
  }

  if (!IconComponent) {
    console.error(`Icon "${name}" not found in lucide-react`);
    return null;
  }

  return <IconComponent className={cn("size-5", className)} {...props} />;
}
