import { Suspense } from "react";
import StoryPageClient from "./client";

// Generate static params for all years at build time
export async function generateStaticParams() {
  // Pre-define available years from 2005-2025
  const years = Array.from({ length: 21 }, (_, i) => 2005 + i);
  return years.map((year) => ({
    year: year.toString(),
  }));
}

export default async function StoryPage({ params }: { params: Promise<{ year: string }> }) {
  const { year } = await params;
  
  return (
    <Suspense fallback={<div className="fixed inset-0 bg-base flex items-center justify-center text-text-muted">Loading your story...</div>}>
      <StoryPageClient year={year} />
    </Suspense>
  );
}
