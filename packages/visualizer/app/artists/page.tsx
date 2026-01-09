"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { Clock, Music, Calendar, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { PageContainer, PageHeader } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SearchInput } from "@/components/ui/SearchInput";
import { useData, useSearch, useDebounce } from "@/lib/hooks";
import { formatNumber, formatDate } from "@/lib/format";

const ITEMS_PER_PAGE = 50;

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

type SortField = "plays" | "durationHours" | "name" | "firstPlay";

export default function ArtistsPage() {
  const { data: artists, isLoading } = useData<Artist[]>("artists/index.json");
  const [sortField, setSortField] = useState<SortField>("plays");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  
  // Debounce search for better performance with large dataset
  const debouncedSearch = useDebounce(searchInput, 200);

  const searchOptions = useMemo(() => ({ 
    keys: ["name"],
    threshold: 0.3,
    ignoreLocation: true,
  }), []);
  const { results } = useSearch(artists || [], searchOptions, debouncedSearch);

  // Reset page when search or sort changes
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, sortField, sortAsc]);

  const sortedArtists = useMemo(() => {
    const list = debouncedSearch ? results : (artists || []);
    
    return [...list].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "plays":
          cmp = b.plays - a.plays;
          break;
        case "durationHours":
          cmp = b.durationHours - a.durationHours;
          break;
        case "name":
          cmp = a.name.localeCompare(b.name);
          break;
        case "firstPlay":
          cmp = new Date(a.firstPlay).getTime() - new Date(b.firstPlay).getTime();
          break;
      }
      return sortAsc ? -cmp : cmp;
    });
  }, [artists, results, debouncedSearch, sortField, sortAsc]);

  // Pagination
  const totalPages = Math.ceil(sortedArtists.length / ITEMS_PER_PAGE);
  const paginatedArtists = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return sortedArtists.slice(start, start + ITEMS_PER_PAGE);
  }, [sortedArtists, page]);

  const toggleSort = (field: SortField) => {
    if (field === sortField) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  if (isLoading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading artists...</div>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Artists"
        subtitle={
          debouncedSearch 
            ? `${formatNumber(sortedArtists.length)} results for "${debouncedSearch}"`
            : `${formatNumber(artists?.length || 0)} artists in your library`
        }
      />

      {/* Search & Sort */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <SearchInput
          value={searchInput}
          onChange={setSearchInput}
          placeholder="Search artists..."
          className="flex-1"
        />
        <div className="flex gap-2">
          <Button
            variant={sortField === "plays" ? "primary" : "secondary"}
            size="sm"
            onClick={() => toggleSort("plays")}
            leftIcon={<ArrowUpDown className="h-4 w-4" />}
          >
            Plays
          </Button>
          <Button
            variant={sortField === "durationHours" ? "primary" : "secondary"}
            size="sm"
            onClick={() => toggleSort("durationHours")}
          >
            Hours
          </Button>
          <Button
            variant={sortField === "name" ? "primary" : "secondary"}
            size="sm"
            onClick={() => toggleSort("name")}
          >
            A-Z
          </Button>
        </div>
      </div>

      {/* Artists List */}
      <div className="space-y-2">
        {paginatedArtists.map((artist, index) => (
          <Link key={artist.id} href={`/artists/${artist.id}`}>
            <Card hover padding="md" className="flex items-center gap-4">
              {/* Rank */}
              <span className="w-8 text-center text-lg font-display text-text-muted">
                {(page - 1) * ITEMS_PER_PAGE + index + 1}
              </span>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-text-primary truncate">
                  {artist.name}
                </h3>
                <div className="flex items-center gap-3 text-caption mt-1">
                  <span className="flex items-center gap-1">
                    <Music className="h-3 w-3" />
                    {formatNumber(artist.plays)} plays
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatNumber(Math.round(artist.durationHours))}h
                  </span>
                  <span className="hidden md:flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Since {formatDate(artist.firstPlay, { format: "short" })}
                  </span>
                </div>
              </div>

              {/* Tracks count */}
              <div className="text-right hidden md:block">
                <span className="text-sm text-text-secondary">
                  {artist.uniqueTracks} tracks
                </span>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 mt-8">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            leftIcon={<ChevronLeft className="h-4 w-4" />}
          >
            Previous
          </Button>
          <span className="text-text-secondary">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            rightIcon={<ChevronRight className="h-4 w-4" />}
          >
            Next
          </Button>
        </div>
      )}

      {paginatedArtists.length === 0 && searchInput && (
        <div className="text-center py-12 text-text-muted">
          No artists found matching &ldquo;{searchInput}&rdquo;
        </div>
      )}
    </PageContainer>
  );
}

