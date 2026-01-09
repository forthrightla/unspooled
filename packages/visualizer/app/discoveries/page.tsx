"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { 
  Sparkles, TrendingUp, Calendar, Users, X, ChevronRight, 
  Music, Star, ArrowUpRight 
} from "lucide-react";
import { PageContainer, PageHeader, Section } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useData } from "@/lib/hooks";
import { formatNumber, formatMonth, formatDate } from "@/lib/format";
import { explorerVariants } from "@/lib/motion";

interface ArtistDiscovery {
  id: number;
  name: string;
  firstPlayed: string;
  plays: number;
}

interface YearlyData {
  year: number;
  count: number;
  topArtists: ArtistDiscovery[];
  allArtists: ArtistDiscovery[];
}

interface MonthlyData {
  yearMonth: string;
  count: number;
  artists: ArtistDiscovery[];
}

interface DiscoveriesData {
  totalDiscoveries: number;
  avgPerYear: number;
  yearsActive: number;
  peakMonth: { yearMonth: string; count: number };
  recentDiscoveries: ArtistDiscovery[];
  yearlyTimeline: YearlyData[];
  monthlyTimeline: MonthlyData[];
  gatewayArtists: { id: number; name: string; introducedCount: number }[];
}

export default function DiscoveriesPage() {
  const { data, isLoading } = useData<DiscoveriesData>("discoveries-detailed.json");
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  const selectedYearData = useMemo(() => {
    if (!selectedYear || !data) return null;
    return data.yearlyTimeline.find(y => y.year === selectedYear);
  }, [selectedYear, data]);

  if (isLoading || !data) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading discoveries...</div>
        </div>
      </PageContainer>
    );
  }

  const maxYearlyCount = Math.max(...data.yearlyTimeline.map(y => y.count));

  return (
    <PageContainer>
      <PageHeader
        title="Discoveries"
        subtitle={`${formatNumber(data.totalDiscoveries)} artists discovered over ${data.yearsActive} years`}
      />

      {/* Stats */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-12"
        variants={explorerVariants.stagger}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Total Artists Discovered"
            value={formatNumber(data.totalDiscoveries)}
            icon={<Users className="h-5 w-5" />}
          />
        </motion.div>
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Avg Per Year"
            value={formatNumber(Math.round(data.avgPerYear))}
            icon={<TrendingUp className="h-5 w-5" />}
          />
        </motion.div>
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Years of Discovery"
            value={data.yearsActive.toString()}
            icon={<Calendar className="h-5 w-5" />}
          />
        </motion.div>
        <motion.div variants={explorerVariants.staggerItem}>
          <StatCard
            label="Peak Month"
            value={data.peakMonth.count.toString()}
            subValue={formatMonth(data.peakMonth.yearMonth)}
            icon={<Sparkles className="h-5 w-5" />}
          />
        </motion.div>
      </motion.div>

      {/* Discovery Timeline */}
      <Section 
        title="Discovery Timeline" 
        subtitle="Click any year to see who you discovered"
      >
        <div className="space-y-2">
          {data.yearlyTimeline.map((item, index) => (
            <motion.button
              key={item.year}
              className={`w-full flex items-center gap-4 p-3 rounded-xl transition-all ${
                selectedYear === item.year 
                  ? "bg-accent/20 ring-2 ring-accent" 
                  : "hover:bg-surface-elevated"
              }`}
              onClick={() => setSelectedYear(selectedYear === item.year ? null : item.year)}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.03 }}
            >
              <span className="w-16 text-text-primary font-display text-lg">{item.year}</span>
              <div className="flex-1 h-10 bg-surface rounded-lg overflow-hidden relative">
                <motion.div
                  className="h-full bg-gradient-to-r from-violet-500 via-pink-500 to-orange-400 rounded-lg"
                  initial={{ width: 0 }}
                  animate={{ width: `${(item.count / maxYearlyCount) * 100}%` }}
                  transition={{ delay: index * 0.03 + 0.1, duration: 0.5 }}
                />
                {/* Top discovery preview */}
                <div className="absolute inset-0 flex items-center px-3">
                  {item.topArtists[0] && (
                    <span className="text-sm text-white/80 truncate">
                      {item.topArtists[0].name}
                      {item.topArtists.length > 1 && ` +${item.count - 1} more`}
                    </span>
                  )}
                </div>
              </div>
              <span className="w-20 text-right font-medium text-text-primary">
                {item.count} <span className="text-text-muted text-sm">artists</span>
              </span>
              <ChevronRight className={`h-5 w-5 text-text-muted transition-transform ${
                selectedYear === item.year ? "rotate-90" : ""
              }`} />
            </motion.button>
          ))}
        </div>
      </Section>

      {/* Year Detail Modal/Panel */}
      <AnimatePresence>
        {selectedYearData && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSelectedYear(null)}
          >
            <motion.div
              className="bg-surface-elevated border border-border-subtle rounded-2xl w-full max-w-3xl max-h-[80vh] overflow-hidden shadow-2xl"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="p-6 border-b border-border-subtle bg-gradient-to-r from-violet-500/10 via-pink-500/10 to-orange-400/10">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-display-md text-text-primary font-display">
                      {selectedYearData.year}
                    </h2>
                    <p className="text-text-secondary">
                      {selectedYearData.count} new artists discovered
                    </p>
                  </div>
                  <button
                    onClick={() => setSelectedYear(null)}
                    className="p-2 rounded-full hover:bg-white/10 transition-colors"
                  >
                    <X className="h-6 w-6 text-text-muted" />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="p-6 overflow-y-auto max-h-[calc(80vh-120px)]">
                {/* Top Discoveries */}
                <div className="mb-8">
                  <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Star className="h-4 w-4 text-amber-400" />
                    Top Discoveries of {selectedYearData.year}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {selectedYearData.topArtists.slice(0, 6).map((artist, i) => (
                      <Link key={artist.id} href={`/artists/${artist.id}`}>
                        <motion.div
                          className="p-4 rounded-xl bg-surface border border-border-subtle hover:border-accent/50 transition-all group"
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.05 }}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-medium text-accent">#{i + 1}</span>
                                <h4 className="font-medium text-text-primary truncate group-hover:text-accent transition-colors">
                                  {artist.name}
                                </h4>
                              </div>
                              <p className="text-caption text-text-muted mt-1">
                                Discovered {formatDate(artist.firstPlayed, { format: "short" })}
                              </p>
                            </div>
                            <div className="text-right">
                              <p className="text-lg font-display text-text-primary">
                                {formatNumber(artist.plays)}
                              </p>
                              <p className="text-caption text-text-muted">plays since</p>
                            </div>
                          </div>
                        </motion.div>
                      </Link>
                    ))}
                  </div>
                </div>

                {/* All Discoveries */}
                <div>
                  <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Music className="h-4 w-4" />
                    All {selectedYearData.count} Artists (Chronological)
                  </h3>
                  <div className="space-y-1 max-h-64 overflow-y-auto">
                    {selectedYearData.allArtists.map((artist, i) => (
                      <Link key={artist.id} href={`/artists/${artist.id}`}>
                        <motion.div
                          className="flex items-center justify-between p-2 rounded-lg hover:bg-white/5 transition-colors group"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: Math.min(i * 0.01, 0.5) }}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="text-xs text-text-muted w-8">
                              {formatDate(artist.firstPlayed, { format: "short" }).split(",")[0]}
                            </span>
                            <span className="text-text-primary truncate group-hover:text-accent transition-colors">
                              {artist.name}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-text-muted">
                              {formatNumber(artist.plays)} plays
                            </span>
                            <ArrowUpRight className="h-4 w-4 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                        </motion.div>
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Recent Discoveries */}
      <Section 
        title="Recent Discoveries" 
        subtitle="Your newest musical finds"
      >
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
          variants={explorerVariants.stagger}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
        >
          {data.recentDiscoveries.slice(0, 12).map((artist) => (
            <motion.div key={artist.id} variants={explorerVariants.staggerItem}>
              <Link href={`/artists/${artist.id}`}>
                <Card hover padding="md" className="group">
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <h3 className="font-medium text-text-primary truncate group-hover:text-accent transition-colors">
                        {artist.name}
                      </h3>
                      <p className="text-caption flex items-center gap-1 text-text-muted">
                        <Calendar className="h-3 w-3" />
                        {formatDate(artist.firstPlayed, { format: "short" })}
                      </p>
                    </div>
                    <Badge variant="muted" size="sm">
                      {formatNumber(artist.plays)} plays
                    </Badge>
                  </div>
                </Card>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      </Section>

      {/* Gateway Artists */}
      {data.gatewayArtists.length > 0 && (
        <Section 
          title="Gateway Artists" 
          subtitle="Artists that led you to discover new music"
        >
          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-3"
            variants={explorerVariants.stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
          >
            {data.gatewayArtists.slice(0, 8).map((artist) => (
              <motion.div key={artist.id} variants={explorerVariants.staggerItem}>
                <Link href={`/artists/${artist.id}`}>
                  <Card hover padding="md" className="text-center group">
                    <h3 className="font-medium text-text-primary truncate group-hover:text-accent transition-colors">
                      {artist.name}
                    </h3>
                    <p className="text-caption text-text-muted mt-1">
                      Led to <span className="text-accent">{artist.introducedCount}</span> discoveries
                    </p>
                  </Card>
                </Link>
              </motion.div>
            ))}
          </motion.div>
        </Section>
      )}
    </PageContainer>
  );
}
