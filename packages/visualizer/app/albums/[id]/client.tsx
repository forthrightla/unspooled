"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowLeft, Music, User } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useData } from "@/lib/hooks";
import { formatNumber } from "@/lib/format";
import { explorerVariants } from "@/lib/motion";

interface Album {
  id: number;
  title: string;
  artistName: string;
  plays: number;
}

export default function AlbumPageClient({ id }: { id: string }) {
  const { data: albums, isLoading } = useData<Album[]>("albums/index.json");

  const album = albums?.find((a) => a.id === parseInt(id));
  const rank = albums?.findIndex((a) => a.id === parseInt(id));

  if (isLoading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-text-muted">Loading album...</div>
        </div>
      </PageContainer>
    );
  }

  if (!album) {
    return (
      <PageContainer>
        <div className="text-center py-20">
          <h1 className="text-display-md text-text-primary mb-4">Album not found</h1>
          <Link href="/">
            <Button variant="secondary">Go home</Button>
          </Link>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      {/* Back Button */}
      <Link href="/" className="inline-flex items-center gap-2 text-text-secondary hover:text-text-primary mb-8 transition-colors">
        <ArrowLeft className="h-4 w-4" />
        <span>Back</span>
      </Link>

      {/* Hero */}
      <motion.div
        className="mb-12"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-start gap-4 mb-6">
          {rank !== undefined && rank >= 0 && (
            <Badge variant="accent" size="md">#{rank + 1} Album</Badge>
          )}
        </div>

        <h1 className="text-display-lg text-text-primary mb-2">{album.title}</h1>
        <p className="text-body text-text-secondary flex items-center gap-2">
          <User className="h-4 w-4" />
          {album.artistName}
        </p>
      </motion.div>

      {/* Stats */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
        variants={explorerVariants.stagger}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={explorerVariants.staggerItem}>
          <Card padding="lg">
            <div className="flex items-center gap-4">
              <Music className="h-8 w-8 text-accent" />
              <div>
                <p className="text-3xl font-display text-text-primary">
                  {formatNumber(album.plays)}
                </p>
                <p className="text-caption">Total plays</p>
              </div>
            </div>
          </Card>
        </motion.div>
      </motion.div>
    </PageContainer>
  );
}

