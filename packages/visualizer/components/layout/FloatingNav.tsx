"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Home, 
  Clock, 
  Users, 
  Search, 
  Sparkles,
  BarChart3,
  Compass,
  Menu,
  X
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { explorerVariants } from "@/lib/motion";

const navItems = [
  { icon: Home, label: "Home", href: "/" },
  { icon: Clock, label: "Timeline", href: "/timeline" },
  { icon: Users, label: "Artists", href: "/artists" },
  { icon: Compass, label: "Discoveries", href: "/discoveries" },
  { icon: BarChart3, label: "Patterns", href: "/patterns" },
  { icon: Sparkles, label: "Story", href: "/story" },
  { icon: Search, label: "Search", href: "/search" },
];

export function FloatingNav() {
  const pathname = usePathname();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <motion.nav
      className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2"
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.3, type: "spring", stiffness: 300, damping: 25 }}
    >
      {/* Desktop Nav */}
      <div className="hidden md:flex glass items-center gap-1 rounded-full border border-border-subtle px-2 py-2 shadow-lg">
        {navItems.map((item) => {
          const isActive = pathname === item.href || 
            (item.href !== "/" && pathname.startsWith(item.href));
          
          return (
            <Link key={item.label} href={item.href}>
              <motion.div
                className={`
                  flex items-center gap-2 rounded-full px-4 py-2 
                  transition-colors relative
                  ${isActive 
                    ? "text-text-primary" 
                    : "text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
                  }
                `}
                variants={explorerVariants.button}
                whileHover="hover"
                whileTap="tap"
              >
                {isActive && (
                  <motion.div
                    className="absolute inset-0 bg-accent/20 rounded-full"
                    layoutId="nav-active"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
                <item.icon className="h-4 w-4 relative z-10" />
                <span className="text-sm font-medium relative z-10">{item.label}</span>
              </motion.div>
            </Link>
          );
        })}
      </div>

      {/* Mobile Nav */}
      <div className="md:hidden">
        <AnimatePresence>
          {isExpanded && (
            <motion.div
              className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 glass rounded-2xl border border-border-subtle p-2 shadow-lg"
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
            >
              <div className="grid grid-cols-4 gap-1">
                {navItems.map((item) => {
                  const isActive = pathname === item.href;
                  return (
                    <Link 
                      key={item.label} 
                      href={item.href}
                      onClick={() => setIsExpanded(false)}
                    >
                      <div
                        className={`
                          flex flex-col items-center gap-1 rounded-xl px-3 py-2
                          ${isActive 
                            ? "bg-accent/20 text-text-primary" 
                            : "text-text-secondary"
                          }
                        `}
                      >
                        <item.icon className="h-5 w-5" />
                        <span className="text-xs">{item.label}</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="glass flex items-center justify-center w-14 h-14 rounded-full border border-border-subtle shadow-lg"
        >
          {isExpanded ? (
            <X className="h-6 w-6 text-text-primary" />
          ) : (
            <Menu className="h-6 w-6 text-text-primary" />
          )}
        </button>
      </div>
    </motion.nav>
  );
}

