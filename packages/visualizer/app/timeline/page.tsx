"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Play, Users, Sparkles, ChevronLeft, ChevronRight, X, Star, Music, ArrowUpRight, Clock, Calendar, TrendingUp, Disc3, ArrowLeft } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { useData } from "@/lib/hooks";
import { formatNumber, formatDate } from "@/lib/format";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

interface TimelineMonth {
  yearMonth: string;
  plays: number;
  durationHours: number;
  uniqueArtists: number;
  uniqueAlbums: number;
  uniqueTracks: number;
  newDiscoveries: number;
  topArtist: { id: number; name: string; plays: number };
  topArtists: { id: number; name: string; plays: number; durationMs: number }[];
  fragmentationScore: number;
}

interface ArtistDiscovery {
  id: number;
  name: string;
  firstPlayed: string;
  plays: number;
}

interface YearlyDiscovery {
  year: number;
  count: number;
  topArtists: ArtistDiscovery[];
  allArtists: ArtistDiscovery[];
}

interface MonthlyDiscovery {
  yearMonth: string;
  count: number;
  artists: ArtistDiscovery[];
}

interface DiscoveriesData {
  yearlyTimeline: YearlyDiscovery[];
  monthlyTimeline: MonthlyDiscovery[];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FULL_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// Custom tooltip for the all-time timeline chart
const AllTimeTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const [year, month] = label.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    const monthName = date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    return (
      <div className="bg-surface-elevated border border-border-subtle px-3 py-2 rounded-lg shadow-lg">
        <p className="text-sm font-medium text-text-primary">{monthName}</p>
        <p className="text-lg font-display text-accent">
          {formatNumber(payload[0].value)} plays
        </p>
      </div>
    );
  }
  return null;
};

// Custom tooltip for the year timeline chart
const YearTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-surface-elevated border border-border-subtle px-3 py-2 rounded-lg shadow-lg">
        <p className="text-sm font-medium text-text-primary">{label}</p>
        <p className="text-lg font-display text-accent">
          {formatNumber(payload[0].value)} plays
        </p>
      </div>
    );
  }
  return null;
};

// Custom tooltip for yearly overview chart
const YearlyOverviewTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-surface-elevated border border-border-subtle px-3 py-2 rounded-lg shadow-lg">
        <p className="text-sm font-medium text-text-primary">{label}</p>
        <p className="text-lg font-display text-accent">
          {formatNumber(payload[0].value)} plays
        </p>
      </div>
    );
  }
  return null;
};

type DetailPanel = 'plays' | 'hours' | 'artists' | 'tracks' | 'discoveries' | null;

