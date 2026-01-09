"use client";

import { useState, useMemo, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Users, Disc3, Music, Search as SearchIcon } from "lucide-react";
import { PageContainer, PageHeader } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SearchInput } from "@/components/ui/SearchInput";
import { useData, useDebounce } from "@/lib/hooks";
import { formatNumber } from "@/lib/format";
import { explorerVariants } from "@/lib/motion";
import Fuse from "fuse.js";

interface Artist {
  id: number;
  name: string;
  plays: number;
}

interface Album {
  id: number;
  title: string;
  artistName: string;
  plays: number;
}

interface Track {
  id: number;
  title: string;
  artistName: string;
  plays: number;
}

type SearchResult = 
  | { type: "artist"; item: Artist }
  | { type: "album"; item: Album }
  | { type: "track"; item: Track };

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 200);
  
  const { data: artists } = useData<Artist[]>("artists/index.json");
  const { data: albums } = useData<Album[]>("albums/index.json");
  const { data: tracks } = useData<Track[]>("tracks/index.json");

  const [results, setResults] = useState<SearchResult[]>([]);

  const fuses = useMemo(() => {
    if (!artists || !albums || !tracks) return null;

    return {
      artists: new Fuse(artists, {
        keys: ["name"],
        threshold: 0.3,
        ignoreLocation: true,
      }),
      albums: new Fuse(albums, {
        keys: ["title", "artistName"],
        threshold: 0.3,
        ignoreLocation: true,
      }),
      tracks: new Fuse(tracks, {
        keys: ["title", "artistName"],
        threshold: 0.3,
        ignoreLocation: true,
      }),
    };
  }, [artists, albums, tracks]);

  useEffect(() => {
    if (!fuses || !debouncedQuery.trim()) {
      setResults([]);
      return;
    }

    const artistResults = fuses.artists
      .search(debouncedQuery, { limit: 5 })
      .map((r): SearchResult => ({ type: "artist", item: r.item }));

    const albumResults = fuses.albums
      .search(debouncedQuery, { limit: 5 })
      .map((r): SearchResult => ({ type: "album", item: r.item }));

    const trackResults = fuses.tracks
      .search(debouncedQuery, { limit: 10 })
      .map((r): SearchResult => ({ type: "track", item: r.item }));

    setResults([...artistResults, ...albumResults, ...trackResults]);
  }, [debouncedQuery, fuses]);

  const getIcon = (type: string) => {
    switch (type) {
      case "artist": return <Users className="h-4 w-4" />;
      case "album": return <Disc3 className="h-4 w-4" />;
      case "track": return <Music className="h-4 w-4" />;
      default: return null;
    }
  };

  const getLink = (result: SearchResult) => {
    switch (result.type) {
      case "artist": return `/artists/${result.item.id}`;
      case "album": return `/albums/${result.item.id}`;
      case "track": return `/artists`; // No individual track pages for now
    }
  };

  const getTitle = (result: SearchResult) => {
    switch (result.type) {
      case "artist": return result.item.name;
      case "album": return result.item.title;
      case "track": return result.item.title;
    }
  };

  const getSubtitle = (result: SearchResult) => {
    switch (result.type) {
      case "artist": return null;
      case "album": return result.item.artistName;
      case "track": return result.item.artistName;
    }
  };

  return (
    <PageContainer>
      <PageHeader
        title="Search"
        subtitle="Find artists, albums, and tracks"
      />

      <SearchInput
        value={query}
        onChange={setQuery}
        placeholder="Search for anything..."
        className="mb-8"
        autoFocus
      />

      {/* Empty State */}
      {!query && (
        <motion.div
          className="text-center py-20"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <SearchIcon className="h-16 w-16 text-text-muted mx-auto mb-4" />
          <p className="text-text-secondary">
            Start typing to search your music library
          </p>
          <p className="text-caption mt-2">
            Search across {formatNumber(artists?.length || 0)} artists, {formatNumber(albums?.length || 0)} albums, and {formatNumber(tracks?.length || 0)} tracks
          </p>
        </motion.div>
      )}

      {/* No Results */}
      {query && results.length === 0 && (
        <motion.div
          className="text-center py-20"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <p className="text-text-secondary">
            No results found for &ldquo;{query}&rdquo;
          </p>
        </motion.div>
      )}

      {/* Results */}
      <AnimatePresence mode="wait">
        {results.length > 0 && (
          <motion.div
            className="space-y-2"
            variants={explorerVariants.stagger}
            initial="hidden"
            animate="visible"
            exit="hidden"
          >
            {results.map((result, index) => (
              <motion.div
                key={`${result.type}-${result.item.id}`}
                variants={explorerVariants.staggerItem}
              >
                <Link href={getLink(result)}>
                  <Card hover padding="md" className="flex items-center gap-4">
                    <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-surface-elevated text-text-muted">
                      {getIcon(result.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-text-primary truncate">
                          {getTitle(result)}
                        </h3>
                        <Badge variant="muted" size="sm">
                          {result.type}
                        </Badge>
                      </div>
                      {getSubtitle(result) && (
                        <p className="text-caption truncate">
                          {getSubtitle(result)}
                        </p>
                      )}
                    </div>
                    <div className="text-right">
                      <span className="text-sm text-text-secondary">
                        {formatNumber(result.item.plays)} plays
                      </span>
                    </div>
                  </Card>
                </Link>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </PageContainer>
  );
}

