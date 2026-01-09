"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { Play, Sparkles, ArrowRight, Clock, Calendar, TrendingUp, Users, Disc3, Moon, Sun, Music, Zap } from "lucide-react";
import { useData } from "@/lib/hooks";
import { formatNumber } from "@/lib/format";

interface OverviewData {
  totalPlays: number;
  totalDurationHours: number;
  totalArtists: number;
  totalAlbums: number;
  totalTracks: number;
  firstPlay: string;
  lastPlay: string;
  topArtist: { id: number; name: string; plays: number };
  topAlbum: { id: number; title: string; artistName: string; plays: number };
  topTrack: { id: number; title: string; artistName: string; plays: number };
}

interface TopArtist {
  id: number;
  name: string;
  plays: number;
}

interface TimelineMonth {
  yearMonth: string;
  plays: number;
  durationHours: number;
  newDiscoveries: number;
  uniqueArtists: number;
}

interface TemporalData {
  hourly: { hour: number; plays: number }[];
  weekday: { day: number; plays: number }[];
  insights: {
    peakHour: number;
    peakDay: number;
    nightOwlScore: number;
    weekendWarriorScore: number;
  };
}

interface DiscoveriesData {
  totalDiscoveries: number;
  recentDiscoveries: { id: number; name: string; firstPlayed: string; plays: number }[];
  peakMonth: { yearMonth: string; count: number };
}

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const HOURS = ['12am', '1am', '2am', '3am', '4am', '5am', '6am', '7am', '8am', '9am', '10am', '11am', '12pm', '1pm', '2pm', '3pm', '4pm', '5pm', '6pm', '7pm', '8pm', '9pm', '10pm', '11pm'];

