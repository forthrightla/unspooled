"use client";

import { motion } from "framer-motion";
import { Sun, Moon, Coffee, Sunset } from "lucide-react";
import { PageContainer, PageHeader, Section } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";
import { useData } from "@/lib/hooks";
import { formatNumber, formatHour } from "@/lib/format";
import { explorerVariants } from "@/lib/motion";

interface TemporalData {
  hourly: { hour: number; plays: number; avgPerDay: number }[];
  weekday: { day: number; plays: number; avgPerWeek: number }[];
  insights: {
    peakHour: number;
    peakDay: number;
    nightOwlScore: number;
    weekendWarriorScore: number;
  };
}

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export default function PatternsPage() {
  const { data: temporal, isLoading } = useData<TemporalData>("temporal.json");

  if (isLoading || !temporal) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading patterns...</div>
        </div>
      </PageContainer>
    );
  }

  const maxHourlyPlays = Math.max(...temporal.hourly.map((h) => h.plays));
  const maxWeekdayPlays = Math.max(...temporal.weekday.map((d) => d.plays));

  const getTimeOfDayIcon = (hour: number) => {
    if (hour >= 5 && hour < 12) return <Coffee className="h-5 w-5" />;
    if (hour >= 12 && hour < 17) return <Sun className="h-5 w-5" />;
    if (hour >= 17 && hour < 21) return <Sunset className="h-5 w-5" />;
    return <Moon className="h-5 w-5" />;
  };

  const getTimeOfDayLabel = (hour: number) => {
    if (hour >= 5 && hour < 12) return "Morning Person";
    if (hour >= 12 && hour < 17) return "Afternoon Listener";
    if (hour >= 17 && hour < 21) return "Evening Vibes";
    return "Night Owl";
  };

  return (
    <PageContainer>
      <PageHeader
        title="Patterns"
        subtitle="Discover when and how you listen to music"
      />

      {/* Key Insights */}
      <motion.div
        className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12"
        variants={explorerVariants.stagger}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Peak Hour"
            value={formatHour(temporal.insights.peakHour)}
            icon={getTimeOfDayIcon(temporal.insights.peakHour)}
          />
        </motion.div>
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Peak Day"
            value={WEEKDAYS[temporal.insights.peakDay]}
            subValue={`${formatNumber(temporal.weekday[temporal.insights.peakDay].plays)} plays`}
          />
        </motion.div>
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Night Owl Score"
            value={`${Math.round(temporal.insights.nightOwlScore * 100)}%`}
            subValue={temporal.insights.nightOwlScore > 0.5 ? "You're a night owl!" : "Early bird"}
          />
        </motion.div>
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Weekend Warrior"
            value={`${Math.round(temporal.insights.weekendWarriorScore * 100)}%`}
            subValue={temporal.insights.weekendWarriorScore > 0.3 ? "Weekend heavy" : "Weekday listener"}
          />
        </motion.div>
      </motion.div>

      {/* Listening Personality */}
      <Section>
        <Card variant="gradient" padding="lg" className="mb-12">
          <div className="flex items-center gap-4">
            {getTimeOfDayIcon(temporal.insights.peakHour)}
            <div>
              <Badge variant="accent" className="mb-2">Your Listening Style</Badge>
              <h3 className="text-display-md text-text-primary">
                {getTimeOfDayLabel(temporal.insights.peakHour)}
              </h3>
              <p className="text-text-secondary mt-2">
                You listen to most of your music around {formatHour(temporal.insights.peakHour)}, 
                with {WEEKDAYS[temporal.insights.peakDay]}s being your most active day.
              </p>
            </div>
          </div>
        </Card>
      </Section>

      {/* Hourly Distribution */}
      <Section title="By Hour of Day" subtitle="When do you listen the most?">
        <Card padding="lg">
          <div className="flex items-end gap-1 h-48">
            {temporal.hourly.map((hour, index) => (
              <motion.div
                key={hour.hour}
                className="flex-1 flex flex-col items-center gap-2"
                initial={{ height: 0 }}
                animate={{ height: "100%" }}
                transition={{ delay: index * 0.02 }}
              >
                <div className="flex-1 w-full flex items-end">
                  <motion.div
                    className={`w-full rounded-t ${
                      hour.hour === temporal.insights.peakHour
                        ? "bg-accent"
                        : "bg-surface-elevated hover:bg-surface-hover"
                    } transition-colors`}
                    initial={{ height: 0 }}
                    animate={{ height: `${(hour.plays / maxHourlyPlays) * 100}%` }}
                    transition={{ delay: index * 0.02 + 0.3, duration: 0.4 }}
                  />
                </div>
                <span className="text-xs text-text-muted">
                  {hour.hour % 6 === 0 ? formatHour(hour.hour).replace(" ", "") : ""}
                </span>
              </motion.div>
            ))}
          </div>
        </Card>
      </Section>

      {/* Weekday Distribution */}
      <Section title="By Day of Week" subtitle="Which days do you listen most?">
        <div className="space-y-3">
          {temporal.weekday.map((day, index) => (
            <motion.div
              key={day.day}
              className="flex items-center gap-4"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <span className={`w-24 font-medium ${
                day.day === temporal.insights.peakDay 
                  ? "text-accent" 
                  : "text-text-primary"
              }`}>
                {WEEKDAYS[day.day]}
              </span>
              <div className="flex-1 h-10 bg-surface rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    day.day === temporal.insights.peakDay
                      ? "bg-gradient-to-r from-accent to-accent-hover"
                      : "bg-surface-elevated"
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${(day.plays / maxWeekdayPlays) * 100}%` }}
                  transition={{ delay: index * 0.05 + 0.2, duration: 0.5 }}
                />
              </div>
              <span className="w-20 text-right text-text-secondary">
                {formatNumber(day.plays)}
              </span>
            </motion.div>
          ))}
        </div>
      </Section>
    </PageContainer>
  );
}

