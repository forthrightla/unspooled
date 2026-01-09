import { Suspense } from "react";
import fs from "fs";
import path from "path";
import AlbumPageClient from "./client";

interface Album {
  id: number;
  title: string;
  artistName: string;
  plays: number;
}

// Generate static params for all albums at build time
export async function generateStaticParams() {
  const filePath = path.join(process.cwd(), "public/data/albums/index.json");
  
  try {
    const data = fs.readFileSync(filePath, "utf8");
    const albums: Album[] = JSON.parse(data);
    
    // Generate params for all albums
    return albums.map((album) => ({
      id: album.id.toString(),
    }));
  } catch {
    return [];
  }
}

export default async function AlbumPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  
  return (
    <Suspense fallback={<div className="min-h-screen bg-base flex items-center justify-center text-text-muted">Loading...</div>}>
      <AlbumPageClient id={id} />
    </Suspense>
  );
}