export default function HomePage() {
  const { data: overview, isLoading } = useData<OverviewData>("overview.json");
  const { data: artists } = useData<TopArtist[]>("artists/index.json");
  const { data: timeline } = useData<TimelineMonth[]>("timeline.json");
  const { data: temporal } = useData<TemporalData>("temporal.json");
  const { data: discoveries } = useData<DiscoveriesData>("discoveries-detailed.json");

  const years = useMemo(() => {
    if (!overview) return 0;
    return new Date(overview.lastPlay).getFullYear() - new Date(overview.firstPlay).getFullYear();
  }, [overview]);

  // Peak month ever (for timeline visualization scaling)
  const peakMonth = useMemo(() => {
    if (!timeline) return null;
    return timeline.reduce((max, m) => m.plays > max.plays ? m : max, timeline[0]);
  }, [timeline]);

  // Find the busiest year
  const busiestYear = useMemo(() => {
    if (!timeline) return null;
    const yearTotals: Record<number, number> = {};
    timeline.forEach(m => {
      const year = parseInt(m.yearMonth.split('-')[0]);
      yearTotals[year] = (yearTotals[year] || 0) + m.plays;
    });
    const sorted = Object.entries(yearTotals).sort((a, b) => b[1] - a[1]);
    return sorted[0] ? { year: parseInt(sorted[0][0]), plays: sorted[0][1] } : null;
  }, [timeline]);

  if (isLoading || !overview) {
    return (
      <div className="min-h-screen bg-base flex items-center justify-center">
        <motion.div 
          className="text-text-muted"
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          Loading your music journey...
        </motion.div>
      </div>
    );
  }

  const topFive = artists?.slice(0, 5) || [];
  const firstYear = new Date(overview.firstPlay).getFullYear();
  const lastYear = new Date(overview.lastPlay).getFullYear();
  const dateRange = `${new Date(overview.firstPlay).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} – ${new Date(overview.lastPlay).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}`;

  return (
    <div className="min-h-screen bg-base overflow-hidden">
      {/* Subtle Ambient Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-[150px]" />
        <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-cyan-600/10 rounded-full blur-[150px]" />
      </div>

      {/* Main Content */}
      <main className="relative z-10 max-w-6xl mx-auto px-6 py-8 md:py-12">
        
        {/* Hero - Time Capsule Opening */}
        <section className="mb-12">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="text-center mb-10">
              <motion.p 
                className="text-text-muted text-sm mb-4 tracking-wider uppercase"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                {dateRange}
              </motion.p>
              <motion.h1 
                className="font-display text-6xl md:text-8xl text-text-primary leading-none mb-4"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.3, type: "spring" }}
              >
                {formatNumber(overview.totalPlays)}
              </motion.h1>
              <motion.p 
                className="text-text-secondary text-xl"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
              >
                songs across {years} years of listening
              </motion.p>
            </div>

            {/* The Journey Stats */}
            <motion.div 
              className="flex flex-wrap justify-center gap-8 md:gap-12 mb-10"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
            >
              <div className="text-center">
                <p className="text-3xl font-display text-text-primary">{formatNumber(Math.round(overview.totalDurationHours))}</p>
                <p className="text-text-muted text-sm">hours listened</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-display text-text-primary">{Math.round(overview.totalDurationHours / 24)}</p>
                <p className="text-text-muted text-sm">days of music</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-display text-text-primary">{formatNumber(overview.totalArtists)}</p>
                <p className="text-text-muted text-sm">artists explored</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-display text-text-primary">{formatNumber(discoveries?.totalDiscoveries || 0)}</p>
                <p className="text-text-muted text-sm">new discoveries</p>
              </div>
            </motion.div>

            {/* Full Timeline Sparkline */}
            <Link href="/timeline" className="block group">
              <div className="flex items-end gap-[2px] h-16 mb-2">
                {timeline?.map((month, i) => (
                  <motion.div
                    key={month.yearMonth}
                    className="flex-1 rounded-sm bg-gradient-to-t from-accent/50 to-accent/20 group-hover:from-accent/70 group-hover:to-accent/40 transition-colors"
                    initial={{ height: 0 }}
                    animate={{ height: `${(month.plays / (peakMonth?.plays || 1)) * 100}%` }}
                    transition={{ delay: i * 0.002, duration: 0.3 }}
                    style={{ minHeight: "2px" }}
                  />
                ))}
              </div>
              <div className="flex justify-between text-xs text-text-muted">
                <span>{firstYear}</span>
                <span className="group-hover:text-text-secondary transition-colors">Click to explore your timeline →</span>
                <span>{lastYear}</span>
              </div>
            </Link>
          </motion.div>
        </section>

        {/* Personality & Milestones */}
        <section className="mb-12">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Busiest Year */}
            {busiestYear && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="p-5 rounded-2xl bg-gradient-to-br from-accent/10 to-cyan-500/5 border border-accent/20"
              >
                <div className="flex items-center gap-2 text-accent text-sm font-medium mb-3">
                  <Zap className="w-4 h-4" />
                  <span>Peak Year</span>
                </div>
                <p className="text-3xl font-display text-text-primary">{busiestYear.year}</p>
                <p className="text-text-muted text-sm">{formatNumber(busiestYear.plays)} plays</p>
              </motion.div>
            )}

            {/* Listening Personality */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="p-5 rounded-2xl bg-surface border border-border-subtle"
            >
              <div className="flex items-center gap-2 text-amber-400 text-sm font-medium mb-3">
                {temporal?.insights.peakHour && temporal.insights.peakHour >= 18 ? (
                  <Moon className="w-4 h-4" />
                ) : (
                  <Sun className="w-4 h-4" />
                )}
                <span>Prime Time</span>
              </div>
              <p className="text-2xl font-display text-text-primary">{HOURS[temporal?.insights.peakHour || 0]}</p>
              <p className="text-text-muted text-sm">{DAYS[temporal?.insights.peakDay || 0]}s</p>
            </motion.div>

            {/* Night Owl Score */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="p-5 rounded-2xl bg-surface border border-border-subtle"
            >
              <div className="flex items-center gap-2 text-violet-400 text-sm font-medium mb-3">
                <Moon className="w-4 h-4" />
                <span>Night Owl</span>
              </div>
              <p className="text-2xl font-display text-text-primary">{Math.round((temporal?.insights.nightOwlScore || 0) * 100)}%</p>
              <p className="text-text-muted text-sm">late-night listening</p>
            </motion.div>

            {/* Discovery Rate */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="p-5 rounded-2xl bg-surface border border-border-subtle"
            >
              <div className="flex items-center gap-2 text-pink-400 text-sm font-medium mb-3">
                <Sparkles className="w-4 h-4" />
                <span>Explorer</span>
              </div>
              <p className="text-2xl font-display text-text-primary">{Math.round((discoveries?.totalDiscoveries || 0) / years)}</p>
              <p className="text-text-muted text-sm">new artists / year</p>
            </motion.div>
          </div>
        </section>

        {/* Two Column: Top Artist + Records */}
        <section className="mb-12">
          <div className="grid lg:grid-cols-3 gap-6">
            {/* #1 Artist - Featured */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="lg:col-span-1"
            >
              <Link href={`/artists/${overview.topArtist.id}`} className="block group">
                <div className="relative h-full min-h-[280px] rounded-2xl bg-gradient-to-br from-violet-600/20 to-pink-600/10 border border-violet-500/20 group-hover:border-violet-400/40 transition-all overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                  <div className="absolute top-4 left-4">
                    <span className="px-3 py-1 rounded-full bg-violet-500/30 text-violet-200 text-xs font-medium backdrop-blur-sm">
                      #1 All-Time
                    </span>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 p-5">
                    <h3 className="text-2xl font-display text-white mb-1 group-hover:text-violet-200 transition-colors">{overview.topArtist.name}</h3>
                    <p className="text-text-secondary">{formatNumber(overview.topArtist.plays)} plays</p>
                  </div>
                </div>
              </Link>
            </motion.div>

            {/* Top 2-5 + Records */}
            <div className="lg:col-span-2 space-y-4">
              {/* Top 2-5 Row */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="grid grid-cols-2 md:grid-cols-4 gap-3"
              >
                {topFive.slice(1, 5).map((artist, i) => (
                  <Link key={artist.id} href={`/artists/${artist.id}`} className="group">
                    <div className="p-4 rounded-xl bg-surface border border-border-subtle group-hover:border-white/20 group-hover:bg-surface-hover transition-all">
                      <span className="text-xs text-text-muted">#{i + 2}</span>
                      <h4 className="font-medium text-text-primary truncate group-hover:text-white transition-colors">{artist.name}</h4>
                      <p className="text-xs text-text-muted">{formatNumber(artist.plays)}</p>
                    </div>
                  </Link>
                ))}
              </motion.div>

              {/* Records Row */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="grid md:grid-cols-2 gap-3"
              >
                {/* Top Track */}
                <div className="p-4 rounded-xl bg-gradient-to-br from-pink-600/10 to-orange-600/5 border border-pink-500/20">
                  <p className="text-pink-300/80 text-xs font-medium mb-2">Most Played Track</p>
                  <h4 className="font-medium text-text-primary truncate">{overview.topTrack.title}</h4>
                  <p className="text-sm text-text-muted">{overview.topTrack.artistName} · {formatNumber(overview.topTrack.plays)} plays</p>
                </div>

                {/* Top Album */}
                <Link href={`/albums/${overview.topAlbum.id}`} className="group">
                  <div className="p-4 rounded-xl bg-gradient-to-br from-cyan-600/10 to-violet-600/5 border border-cyan-500/20 group-hover:border-cyan-400/40 transition-all">
                    <p className="text-cyan-300/80 text-xs font-medium mb-2">Most Played Album</p>
                    <h4 className="font-medium text-text-primary truncate group-hover:text-white transition-colors">{overview.topAlbum.title}</h4>
                    <p className="text-sm text-text-muted">{overview.topAlbum.artistName} · {formatNumber(overview.topAlbum.plays)} plays</p>
                  </div>
                </Link>
              </motion.div>
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-4 text-center"
          >
            <Link 
              href="/artists" 
              className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary transition-colors group"
            >
              <span>See all {formatNumber(overview.totalArtists)} artists</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </motion.div>
        </section>

        {/* Dive Into Your History */}
        <section className="pb-20">
          <motion.h2 
            className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
          >
            Explore Your History
          </motion.h2>
          
          <motion.div
            className="grid md:grid-cols-4 gap-4"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
          >
            <Link href="/timeline" className="group">
              <div className="relative h-32 rounded-xl overflow-hidden border border-white/5 group-hover:border-emerald-500/30 transition-all">
                <div className="absolute inset-0 bg-gradient-to-br from-emerald-600/20 to-cyan-600/10" />
                <div className="absolute inset-0 flex flex-col justify-end p-4">
                  <Calendar className="w-5 h-5 text-emerald-400 mb-2" />
                  <h3 className="font-medium text-white">Timeline</h3>
                  <p className="text-text-muted text-xs">{years} years, month by month</p>
                </div>
              </div>
            </Link>

            <Link href="/discoveries" className="group">
              <div className="relative h-32 rounded-xl overflow-hidden border border-white/5 group-hover:border-amber-500/30 transition-all">
                <div className="absolute inset-0 bg-gradient-to-br from-amber-600/20 to-pink-600/10" />
                <div className="absolute inset-0 flex flex-col justify-end p-4">
                  <Sparkles className="w-5 h-5 text-amber-400 mb-2" />
                  <h3 className="font-medium text-white">Discoveries</h3>
                  <p className="text-text-muted text-xs">{formatNumber(discoveries?.totalDiscoveries || 0)} artists found</p>
                </div>
              </div>
            </Link>

            <Link href="/patterns" className="group">
              <div className="relative h-32 rounded-xl overflow-hidden border border-white/5 group-hover:border-violet-500/30 transition-all">
                <div className="absolute inset-0 bg-gradient-to-br from-violet-600/20 to-indigo-600/10" />
                <div className="absolute inset-0 flex flex-col justify-end p-4">
                  <TrendingUp className="w-5 h-5 text-violet-400 mb-2" />
                  <h3 className="font-medium text-white">Patterns</h3>
                  <p className="text-text-muted text-xs">Your listening habits</p>
                </div>
              </div>
            </Link>

            <Link href="/story" className="group">
              <div className="relative h-32 rounded-xl overflow-hidden border border-white/5 group-hover:border-pink-500/30 transition-all">
                <div className="absolute inset-0 bg-gradient-to-br from-pink-600/20 to-orange-600/10" />
                <div className="absolute inset-0 flex flex-col justify-end p-4">
                  <Play className="w-5 h-5 text-pink-400 mb-2" />
                  <h3 className="font-medium text-white">Year Stories</h3>
                  <p className="text-text-muted text-xs">Relive each year</p>
                </div>
              </div>
            </Link>
          </motion.div>
        </section>
      </main>
    </div>
  );
}
