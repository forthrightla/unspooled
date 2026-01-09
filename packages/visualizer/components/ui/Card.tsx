"use client";

import { forwardRef, HTMLAttributes } from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { explorerVariants } from "@/lib/motion";

interface CardProps extends HTMLMotionProps<"div"> {
  variant?: "default" | "elevated" | "ghost" | "gradient";
  hover?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingStyles = {
  none: "",
  sm: "p-3",
  md: "p-4 md:p-5",
  lg: "p-6 md:p-8",
};

const variantStyles = {
  default: "bg-surface border border-border-subtle",
  elevated: "bg-surface-elevated border border-border shadow-lg",
  ghost: "bg-transparent",
  gradient: "bg-gradient-to-br from-surface to-surface-elevated border border-border-subtle",
};

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ 
    variant = "default", 
    hover = false, 
    padding = "md",
    className = "", 
    children, 
    ...props 
  }, ref) => {
    return (
      <motion.div
        ref={ref}
        className={`
          rounded-xl
          ${variantStyles[variant]}
          ${paddingStyles[padding]}
          ${hover ? "cursor-pointer transition-colors hover:border-border" : ""}
          ${className}
        `}
        variants={hover ? explorerVariants.cardHover : undefined}
        initial={hover ? "rest" : undefined}
        whileHover={hover ? "hover" : undefined}
        whileTap={hover ? "tap" : undefined}
        {...props}
      >
        {children}
      </motion.div>
    );
  }
);

Card.displayName = "Card";

// Card Header
interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function CardHeader({ 
  title, 
  subtitle, 
  action, 
  className = "",
  ...props 
}: CardHeaderProps) {
  return (
    <div className={`flex items-start justify-between gap-4 ${className}`} {...props}>
      <div>
        <h3 className="text-heading text-text-primary">{title}</h3>
        {subtitle && (
          <p className="text-caption mt-1">{subtitle}</p>
        )}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}

// Card Content
interface CardContentProps extends HTMLAttributes<HTMLDivElement> {}

export function CardContent({ className = "", children, ...props }: CardContentProps) {
  return (
    <div className={`mt-4 ${className}`} {...props}>
      {children}
    </div>
  );
}

// Card Footer
interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {}

export function CardFooter({ className = "", children, ...props }: CardFooterProps) {
  return (
    <div 
      className={`mt-4 pt-4 border-t border-border-subtle flex items-center justify-between ${className}`} 
      {...props}
    >
      {children}
    </div>
  );
}


