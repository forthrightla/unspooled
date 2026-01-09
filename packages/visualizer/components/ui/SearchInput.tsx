"use client";

import { forwardRef, InputHTMLAttributes } from "react";
import { Search, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface SearchInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange"> {
  value: string;
  onChange: (value: string) => void;
  onClear?: () => void;
}

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  ({ value, onChange, onClear, className = "", placeholder = "Search...", ...props }, ref) => {
    const handleClear = () => {
      onChange("");
      onClear?.();
    };

    return (
      <div className={`relative ${className}`}>
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-text-muted" />
        <input
          ref={ref}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="
            w-full h-12 pl-12 pr-12
            bg-surface border border-border-subtle rounded-xl
            text-text-primary placeholder:text-text-muted
            focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
            transition-colors
          "
          {...props}
        />
        <AnimatePresence>
          {value && (
            <motion.button
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              onClick={handleClear}
              className="absolute right-4 top-1/2 -translate-y-1/2 p-1 hover:bg-surface-elevated rounded-full transition-colors"
            >
              <X className="h-4 w-4 text-text-muted" />
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    );
  }
);

SearchInput.displayName = "SearchInput";