export default function TimelinePage() {
  const { data: timeline, isLoading } = useData<TimelineMonth[]>("timeline.json");
  const { data: discoveriesData } = useData<DiscoveriesData>("discoveries-detailed.json");
  const [selectedYear, setSelectedYear] = useState<number | null>(null); // null = all years overview
  const [showDiscoveriesModal, setShowDiscoveriesModal] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState<TimelineMonth | null>(null);
  const [discoveriesYear, setDiscoveriesYear] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<DetailPanel>(null);

  // Group data by year
  const { groupedByYear, years } = useMemo(() => {
    if (!timeline) return { groupedByYear: {}, years: [] };
    
    const grouped: Record<number, TimelineMonth[]> = {};
    
    timeline.forEach((month) => {
      const year = parseInt(month.yearMonth.split("-")[0]);
      if (!grouped[year]) grouped[year] = [];
      grouped[year].push(month);
    });
    
    const sortedYears = Object.keys(grouped).map(Number).sort((a, b) => b - a);
    
    return { groupedByYear: grouped, years: sortedYears };
  }, [timeline]);

  // Yearly summaries for the overview
  const yearlySummaries = useMemo(() => {
    return years.map(year => {
      const months = groupedByYear[year] || [];
      const totalPlays = months.reduce((sum, m) => sum + m.plays, 0);
      const totalHours = months.reduce((sum, m) => sum + m.durationHours, 0);
      const discoveries = months.reduce((sum, m) => sum + m.newDiscoveries, 0);
      const uniqueArtists = Math.max(...months.map(m => m.uniqueArtists), 0);
      
      // Find top artist of the year
      const artistPlays: Record<string, { id: number; name: string; plays: number }> = {};
      months.forEach(m => {
        if (m.topArtist) {
          const key = m.topArtist.id.toString();
          if (!artistPlays[key]) {
            artistPlays[key] = { ...m.topArtist, plays: 0 };
          }
          artistPlays[key].plays += m.topArtist.plays;
        }
      });
      const topArtist = Object.values(artistPlays).sort((a, b) => b.plays - a.plays)[0] || null;
      
      return { year, totalPlays, totalHours, discoveries, uniqueArtists, topArtist };
    });
  }, [years, groupedByYear]);

  // Current year's data (when drilled in)
  const currentYearData = useMemo(() => {
    if (selectedYear === null) return null;
    const months = groupedByYear[selectedYear] || [];
    const totalPlays = months.reduce((sum, m) => sum + m.plays, 0);
    const totalHours = months.reduce((sum, m) => sum + m.durationHours, 0);
    const discoveries = months.reduce((sum, m) => sum + m.newDiscoveries, 0);
    
    // Fill in all 12 months
    const fullYear = MONTHS.map((_, i) => {
      const monthNum = String(i + 1).padStart(2, "0");
      const yearMonth = `${selectedYear}-${monthNum}`;
      return months.find(m => m.yearMonth === yearMonth) || null;
    });
    
    return { months: fullYear, totalPlays, totalHours, discoveries };
  }, [groupedByYear, selectedYear]);

  // Chart data for the full timeline (all-time view)
  const allTimeChartData = useMemo(() => {
    if (!timeline) return [];
    return timeline.map(m => ({
      yearMonth: m.yearMonth,
      plays: m.plays,
    })).sort((a, b) => a.yearMonth.localeCompare(b.yearMonth));
  }, [timeline]);

  // Chart data for yearly overview (aggregated by year)
  const yearlyChartData = useMemo(() => {
    return yearlySummaries
      .map(y => ({ year: y.year.toString(), plays: y.totalPlays }))
      .sort((a, b) => a.year.localeCompare(b.year));
  }, [yearlySummaries]);

  // Chart data for the selected year (monthly breakdown)
  const selectedYearChartData = useMemo(() => {
    if (selectedYear === null) return [];
    const months = groupedByYear[selectedYear] || [];
    return MONTHS.map((monthName, i) => {
      const monthNum = String(i + 1).padStart(2, "0");
      const yearMonth = `${selectedYear}-${monthNum}`;
      const monthData = months.find(m => m.yearMonth === yearMonth);
      return {
        month: monthName,
        plays: monthData?.plays || 0,
      };
    });
  }, [selectedYear, groupedByYear]);

  // Find peak month for all-time
  const peakMonth = useMemo(() => {
    if (!allTimeChartData.length) return null;
    return allTimeChartData.reduce((max, d) => d.plays > max.plays ? d : max, allTimeChartData[0]);
  }, [allTimeChartData]);

  // Find peak year
  const peakYear = useMemo(() => {
    if (!yearlySummaries.length) return null;
    return yearlySummaries.reduce((max, y) => y.totalPlays > max.totalPlays ? y : max, yearlySummaries[0]);
  }, [yearlySummaries]);

  // Find peak month for selected year
  const selectedYearPeakMonth = useMemo(() => {
    if (!selectedYearChartData.length) return null;
    const peak = selectedYearChartData.reduce((max, d) => d.plays > max.plays ? d : max, selectedYearChartData[0]);
    return peak.plays > 0 ? peak : null;
  }, [selectedYearChartData]);

  // Keyboard navigation (only in year view)
  const currentYearIndex = selectedYear !== null ? years.indexOf(selectedYear) : -1;
  const canGoPrev = selectedYear !== null && currentYearIndex < years.length - 1;
  const canGoNext = selectedYear !== null && currentYearIndex > 0;
  const prevYear = canGoPrev ? years[currentYearIndex + 1] : null;
  const nextYear = canGoNext ? years[currentYearIndex - 1] : null;

  const goToPrevYear = useCallback(() => {
    if (canGoPrev) setSelectedYear(years[currentYearIndex + 1]);
  }, [canGoPrev, years, currentYearIndex]);

  const goToNextYear = useCallback(() => {
    if (canGoNext) setSelectedYear(years[currentYearIndex - 1]);
  }, [canGoNext, years, currentYearIndex]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't handle if modal is open or if user is typing
      if (showDiscoveriesModal || selectedMonth) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      
      if (selectedYear !== null) {
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          goToPrevYear();
        } else if (e.key === 'ArrowRight') {
          e.preventDefault();
          goToNextYear();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          setSelectedYear(null);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goToPrevYear, goToNextYear, showDiscoveriesModal, selectedMonth, selectedYear]);

  // Get discoveries for the selected year (for modal)
  const selectedYearDiscoveries = useMemo(() => {
    if (!discoveriesData || discoveriesYear === null) return null;
    return discoveriesData.yearlyTimeline.find(y => y.year === discoveriesYear);
  }, [discoveriesData, discoveriesYear]);

  // Get discoveries for the selected month
  const selectedMonthDiscoveries = useMemo(() => {
    if (!discoveriesData || !selectedMonth) return null;
    return discoveriesData.monthlyTimeline?.find(m => m.yearMonth === selectedMonth.yearMonth);
  }, [discoveriesData, selectedMonth]);

  if (isLoading || !timeline) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading timeline...</div>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      {/* Header */}
      <div className="mb-8">
        {selectedYear !== null && (
          <button
            onClick={() => setSelectedYear(null)}
            className="inline-flex items-center gap-2 text-text-secondary hover:text-text-primary mb-4 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>All Years</span>
          </button>
        )}
        <h1 className="text-display-lg text-text-primary mb-2">
          {selectedYear !== null ? `${selectedYear}` : "Timeline"}
        </h1>
        <p className="text-text-secondary">
          {selectedYear !== null 
            ? `Your listening journey through ${selectedYear}`
            : "Your complete listening history"
          }
        </p>
      </div>

      <AnimatePresence mode="wait">
        {/* ALL YEARS OVERVIEW */}
        {selectedYear === null ? (
          <motion.div
            key="overview"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {/* Big Sexy All-Time Timeline Graph */}
            {allTimeChartData.length > 0 && (
              <div className="mb-10">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider">All-Time Listening</h2>
                  {peakMonth && (
                    <div className="text-xs text-text-muted">
                      Peak: <span className="text-accent font-medium">
                        {(() => {
                          const [y, m] = peakMonth.yearMonth.split('-');
                          return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                        })()}
                      </span> ({formatNumber(peakMonth.plays)} plays)
                    </div>
                  )}
                </div>
                <div className="h-48 bg-surface rounded-xl p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={allTimeChartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="alltime-gradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.5} />
                          <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis 
                        dataKey="yearMonth" 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#888', fontSize: 11 }}
                        tickFormatter={(value) => {
                          const [year, month] = value.split('-');
                          if (month === '01') return year;
                          return '';
                        }}
                        interval={11}
                      />
                      <YAxis 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#888', fontSize: 11 }}
                        tickFormatter={(value) => formatNumber(value)}
                        width={45}
                      />
                      <Tooltip content={<AllTimeTooltip />} />
                      <Area
                        type="monotone"
                        dataKey="plays"
                        stroke="#8b5cf6"
                        strokeWidth={2}
                        fill="url(#alltime-gradient)"
                        dot={false}
                        activeDot={{ fill: '#8b5cf6', stroke: '#18181b', strokeWidth: 2, r: 5 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* All-Time Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              <div className="bg-surface rounded-xl p-5 text-center">
                <Play className="h-5 w-5 text-accent mx-auto mb-2" />
                <p className="text-3xl font-display text-text-primary">
                  {formatNumber(yearlySummaries.reduce((sum, y) => sum + y.totalPlays, 0))}
                </p>
                <p className="text-sm text-text-muted">Total Plays</p>
              </div>
              <div className="bg-surface rounded-xl p-5 text-center">
                <Clock className="h-5 w-5 text-blue-400 mx-auto mb-2" />
                <p className="text-3xl font-display text-text-primary">
                  {formatNumber(Math.round(yearlySummaries.reduce((sum, y) => sum + y.totalHours, 0)))}
                </p>
                <p className="text-sm text-text-muted">Total Hours</p>
              </div>
              <div className="bg-surface rounded-xl p-5 text-center">
                <Sparkles className="h-5 w-5 text-pink-400 mx-auto mb-2" />
                <p className="text-3xl font-display text-text-primary">
                  {formatNumber(yearlySummaries.reduce((sum, y) => sum + y.discoveries, 0))}
                </p>
                <p className="text-sm text-text-muted">Artists Discovered</p>
              </div>
              <div className="bg-surface rounded-xl p-5 text-center">
                <Calendar className="h-5 w-5 text-amber-400 mx-auto mb-2" />
                <p className="text-3xl font-display text-text-primary">
                  {years.length}
                </p>
                <p className="text-sm text-text-muted">Years of Data</p>
              </div>
            </div>

            {/* Year Cards Grid */}
            <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">By Year</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {yearlySummaries.map((summary, i) => (
                <motion.div
                  key={summary.year}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  onClick={() => setSelectedYear(summary.year)}
                  className="bg-surface rounded-xl p-5 cursor-pointer hover:bg-surface-hover hover:ring-2 hover:ring-accent/30 transition-all group"
                >
                  <div className="flex items-start justify-between mb-4">
                    <h3 className="text-2xl font-display text-text-primary group-hover:text-accent transition-colors">
                      {summary.year}
                    </h3>
                    {peakYear?.year === summary.year && (
                      <span className="text-xs bg-accent/20 text-accent px-2 py-1 rounded-full">Peak Year</span>
                    )}
                  </div>
                  
                  <div className="flex items-baseline gap-2 mb-4">
                    <span className="text-3xl font-display text-text-primary">
                      {formatNumber(summary.totalPlays)}
                    </span>
                    <span className="text-sm text-text-muted">plays</span>
                  </div>
                  
                  {summary.topArtist && (
                    <div className="mb-3">
                      <p className="text-xs text-text-muted mb-1">Top Artist</p>
                      <p className="text-sm text-text-primary truncate">{summary.topArtist.name}</p>
                    </div>
                  )}
                  
                  <div className="flex items-center gap-4 pt-3 border-t border-border-subtle text-xs text-text-muted">
                    <span>{formatNumber(Math.round(summary.totalHours))}h</span>
                    <span>{summary.discoveries} discoveries</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        ) : (
          /* YEAR DETAIL VIEW */
          <motion.div
            key={selectedYear}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {/* Year Timeline Graph */}
            {selectedYearChartData.length > 0 && (
              <div className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider">{selectedYear} Monthly Listening</h2>
                  {selectedYearPeakMonth && (
                    <div className="text-xs text-text-muted">
                      Peak: <span className="text-accent font-medium">{selectedYearPeakMonth.month}</span> ({formatNumber(selectedYearPeakMonth.plays)} plays)
                    </div>
                  )}
                </div>
                <div className="h-48 bg-surface rounded-xl p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={selectedYearChartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="year-gradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.5} />
                          <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis 
                        dataKey="month" 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#888', fontSize: 11 }}
                      />
                      <YAxis 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#888', fontSize: 11 }}
                        tickFormatter={(value) => formatNumber(value)}
                        width={45}
                      />
                      <Tooltip content={<YearTooltip />} />
                      <Area
                        type="monotone"
                        dataKey="plays"
                        stroke="#8b5cf6"
                        strokeWidth={2}
                        fill="url(#year-gradient)"
                        dot={{ fill: '#8b5cf6', strokeWidth: 0, r: 4 }}
                        activeDot={{ fill: '#8b5cf6', stroke: '#18181b', strokeWidth: 2, r: 6 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Stats Bar */}
            {currentYearData && (
              <div className="grid grid-cols-3 gap-4 mb-8">
                <div className="bg-surface rounded-xl p-4 text-center">
                  <div className="flex items-center justify-center gap-2 text-text-muted mb-1">
                    <Play className="h-4 w-4" />
                    <span className="text-sm">Plays</span>
                  </div>
                  <p className="text-2xl font-display text-text-primary">
                    {formatNumber(currentYearData.totalPlays)}
                  </p>
                </div>
                <div className="bg-surface rounded-xl p-4 text-center">
                  <div className="flex items-center justify-center gap-2 text-text-muted mb-1">
                    <Clock className="h-4 w-4" />
                    <span className="text-sm">Hours</span>
                  </div>
                  <p className="text-2xl font-display text-text-primary">
                    {currentYearData.totalHours > 0 ? formatNumber(Math.round(currentYearData.totalHours)) : "—"}
                  </p>
                </div>
                <button
                  onClick={() => {
                    if (currentYearData.discoveries > 0) {
                      setDiscoveriesYear(selectedYear);
                      setShowDiscoveriesModal(true);
                    }
                  }}
                  className={`bg-surface rounded-xl p-4 text-center w-full transition-all ${
                    currentYearData.discoveries > 0 
                      ? "hover:bg-surface-hover hover:ring-2 hover:ring-accent/50 cursor-pointer" 
                      : "cursor-default"
                  }`}
                >
                  <div className="flex items-center justify-center gap-2 text-text-muted mb-1">
                    <Sparkles className="h-4 w-4" />
                    <span className="text-sm">Discoveries</span>
                  </div>
                  <p className="text-2xl font-display text-text-primary">
                    {currentYearData.discoveries}
                  </p>
                  {currentYearData.discoveries > 0 && (
                    <p className="text-xs text-accent mt-1">Click to view</p>
                  )}
                </button>
              </div>
            )}

            {/* Monthly Grid */}
            {currentYearData && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {currentYearData.months.map((month, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                onClick={() => month && setSelectedMonth(month)}
                className={`bg-surface rounded-xl p-5 transition-all ${!month ? "opacity-40" : "cursor-pointer hover:bg-surface-hover hover:ring-2 hover:ring-accent/30"}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-lg font-medium text-text-primary">{MONTHS[i]}</h3>
                  {month && month.newDiscoveries > 0 && (
                    <span className="text-xs bg-pink-500/20 text-pink-400 px-2 py-1 rounded-full">
                      +{month.newDiscoveries} new
                    </span>
                  )}
                </div>
                
                {month ? (
                  <>
                    {/* Play count */}
                    <div className="flex items-baseline gap-2 mb-4">
                      <span className="text-3xl font-display text-text-primary">
                        {formatNumber(month.plays)}
                      </span>
                      <span className="text-sm text-text-muted">plays</span>
                    </div>
                    
                    {/* Top Artist */}
                    {month.topArtist && (
                      <Link 
                        href={`/artists/${month.topArtist.id}`}
                        className="flex items-center justify-between p-3 -mx-2 rounded-lg hover:bg-surface-hover transition-colors group"
                      >
                        <div>
                          <p className="text-xs text-text-muted mb-1">Top Artist</p>
                          <p className="text-sm text-text-primary group-hover:text-accent transition-colors">
                            {month.topArtist.name}
                          </p>
                        </div>
                        <span className="text-sm text-text-muted">
                          {formatNumber(month.topArtist.plays)} plays
                        </span>
                      </Link>
                    )}
                    
                    {/* Quick stats */}
                    <div className="flex items-center gap-4 mt-3 pt-3 border-t border-border-subtle text-xs text-text-muted">
                      <span>{month.uniqueArtists} artists</span>
                      <span>{month.uniqueTracks} tracks</span>
                      {month.durationHours > 0 && (
                        <span>{Math.round(month.durationHours)}h</span>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-text-muted">No listening data</p>
                )}
                </motion.div>
              ))}
              </div>
            )}

            {/* Year Navigation */}
            <div className="flex items-center justify-center gap-4 mt-12">
              <button
                onClick={goToPrevYear}
                disabled={!canGoPrev}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
                <span>{prevYear ?? ''}</span>
              </button>
              <span className="text-text-muted text-sm">← → to navigate</span>
              <button
                onClick={goToNextYear}
                disabled={!canGoNext}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <span>{nextYear ?? ''}</span>
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Month Detail Modal */}
      <AnimatePresence>
        {selectedMonth && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
          >
            <motion.div
              className="bg-surface-elevated border border-border-subtle rounded-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden shadow-2xl"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="p-6 border-b border-border-subtle bg-gradient-to-r from-teal-500/10 via-cyan-500/10 to-blue-500/10">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-display-md text-text-primary font-display">
                      {(() => {
                        const [year, month] = selectedMonth.yearMonth.split('-');
                        return `${FULL_MONTHS[parseInt(month) - 1]} ${year}`;
                      })()}
                    </h2>
                    <p className="text-text-secondary">
                      {formatNumber(selectedMonth.plays)} plays · {Math.round(selectedMonth.durationHours)} hours · {selectedMonth.uniqueArtists} artists
                    </p>
                  </div>
                  <button
                    onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
                    className="p-2 rounded-full hover:bg-white/10 transition-colors"
                  >
                    <X className="h-6 w-6 text-text-muted" />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="p-6 overflow-y-auto max-h-[calc(85vh-100px)]">
                {/* Key Stats Row - Clickable */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
                  <button
                    onClick={() => setExpandedDetail(expandedDetail === 'plays' ? null : 'plays')}
                    className={`bg-surface rounded-xl p-4 text-center transition-all hover:bg-surface-hover ${expandedDetail === 'plays' ? 'ring-2 ring-accent' : ''}`}
                  >
                    <Play className="h-4 w-4 text-accent mx-auto mb-1" />
                    <p className="text-xl font-display text-text-primary">{formatNumber(selectedMonth.plays)}</p>
                    <p className="text-xs text-text-muted">Plays</p>
                  </button>
                  <button
                    onClick={() => setExpandedDetail(expandedDetail === 'hours' ? null : 'hours')}
                    className={`bg-surface rounded-xl p-4 text-center transition-all hover:bg-surface-hover ${expandedDetail === 'hours' ? 'ring-2 ring-blue-400' : ''}`}
                  >
                    <Clock className="h-4 w-4 text-blue-400 mx-auto mb-1" />
                    <p className="text-xl font-display text-text-primary">{Math.round(selectedMonth.durationHours)}</p>
                    <p className="text-xs text-text-muted">Hours</p>
                  </button>
                  <button
                    onClick={() => setExpandedDetail(expandedDetail === 'artists' ? null : 'artists')}
                    className={`bg-surface rounded-xl p-4 text-center transition-all hover:bg-surface-hover ${expandedDetail === 'artists' ? 'ring-2 ring-purple-400' : ''}`}
                  >
                    <Users className="h-4 w-4 text-purple-400 mx-auto mb-1" />
                    <p className="text-xl font-display text-text-primary">{selectedMonth.uniqueArtists}</p>
                    <p className="text-xs text-text-muted">Artists</p>
                  </button>
                  <button
                    onClick={() => setExpandedDetail(expandedDetail === 'tracks' ? null : 'tracks')}
                    className={`bg-surface rounded-xl p-4 text-center transition-all hover:bg-surface-hover ${expandedDetail === 'tracks' ? 'ring-2 ring-pink-400' : ''}`}
                  >
                    <Disc3 className="h-4 w-4 text-pink-400 mx-auto mb-1" />
                    <p className="text-xl font-display text-text-primary">{selectedMonth.uniqueTracks}</p>
                    <p className="text-xs text-text-muted">Tracks</p>
                  </button>
                  <button
                    onClick={() => setExpandedDetail(expandedDetail === 'discoveries' ? null : 'discoveries')}
                    className={`bg-surface rounded-xl p-4 text-center transition-all hover:bg-surface-hover ${expandedDetail === 'discoveries' ? 'ring-2 ring-amber-400' : ''}`}
                  >
                    <Sparkles className="h-4 w-4 text-amber-400 mx-auto mb-1" />
                    <p className="text-xl font-display text-text-primary">{selectedMonth.newDiscoveries}</p>
                    <p className="text-xs text-text-muted">Discoveries</p>
                  </button>
                </div>

                {/* Expanded Detail Panel */}
                <AnimatePresence mode="wait">
                  {expandedDetail && (
                    <motion.div
                      key={expandedDetail}
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="mb-6 overflow-hidden"
                    >
                      <div className="bg-surface rounded-xl p-4">
                        {expandedDetail === 'plays' && (
                          <div>
                            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                              <Play className="h-4 w-4 text-accent" />
                              Play Statistics
                            </h4>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Total Plays</p>
                                <p className="text-lg font-display text-text-primary">{formatNumber(selectedMonth.plays)}</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Per Day</p>
                                <p className="text-lg font-display text-text-primary">{Math.round(selectedMonth.plays / 30)}</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Per Hour Listened</p>
                                <p className="text-lg font-display text-text-primary">
                                  {selectedMonth.durationHours > 0 ? Math.round(selectedMonth.plays / selectedMonth.durationHours) : 0}
                                </p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Unique Ratio</p>
                                <p className="text-lg font-display text-text-primary">
                                  {Math.round((selectedMonth.uniqueTracks / selectedMonth.plays) * 100)}%
                                </p>
                              </div>
                            </div>
                          </div>
                        )}

                        {expandedDetail === 'hours' && (
                          <div>
                            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                              <Clock className="h-4 w-4 text-blue-400" />
                              Listening Time
                            </h4>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Total Hours</p>
                                <p className="text-lg font-display text-text-primary">{Math.round(selectedMonth.durationHours)}</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Per Day</p>
                                <p className="text-lg font-display text-text-primary">{(selectedMonth.durationHours / 30).toFixed(1)}h</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Total Minutes</p>
                                <p className="text-lg font-display text-text-primary">{formatNumber(Math.round(selectedMonth.durationHours * 60))}</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Avg Track</p>
                                <p className="text-lg font-display text-text-primary">
                                  {selectedMonth.plays > 0 ? `${Math.round((selectedMonth.durationHours * 60) / selectedMonth.plays)}m` : '—'}
                                </p>
                              </div>
                            </div>
                          </div>
                        )}

                        {expandedDetail === 'artists' && (
                          <div>
                            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                              <Users className="h-4 w-4 text-purple-400" />
                              All {selectedMonth.uniqueArtists} Artists
                            </h4>
                            <div className="max-h-64 overflow-y-auto">
                              {selectedMonth.topArtists && selectedMonth.topArtists.length > 0 ? (
                                <div className="space-y-1">
                                  {selectedMonth.topArtists.map((artist, i) => (
                                    <Link
                                      key={artist.id}
                                      href={`/artists/${artist.id}`}
                                      onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
                                      className="flex items-center gap-3 p-2 rounded-lg hover:bg-surface-hover transition-colors group"
                                    >
                                      <span className={`w-6 text-center text-xs font-medium ${i < 3 ? 'text-purple-400' : 'text-text-muted'}`}>
                                        {i + 1}
                                      </span>
                                      <span className="flex-1 text-sm text-text-primary truncate group-hover:text-accent transition-colors">
                                        {artist.name}
                                      </span>
                                      <span className="text-sm text-text-muted">{formatNumber(artist.plays)}</span>
                                    </Link>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-sm text-text-muted text-center py-4">Artist data will be available after re-exporting</p>
                              )}
                            </div>
                          </div>
                        )}

                        {expandedDetail === 'tracks' && (
                          <div>
                            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                              <Disc3 className="h-4 w-4 text-pink-400" />
                              Track Statistics
                            </h4>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Unique Tracks</p>
                                <p className="text-lg font-display text-text-primary">{formatNumber(selectedMonth.uniqueTracks)}</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Plays/Track</p>
                                <p className="text-lg font-display text-text-primary">
                                  {selectedMonth.uniqueTracks > 0 ? (selectedMonth.plays / selectedMonth.uniqueTracks).toFixed(1) : '—'}
                                </p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">Albums</p>
                                <p className="text-lg font-display text-text-primary">{selectedMonth.uniqueAlbums || '—'}</p>
                              </div>
                              <div className="p-3 rounded-lg bg-surface-elevated">
                                <p className="text-xs text-text-muted">New Tracks</p>
                                <p className="text-lg font-display text-text-primary">—</p>
                              </div>
                            </div>
                            <p className="text-xs text-text-muted mt-3 text-center">
                              Top tracks coming soon
                            </p>
                          </div>
                        )}

                        {expandedDetail === 'discoveries' && (
                          <div>
                            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                              <Sparkles className="h-4 w-4 text-amber-400" />
                              {selectedMonth.newDiscoveries} New Artist{selectedMonth.newDiscoveries !== 1 ? 's' : ''} Discovered
                            </h4>
                            {selectedMonthDiscoveries && selectedMonthDiscoveries.artists.length > 0 ? (
                              <div className="max-h-64 overflow-y-auto space-y-1">
                                {selectedMonthDiscoveries.artists.map((artist) => (
                                  <Link
                                    key={artist.id}
                                    href={`/artists/${artist.id}`}
                                    onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
                                    className="flex items-center justify-between p-2 rounded-lg hover:bg-surface-hover transition-colors group"
                                  >
                                    <div className="flex items-center gap-2 min-w-0">
                                      <span className="text-xs bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded font-medium">NEW</span>
                                      <span className="text-sm text-text-primary truncate group-hover:text-accent transition-colors">
                                        {artist.name}
                                      </span>
                                    </div>
                                    <div className="text-right text-xs text-text-muted">
                                      <span>{formatNumber(artist.plays)} plays since</span>
                                    </div>
                                  </Link>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-text-muted text-center py-4">
                                {selectedMonth.newDiscoveries > 0 ? 'Discovery details loading...' : 'No new artists discovered this month'}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Two Column Layout */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Left Column - Top Artists */}
                  <div>
                    <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Star className="h-4 w-4 text-amber-400" />
                      All Artists
                    </h3>
                    <div className="bg-surface rounded-xl p-2 max-h-80 overflow-y-auto">
                      {selectedMonth.topArtists && selectedMonth.topArtists.length > 0 ? (
                        <div className="space-y-1">
                          {selectedMonth.topArtists.map((artist, i) => (
                            <Link
                              key={artist.id}
                              href={`/artists/${artist.id}`}
                              onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
                              className="flex items-center gap-3 p-2 rounded-lg hover:bg-surface-hover transition-colors group"
                            >
                              <span className={`w-6 text-center text-sm font-medium ${i < 3 ? 'text-accent' : 'text-text-muted'}`}>
                                {i + 1}
                              </span>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-text-primary truncate group-hover:text-accent transition-colors">
                                  {artist.name}
                                </p>
                              </div>
                              <div className="text-right">
                                <p className="text-sm font-medium text-text-primary">{formatNumber(artist.plays)}</p>
                                <p className="text-xs text-text-muted">
                                  {Math.round((artist.plays / selectedMonth.plays) * 100)}%
                                </p>
                              </div>
                            </Link>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-text-muted text-center py-4">No artist data available</p>
                      )}
                    </div>
                  </div>

                  {/* Right Column - Discoveries + Insights */}
                  <div className="space-y-6">
                    {/* New Discoveries */}
                    {selectedMonthDiscoveries && selectedMonthDiscoveries.artists.length > 0 && (
                      <div>
                        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                          <Sparkles className="h-4 w-4 text-pink-400" />
                          Artists Discovered ({selectedMonthDiscoveries.count})
                        </h3>
                        <div className="bg-gradient-to-br from-pink-500/10 to-violet-500/10 rounded-xl p-3 border border-pink-500/20 max-h-48 overflow-y-auto">
                          <div className="space-y-1">
                            {selectedMonthDiscoveries.artists.slice(0, 10).map((artist, i) => (
                              <Link
                                key={artist.id}
                                href={`/artists/${artist.id}`}
                                onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
                                className="flex items-center justify-between p-2 rounded-lg hover:bg-white/5 transition-colors group"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="text-xs text-pink-400 font-medium">NEW</span>
                                  <span className="text-sm text-text-primary truncate group-hover:text-accent transition-colors">
                                    {artist.name}
                                  </span>
                                </div>
                                <span className="text-xs text-text-muted">{formatNumber(artist.plays)} plays since</span>
                              </Link>
                            ))}
                            {selectedMonthDiscoveries.artists.length > 10 && (
                              <p className="text-xs text-text-muted text-center pt-2">
                                +{selectedMonthDiscoveries.artists.length - 10} more discoveries
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Insights */}
                    <div>
                      <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-emerald-400" />
                        Insights
                      </h3>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 rounded-xl bg-surface">
                          <p className="text-xs text-text-muted">Daily Average</p>
                          <p className="text-lg font-display text-text-primary">
                            {Math.round(selectedMonth.plays / 30)} <span className="text-xs text-text-muted">plays</span>
                          </p>
                        </div>
                        <div className="p-3 rounded-xl bg-surface">
                          <p className="text-xs text-text-muted">Listening Time</p>
                          <p className="text-lg font-display text-text-primary">
                            {(selectedMonth.durationHours / 30).toFixed(1)} <span className="text-xs text-text-muted">hrs/day</span>
                          </p>
                        </div>
                        <div className="p-3 rounded-xl bg-surface">
                          <p className="text-xs text-text-muted">Avg Track</p>
                          <p className="text-lg font-display text-text-primary">
                            {selectedMonth.plays > 0 
                              ? `${Math.round((selectedMonth.durationHours * 60) / selectedMonth.plays)}`
                              : '—'} <span className="text-xs text-text-muted">min</span>
                          </p>
                        </div>
                        <div className="p-3 rounded-xl bg-surface">
                          <p className="text-xs text-text-muted">Variety</p>
                          <p className="text-lg font-display text-text-primary">
                            {selectedMonth.uniqueArtists > 0 
                              ? Math.round((selectedMonth.uniqueArtists / selectedMonth.plays) * 100)
                              : 0}<span className="text-xs text-text-muted">%</span>
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Top Artist Highlight */}
                    {selectedMonth.topArtist && (
                      <div>
                        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                          <Music className="h-4 w-4 text-blue-400" />
                          #1 Artist
                        </h3>
                        <Link 
                          href={`/artists/${selectedMonth.topArtist.id}`}
                          onClick={() => { setSelectedMonth(null); setExpandedDetail(null); }}
                          className="block"
                        >
                          <div className="p-4 rounded-xl bg-gradient-to-r from-accent/10 to-blue-500/10 border border-accent/20 hover:border-accent/40 transition-all group">
                            <div className="flex items-center justify-between">
                              <div>
                                <h4 className="text-lg font-medium text-text-primary group-hover:text-accent transition-colors">
                                  {selectedMonth.topArtist.name}
                                </h4>
                                <p className="text-sm text-text-muted">
                                  {formatNumber(selectedMonth.topArtist.plays)} plays · {Math.round((selectedMonth.topArtist.plays / selectedMonth.plays) * 100)}% of listening
                                </p>
                              </div>
                              <ArrowUpRight className="h-5 w-5 text-text-muted group-hover:text-accent transition-colors" />
                            </div>
                          </div>
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Discoveries Modal */}
      <AnimatePresence>
        {showDiscoveriesModal && selectedYearDiscoveries && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowDiscoveriesModal(false)}
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
                      {discoveriesYear} Discoveries
                    </h2>
                    <p className="text-text-secondary">
                      {selectedYearDiscoveries.count} new artists discovered
                    </p>
                  </div>
                  <button
                    onClick={() => setShowDiscoveriesModal(false)}
                    className="p-2 rounded-full hover:bg-white/10 transition-colors"
                  >
                    <X className="h-6 w-6 text-text-muted" />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="p-6 overflow-y-auto max-h-[calc(80vh-120px)]">
                {/* Top Discoveries */}
                {selectedYearDiscoveries.topArtists && selectedYearDiscoveries.topArtists.length > 0 && (
                  <div className="mb-8">
                    <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
                      <Star className="h-4 w-4 text-amber-400" />
                      Top Discoveries of {discoveriesYear}
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {selectedYearDiscoveries.topArtists.slice(0, 6).map((artist, i) => (
                        <Link key={artist.id} href={`/artists/${artist.id}`} onClick={() => setShowDiscoveriesModal(false)}>
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
                                <p className="text-xs text-text-muted mt-1">
                                  Discovered {formatDate(artist.firstPlayed, { format: "short" })}
                                </p>
                              </div>
                              <div className="text-right">
                                <p className="text-lg font-display text-text-primary">
                                  {formatNumber(artist.plays)}
                                </p>
                                <p className="text-xs text-text-muted">plays since</p>
                              </div>
                            </div>
                          </motion.div>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}

                {/* All Discoveries */}
                {selectedYearDiscoveries.allArtists && selectedYearDiscoveries.allArtists.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
                      <Music className="h-4 w-4" />
                      All {selectedYearDiscoveries.count} Artists
                    </h3>
                    <div className="space-y-1 max-h-64 overflow-y-auto">
                      {selectedYearDiscoveries.allArtists.map((artist, i) => (
                        <Link key={artist.id} href={`/artists/${artist.id}`} onClick={() => setShowDiscoveriesModal(false)}>
                          <motion.div
                            className="flex items-center justify-between p-2 rounded-lg hover:bg-white/5 transition-colors group"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: Math.min(i * 0.01, 0.5) }}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <span className="text-xs text-text-muted w-16">
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
                )}

                {(!selectedYearDiscoveries.topArtists || selectedYearDiscoveries.topArtists.length === 0) && 
                 (!selectedYearDiscoveries.allArtists || selectedYearDiscoveries.allArtists.length === 0) && (
                  <p className="text-center text-text-muted py-8">No discovery data available for this year</p>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </PageContainer>
  );
}
