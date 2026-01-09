import { Suspense } from "react";
import fs from "fs";
import path from "path";
import ArtistPageClient from "./client";

interface Artist {
  id: number;
  name: string;
  plays: number;
}

// Generate static params for all artists at build time
export async function generateStaticParams() {
  const filePath = path.join(process.cwd(), "public/data/artists/index.json");
  
  try {
    const data = fs.readFileSync(filePath, "utf8");
    const artists: Artist[] = JSON.parse(data);
    
    // Generate params for all artists
    return artists.map((artist) => ({
      id: artist.id.toString(),
    }));
  } catch {
    return [];
  }
}

export default async function ArtistPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  
  return (
    <Suspense fallback={<div className="min-h-screen bg-base flex items-center justify-center text-text-muted">Loading...</div>}>
      <ArtistPageClient id={id} />
    </Suspense>
  );
}
