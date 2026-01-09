"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowLeft, Disc3, TrendingUp, TrendingDown, Minus, Music } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useData } from "@/lib/hooks";
import { formatNumber, formatDate } from "@/lib/format";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface Artist {
  id: number;
  name: string;
  plays: number;
  durationHours: number;
  uniqueTracks: number;
  firstPlay: string;
  lastPlay: string;
  country?: string;
  type?: string;
}

interface YearlyData {
  year: number;
  plays: number;
  wasTopArtist: boolean;
}

interface MonthlyData {
  month: string;
  plays: number;
  durationMs?: number;
}

interface TopAlbum {
  title: string;
  plays: number;
  tracks: number;
}

interface TopTrack {
  title: string;
  plays: number;
}

interface ArtistDetail extends Artist {
  peakYear?: number;
  peakMonth?: string;
  yearlyTimeline?: YearlyData[];
  monthlyTimeline?: MonthlyData[];
  topAlbums?: TopAlbum[];
  topTracks?: TopTrack[];
}

// Format month for display
const formatMonthLabel = (monthStr: string) => {
  const [year, month] = monthStr.split('-');
  const date = new Date(parseInt(year), parseInt(month) - 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
};

// Custom tooltip for the chart
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const displayLabel = label?.includes('-') ? formatMonthLabel(label) : label;
    return (
      <div className="bg-surface-elevated border border-border-subtle px-3 py-2 rounded-lg shadow-lg">
        <p className="text-sm font-medium text-text-primary">{displayLabel}</p>
        <p className="text-lg font-display text-accent">
          {formatNumber(payload[0].value)} plays
        </p>
      </div>
    );
  }
  return null;
};

