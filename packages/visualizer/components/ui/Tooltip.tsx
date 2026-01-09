"use client";

import { useState, useRef, useEffect, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { explorerVariants } from "@/lib/motion";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  delay?: number;
}

export function Tooltip({
  content,
  children,
  side = "top",
  delay = 200,
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  const showTooltip = () => {
    timeoutRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delay);
  };

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsVisible(false);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const positionStyles = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  const arrowStyles = {
    top: "top-full left-1/2 -translate-x-1/2 border-t-surface-elevated border-x-transparent border-b-transparent",
    bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-surface-elevated border-x-transparent border-t-transparent",
    left: "left-full top-1/2 -translate-y-1/2 border-l-surface-elevated border-y-transparent border-r-transparent",
    right: "right-full top-1/2 -translate-y-1/2 border-r-surface-elevated border-y-transparent border-l-transparent",
  };

  return (
    <div
      ref={triggerRef}
      className="relative inline-flex"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      <AnimatePresence>
        {isVisible && (
          <motion.div
            className={`absolute z-50 ${positionStyles[side]}`}
            variants={explorerVariants.tooltip}
            initial="hidden"
            animate="visible"
            exit="hidden"
          >
            <div className="bg-surface-elevated text-text-primary text-sm px-3 py-2 rounded-lg shadow-lg border border-border-subtle whitespace-nowrap">
              {content}
            </div>
            <div
              className={`absolute w-0 h-0 border-4 ${arrowStyles[side]}`}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Info tooltip with icon
interface InfoTooltipProps {
  content: ReactNode;
}

export function InfoTooltip({ content }: InfoTooltipProps) {
  return (
    <Tooltip content={content}>
      <button
        type="button"
        className="inline-flex items-center justify-center w-4 h-4 text-text-muted hover:text-text-secondary transition-colors"
        aria-label="More information"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-4 h-4"
        >
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    </Tooltip>
  );
}


