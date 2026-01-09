"use client";

import { motion } from "framer-motion";
import { pageVariants } from "@/lib/motion";

interface PageContainerProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "story";
}

export function PageContainer({ 
  children, 
  className = "",
  variant = "default"
}: PageContainerProps) {
  return (
    <motion.main
      className={`min-h-screen bg-base ${className}`}
      variants={pageVariants[variant]}
      initial="hidden"
      animate="visible"
      exit="exit"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 pb-32">
        {children}
      </div>
    </motion.main>
  );
}

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <motion.header
      className="mb-8 md:mb-12"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-display-lg text-text-primary">{title}</h1>
          {subtitle && (
            <p className="text-body text-text-secondary mt-2 max-w-2xl">
              {subtitle}
            </p>
          )}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
    </motion.header>
  );
}

interface SectionProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}

export function Section({ title, subtitle, children, className = "" }: SectionProps) {
  return (
    <section className={`mb-12 ${className}`}>
      {title && (
        <div className="mb-6">
          <h2 className="text-heading text-text-primary">{title}</h2>
          {subtitle && (
            <p className="text-caption mt-1">{subtitle}</p>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

