"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { Play, Sparkles, Music, Calendar } from "lucide-react";
import { PageContainer, PageHeader } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { useData } from "@/lib/hooks";
import { formatNumber } from "@/lib/format";
import { explorerVariants } from "@/lib/motion";

interface OverviewData {
  totalPlays: number;
  firstPlay: string;
  lastPlay: string;
}

interface TimelineMonth {
  yearMonth: string;
  plays: number;
  durationHours: number;
  uniqueArtists: number;
  newDiscoveries: number;
  topArtist: {
    id: number;
    name: string;
    plays: number;
  };
}

interface YearSummary {
  year: number;
  totalPlays: number;
  totalHours: number;
  uniqueArtists: number;
  newDiscoveries: number;
  topArtist: {
    name: string;
    plays: number;
  };
}

const gradients = [
  "from-orange-500 via-pink-500 to-violet-600",
  "from-cyan-400 via-blue-500 to-purple-600",
  "from-emerald-400 via-teal-500 to-cyan-600",
  "from-rose-400 via-fuchsia-500 to-indigo-600",
  "from-amber-400 via-orange-500 to-red-600",
];

export default function StoryLandingPage() {
  const { data: overview } = useData<OverviewData>("overview.json");
  const { data: timeline, isLoading } = useData<TimelineMonth[]>("timeline.json");

  // Aggregate timeline data by year
  const yearSummaries: YearSummary[] = timeline
    ? Object.entries(
        timeline.reduce((acc, month) => {
          const year = parseInt(month.yearMonth.split("-")[0]);
          if (!acc[year]) {
            acc[year] = {
              year,
              totalPlays: 0,
              totalHours: 0,
              uniqueArtists: new Set<number>(),
              newDiscoveries: 0,
              artistPlays: new Map<string, { name: string; plays: number }>(),
            };
          }
          acc[year].totalPlays += month.plays;
          acc[year].totalHours += month.durationHours || 0;
          acc[year].newDiscoveries += month.newDiscoveries;
          
          // Track artist plays for the year
          const artistKey = month.topArtist.name;
          const existing = acc[year].artistPlays.get(artistKey);
          if (existing) {
            existing.plays += month.topArtist.plays;
          } else {
            acc[year].artistPlays.set(artistKey, {
              name: month.topArtist.name,
              plays: month.topArtist.plays,
            });
          }
          
          return acc;
        }, {} as Record<number, {
          year: number;
          totalPlays: number;
          totalHours: number;
          uniqueArtists: Set<number>;
          newDiscoveries: number;
          artistPlays: Map<string, { name: string; plays: number }>;
        }>)
      )
        .map(([_, data]) => {
          // Find top artist for the year
          let topArtist = { name: "Unknown", plays: 0 };
          data.artistPlays.forEach((artist) => {
            if (artist.plays > topArtist.plays) {
              topArtist = artist;
            }
          });
          
          return {
            year: data.year,
            totalPlays: data.totalPlays,
            totalHours: Math.round(data.totalHours),
            uniqueArtists: data.artistPlays.size,
            newDiscoveries: data.newDiscoveries,
            topArtist,
          };
        })
        .filter((y) => y.totalPlays > 0)
        .sort((a, b) => b.year - a.year)
    : [];

  if (isLoading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading your stories...</div>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Your Music Stories"
        subtitle="Relive your listening journey year by year"
      />

      {/* Hero Section */}
      <motion.div
        className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-violet-600 via-purple-600 to-pink-600 p-8 md:p-12 mb-12"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="absolute inset-0 bg-black/20" />
        <div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2" />
        
        <div className="relative z-10 text-center">
          <Sparkles className="w-12 h-12 text-white/80 mx-auto mb-4" />
          <h2 className="text-3xl md:text-4xl font-display text-white mb-3">
            {overview ? new Date(overview.lastPlay).getFullYear() - new Date(overview.firstPlay).getFullYear() : yearSummaries.length} Years of Music
          </h2>
          <p className="text-white/80 text-lg max-w-md mx-auto">
            {formatNumber(overview?.totalPlays || 0)} total plays across your listening history
          </p>
        </div>
      </motion.div>

      {/* Year Grid */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        variants={explorerVariants.stagger}
        initial="hidden"
        animate="visible"
      >
        {yearSummaries.map((year, index) => (
          <motion.div key={year.year} variants={explorerVariants.staggerItem}>
            <Link href={`/story/${year.year}`}>
              <Card
                hover
                padding="none"
                className="overflow-hidden group cursor-pointer"
              >
                {/* Gradient Header */}
                <div
                  className={`h-24 bg-gradient-to-br ${gradients[index % gradients.length]} relative`}
                >
                  <div className="absolute inset-0 bg-black/20 group-hover:bg-black/10 transition-colors" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-5xl font-display text-white font-bold drop-shadow-lg">
                      {year.year}
                    </span>
                  </div>
                  
                  {/* Play Button Overlay */}
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="w-14 h-14 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
                      <Play className="w-6 h-6 text-gray-900 ml-1" />
                    </div>
                  </div>
                </div>

                {/* Stats */}
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-text-secondary">
                      <Music className="w-4 h-4" />
                      <span className="text-sm">{formatNumber(year.totalPlays)} plays</span>
                    </div>
                    {year.totalHours > 0 && (
                      <div className="flex items-center gap-2 text-text-secondary">
                        <Calendar className="w-4 h-4" />
                        <span className="text-sm">{formatNumber(year.totalHours)}h</span>
                      </div>
                    )}
                  </div>
                  
                  <div className="pt-2 border-t border-border-subtle">
                    <p className="text-caption text-text-muted">Top Artist</p>
                    <p className="text-sm text-text-primary font-medium truncate">
                      {year.topArtist.name}
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          </motion.div>
        ))}
      </motion.div>

      {yearSummaries.length === 0 && (
        <div className="text-center py-20 text-text-muted">
          No listening data available
        </div>
      )}
    </PageContainer>
  );
}