export default function ArtistPageClient({ id }: { id: string }) {
  const { data: artists, isLoading } = useData<Artist[]>("artists/index.json");
  const { data: artistDetail } = useData<ArtistDetail>(`artists/${id}.json`);

  const artist = artistDetail || artists?.find((a) => a.id === parseInt(id));
  const rank = artists?.findIndex((a) => a.id === parseInt(id));
  
  // Use complete monthly data
  const chartData = useMemo(() => {
    if (!artistDetail?.monthlyTimeline) return [];
    return artistDetail.monthlyTimeline.map(m => ({
      label: m.month,
      plays: m.plays,
    }));
  }, [artistDetail?.monthlyTimeline]);
  
  const peakData = useMemo(() => {
    if (chartData.length === 0) return null;
    return chartData.reduce((max, d) => d.plays > max.plays ? d : max, chartData[0]);
  }, [chartData]);

  // Calculate trend from recent data
  const trend = useMemo(() => {
    if (chartData.length < 4) return "stable";
    const recent = chartData.slice(-2);
    const recentAvg = recent.reduce((sum, d) => sum + d.plays, 0) / recent.length;
    const older = chartData.slice(0, -2);
    if (older.length === 0) return "stable";
    const olderAvg = older.reduce((sum, d) => sum + d.plays, 0) / older.length;
    if (olderAvg === 0) return "stable";
    const change = (recentAvg - olderAvg) / olderAvg;
    if (change > 0.3) return "up";
    if (change < -0.3) return "down";
    return "stable";
  }, [chartData]);

  if (isLoading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading artist...</div>
        </div>
      </PageContainer>
    );
  }

  if (!artist) {
    return (
      <PageContainer>
        <div className="text-center py-20">
          <h1 className="text-display-md text-text-primary mb-4">Artist not found</h1>
          <Link href="/artists">
            <Button variant="secondary">Back to artists</Button>
          </Link>
        </div>
      </PageContainer>
    );
  }

  const yearsListening = new Date(artist.lastPlay).getFullYear() - new Date(artist.firstPlay).getFullYear();

  return (
    <PageContainer>
      {/* Back Button */}
      <Link href="/artists" className="inline-flex items-center gap-2 text-text-secondary hover:text-text-primary mb-8 transition-colors">
        <ArrowLeft className="h-4 w-4" />
        <span>All Artists</span>
      </Link>

      {/* Hero */}
      <motion.div
        className="mb-10"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex flex-wrap items-center gap-3 mb-4">
          {rank !== undefined && rank >= 0 && (
            <Badge variant="accent" size="md">#{rank + 1} Artist</Badge>
          )}
          {artist.country && (
            <Badge variant="muted" size="md">{artist.country}</Badge>
          )}
        </div>
        <h1 className="text-display-xl text-text-primary">{artist.name}</h1>
      </motion.div>

      {/* Stats Row */}
      <motion.div
        className="grid grid-cols-2 md:grid-cols-5 gap-6 mb-12"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        <div>
          <p className="text-text-muted text-sm">Total Plays</p>
          <p className="text-3xl font-display text-text-primary">{formatNumber(artist.plays)}</p>
        </div>
        <div>
          <p className="text-text-muted text-sm">Hours Listened</p>
          <p className="text-3xl font-display text-text-primary">{formatNumber(Math.round(artist.durationHours))}</p>
        </div>
        <div>
          <p className="text-text-muted text-sm">Unique Tracks</p>
          <p className="text-3xl font-display text-text-primary">{artist.uniqueTracks}</p>
        </div>
        <div>
          <p className="text-text-muted text-sm">Days Listened</p>
          <p className="text-3xl font-display text-text-primary">{Math.round(artist.durationHours / 24)}</p>
        </div>
        <div>
          <p className="text-text-muted text-sm">Discovered</p>
          <p className="text-3xl font-display text-text-primary">{formatDate(artist.firstPlay, { format: "short" })}</p>
        </div>
      </motion.div>

      {/* Interactive Area Chart */}
      {chartData.length > 0 && (
        <motion.div
          className="mb-12"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-display text-text-primary">Listening Over Time</h2>
            {peakData && (
              <div className="text-sm text-text-muted">
                Peak: <span className="text-accent font-medium">
                  {peakData.label.includes('-') ? formatMonthLabel(peakData.label) : peakData.label}
                </span> ({formatNumber(peakData.plays)} plays)
              </div>
            )}
          </div>

          {/* Recharts Area Chart */}
          <div className="h-64 bg-surface rounded-xl p-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={chartData}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id={`gradient-${artist.id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis 
                  dataKey="label" 
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#888', fontSize: 11 }}
                  dy={10}
                  tickFormatter={(value) => {
                    if (value.includes('-')) {
                      const [year, month] = value.split('-');
                      const date = new Date(parseInt(year), parseInt(month) - 1);
                      return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
                    }
                    return value;
                  }}
                  interval="preserveStartEnd"
                />
                <YAxis 
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#888', fontSize: 12 }}
                  tickFormatter={(value) => formatNumber(value)}
                  width={50}
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="plays"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  fill={`url(#gradient-${artist.id})`}
                  dot={{ fill: '#8b5cf6', strokeWidth: 0, r: 4 }}
                  activeDot={{ 
                    fill: '#8b5cf6', 
                    stroke: '#18181b', 
                    strokeWidth: 2, 
                    r: 6 
                  }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}

      {/* Top Tracks & Albums */}
      <motion.div
        className="grid md:grid-cols-2 gap-6 mb-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        {/* Top Tracks */}
        {artistDetail?.topTracks && artistDetail.topTracks.length > 0 && (
          <div className="bg-surface rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <Music className="h-5 w-5 text-pink-400" />
              <h3 className="font-medium text-text-primary">Top Tracks</h3>
            </div>
            <div className="space-y-2">
              {artistDetail.topTracks.slice(0, 5).map((track, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-text-muted text-sm w-5">{i + 1}</span>
                  <span className="text-text-primary truncate flex-1">{track.title}</span>
                  <span className="text-text-muted text-sm whitespace-nowrap">{formatNumber(track.plays)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top Albums */}
        {artistDetail?.topAlbums && artistDetail.topAlbums.length > 0 && (
          <div className="bg-surface rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <Disc3 className="h-5 w-5 text-cyan-400" />
              <h3 className="font-medium text-text-primary">Top Albums</h3>
            </div>
            <div className="space-y-2">
              {artistDetail.topAlbums.map((album, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-text-muted text-sm w-5">{i + 1}</span>
                  <span className="text-text-primary truncate flex-1">{album.title}</span>
                  <span className="text-text-muted text-sm whitespace-nowrap">{formatNumber(album.plays)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </motion.div>

      {/* Stats Summary */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
      >
        <div className="bg-surface rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-5 w-5 text-emerald-400" />
            <h3 className="font-medium text-text-primary">Stats</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <p className="text-text-muted text-sm">Years listening</p>
              <p className="text-text-primary font-medium">{yearsListening}</p>
            </div>
            <div>
              <p className="text-text-muted text-sm">Plays per year</p>
              <p className="text-text-primary font-medium">{formatNumber(Math.round(artist.plays / Math.max(yearsListening, 1)))}</p>
            </div>
            <div>
              <p className="text-text-muted text-sm">Hours per year</p>
              <p className="text-text-primary font-medium">{formatNumber(Math.round(artist.durationHours / Math.max(yearsListening, 1)))}</p>
            </div>
            <div>
              <p className="text-text-muted text-sm">Avg per track</p>
              <p className="text-text-primary font-medium">{Math.round(artist.plays / artist.uniqueTracks)}×</p>
            </div>
            <div>
              <p className="text-text-muted text-sm">Trend</p>
              <p className={`font-medium flex items-center gap-1 ${
                trend === "up" ? "text-emerald-400" : 
                trend === "down" ? "text-rose-400" : 
                "text-text-primary"
              }`}>
                {trend === "up" && <TrendingUp className="h-4 w-4" />}
                {trend === "down" && <TrendingDown className="h-4 w-4" />}
                {trend === "stable" && <Minus className="h-4 w-4" />}
                {trend === "up" ? "Rising" : trend === "down" ? "Fading" : "Steady"}
              </p>
            </div>
          </div>
        </div>
      </motion.div>
    </PageContainer>
  );
}
