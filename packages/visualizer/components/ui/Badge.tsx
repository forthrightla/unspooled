"use client";

import { HTMLAttributes } from "react";

type BadgeVariant = "default" | "accent" | "success" | "warning" | "muted";
type BadgeSize = "sm" | "md";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: BadgeSize;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-surface-elevated text-text-primary border-border-subtle",
  accent: "bg-accent-muted text-accent border-accent/30",
  success: "bg-green-500/15 text-green-400 border-green-500/30",
  warning: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  muted: "bg-surface text-text-muted border-border-subtle",
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "text-xs px-2 py-0.5",
  md: "text-sm px-2.5 py-1",
};

export function Badge({
  variant = "default",
  size = "sm",
  className = "",
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center
        font-medium rounded-full
        border
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
      {...props}
    >
      {children}
    </span>
  );
}

// Numeric badge for counts
interface CountBadgeProps {
  count: number;
  max?: number;
}

export function CountBadge({ count, max = 99 }: CountBadgeProps) {
  const displayCount = count > max ? `${max}+` : count;
  
  return (
    <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 text-xs font-medium bg-accent text-white rounded-full">
      {displayCount}
    </span>
  );
}

// Dot indicator
interface DotProps {
  color?: "accent" | "success" | "warning" | "error";
  pulse?: boolean;
}

export function Dot({ color = "accent", pulse = false }: DotProps) {
  const colorStyles = {
    accent: "bg-accent",
    success: "bg-green-500",
    warning: "bg-yellow-500",
    error: "bg-red-500",
  };

  return (
    <span className="relative flex h-2 w-2">
      {pulse && (
        <span
          className={`absolute inline-flex h-full w-full rounded-full ${colorStyles[color]} opacity-75 animate-ping`}
        />
      )}
      <span
        className={`relative inline-flex rounded-full h-2 w-2 ${colorStyles[color]}`}
      />
    </span>
  );
}


