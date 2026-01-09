"use client";

import { motion } from "framer-motion";
import { explorerVariants } from "@/lib/motion";
import { Card } from "./Card";

interface StatCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    label?: string;
  };
  className?: string;
}

export function StatCard({
  label,
  value,
  subValue,
  icon,
  trend,
  className = "",
}: StatCardProps) {
  return (
    <Card variant="default" padding="md" className={className}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-caption truncate">{label}</p>
          <motion.p
            className="stat-number mt-1"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            {value}
          </motion.p>
          {subValue && (
            <p className="text-sm text-text-muted mt-1">{subValue}</p>
          )}
          {trend && (
            <div className="flex items-center gap-1 mt-2">
              <TrendIndicator value={trend.value} />
              {trend.label && (
                <span className="text-xs text-text-muted">{trend.label}</span>
              )}
            </div>
          )}
        </div>
        {icon && (
          <div className="flex-shrink-0 text-text-muted">{icon}</div>
        )}
      </div>
    </Card>
  );
}

// Trend indicator
function TrendIndicator({ value }: { value: number }) {
  const isPositive = value > 0;
  const isNeutral = value === 0;

  if (isNeutral) {
    return (
      <span className="text-xs text-text-muted">—</span>
    );
  }

  return (
    <span
      className={`text-xs font-medium ${
        isPositive ? "text-green-400" : "text-red-400"
      }`}
    >
      {isPositive ? "+" : ""}
      {value}%
    </span>
  );
}

// Large stat display for hero sections
interface HeroStatProps {
  value: string | number;
  label: string;
  sublabel?: string;
}

export function HeroStat({ value, label, sublabel }: HeroStatProps) {
  return (
    <motion.div
      className="text-center"
      variants={explorerVariants.slideUp}
      initial="hidden"
      animate="visible"
    >
      <motion.p
        className="text-display-xl gradient-text"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.5 }}
      >
        {value}
      </motion.p>
      <p className="text-heading text-text-secondary mt-2">{label}</p>
      {sublabel && (
        <p className="text-caption mt-1">{sublabel}</p>
      )}
    </motion.div>
  );
}

// Story mode big stat for wrapped-style reveals
interface StoryStatProps {
  value: string | number;
  label: string;
  gradient?: "warm" | "cool" | "electric" | "sunset";
}

export function StoryStat({ value, label, gradient = "warm" }: StoryStatProps) {
  const gradientStyles = {
    warm: "from-orange-400 via-pink-500 to-violet-500",
    cool: "from-cyan-400 via-violet-500 to-pink-500",
    electric: "from-cyan-300 to-violet-500",
    sunset: "from-orange-400 to-pink-500",
  };

  return (
    <div className="text-center">
      <motion.p
        className={`story-headline bg-gradient-to-r ${gradientStyles[gradient]} bg-clip-text text-transparent`}
        initial={{ opacity: 0, scale: 0.5, y: 30 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
      >
        {value}
      </motion.p>
      <motion.p
        className="text-xl md:text-2xl text-white/80 mt-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        {label}
      </motion.p>
    </div>
  );
}

// Inline stat for lists/tables
interface InlineStatProps {
  value: string | number;
  label?: string;
  size?: "sm" | "md";
}

export function InlineStat({ value, label, size = "md" }: InlineStatProps) {
  return (
    <div className={`flex items-baseline gap-1 ${size === "sm" ? "text-sm" : ""}`}>
      <span className="font-mono font-medium text-text-primary">{value}</span>
      {label && <span className="text-text-muted">{label}</span>}
    </div>
  );
}


