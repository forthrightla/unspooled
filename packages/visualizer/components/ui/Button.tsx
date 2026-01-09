"use client";

import { forwardRef, ButtonHTMLAttributes } from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { explorerVariants } from "@/lib/motion";

type ButtonVariant = "primary" | "secondary" | "ghost" | "outline";
type ButtonSize = "sm" | "md" | "lg" | "icon";

interface ButtonProps extends Omit<HTMLMotionProps<"button">, "size"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: `
    bg-accent text-white
    hover:bg-accent-hover
    active:bg-accent
  `,
  secondary: `
    bg-surface-elevated text-text-primary
    hover:bg-surface-hover
    border border-border-subtle
  `,
  ghost: `
    bg-transparent text-text-secondary
    hover:text-text-primary hover:bg-surface
  `,
  outline: `
    bg-transparent text-text-primary
    border border-border
    hover:bg-surface hover:border-text-muted
  `,
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2.5",
  icon: "h-10 w-10 p-0 justify-center",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      isLoading = false,
      leftIcon,
      rightIcon,
      className = "",
      children,
      disabled,
      ...props
    },
    ref
  ) => {
    return (
      <motion.button
        ref={ref}
        className={`
          inline-flex items-center justify-center
          font-medium rounded-lg
          transition-colors duration-150
          focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-base
          disabled:opacity-50 disabled:cursor-not-allowed
          ${variantStyles[variant]}
          ${sizeStyles[size]}
          ${className}
        `}
        variants={explorerVariants.button}
        initial="rest"
        whileHover={disabled ? undefined : "hover"}
        whileTap={disabled ? undefined : "tap"}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <>
            {leftIcon && <span className="flex-shrink-0">{leftIcon}</span>}
            {children}
            {rightIcon && <span className="flex-shrink-0">{rightIcon}</span>}
          </>
        )}
      </motion.button>
    );
  }
);

Button.displayName = "Button";

// Loading spinner component
function LoadingSpinner() {
  return (
    <svg
      className="animate-spin h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

// Icon button variant for convenience
interface IconButtonProps extends Omit<ButtonProps, "size" | "leftIcon" | "rightIcon"> {
  label: string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ label, children, ...props }, ref) => {
    return (
      <Button ref={ref} size="icon" aria-label={label} {...props}>
        {children}
      </Button>
    );
  }
);

IconButton.displayName = "IconButton";


