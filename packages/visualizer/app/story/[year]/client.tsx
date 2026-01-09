"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useData } from "@/lib/hooks";
import { formatNumber } from "@/lib/format";
import { storyVariants } from "@/lib/motion";
import { StoryStat } from "@/components/ui/StatCard";

interface StorySlide {
  id: string;
  type: string;
  title?: string;
  subtitle?: string;
  value?: number;
  label?: string;
  gradient?: string;
  entity?: {
    id: number;
    name?: string;
    title?: string;
    artistName?: string;
    plays: number;
  };
}

interface StoryData {
  year: number;
  slides: StorySlide[];
  generatedAt: string;
}

const gradients: Record<string, string> = {
  "story-1": "from-orange-500 via-pink-500 to-violet-600",
  "story-2": "from-cyan-400 via-blue-500 to-purple-600",
  "story-3": "from-emerald-400 via-teal-500 to-cyan-600",
  default: "from-violet-500 via-purple-500 to-pink-500",
};

export default function StoryPageClient({ year }: { year: string }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  
  const { data: story, isLoading } = useData<StoryData>(`story/${year}.json`);

  const goNext = () => {
    if (story && currentIndex < story.slides.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };

  const goPrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-base flex items-center justify-center">
        <div className="animate-pulse text-text-muted">Loading your story...</div>
      </div>
    );
  }

  if (!story) {
    return (
      <div className="fixed inset-0 bg-base flex flex-col items-center justify-center">
        <h1 className="text-display-md text-text-primary mb-4">Story not found</h1>
        <Link href="/" className="text-accent hover:text-accent-hover">
          Go home
        </Link>
      </div>
    );
  }

  const slide = story.slides[currentIndex];
  const gradient = gradients[slide.gradient || "default"] || gradients.default;
  const progress = ((currentIndex + 1) / story.slides.length) * 100;

  return (
    <div className="fixed inset-0 overflow-hidden">
      {/* Background */}
      <motion.div
        className={`absolute inset-0 bg-gradient-to-br ${gradient}`}
        key={currentIndex}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      />

      {/* Overlay pattern */}
      <div className="absolute inset-0 bg-black/20" />

      {/* Progress bar */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-white/20 z-50">
        <motion.div
          className="h-full bg-white"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* Close button */}
      <Link
        href="/story"
        className="absolute top-4 right-4 z-50 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
      >
        <X className="h-6 w-6 text-white" />
      </Link>

      {/* Year indicator */}
      <div className="absolute top-4 left-4 z-50">
        <span className="text-white/60 text-sm font-medium">{story.year}</span>
      </div>

      {/* Slide content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentIndex}
          className="absolute inset-0 flex flex-col items-center justify-center p-8 text-center"
          variants={storyVariants.slideNext}
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          {slide.type === "intro" && (
            <>
              <motion.h1
                className="story-headline text-white mb-4"
                variants={storyVariants.counter}
              >
                {slide.title}
              </motion.h1>
              <motion.p
                className="text-xl text-white/80"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                {slide.subtitle}
              </motion.p>
            </>
          )}

          {slide.type === "stat" && (
            <>
              <StoryStat
                value={formatNumber(slide.value || 0)}
                label={slide.label || ""}
                gradient="warm"
              />
              {slide.subtitle && (
                <motion.p
                  className="text-lg text-white/70 mt-4"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.5 }}
                >
                  {slide.subtitle}
                </motion.p>
              )}
            </>
          )}

          {slide.type === "artist" && slide.entity && (
            <>
              <motion.p
                className="text-lg text-white/60 mb-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              >
                {slide.title}
              </motion.p>
              <motion.h2
                className="story-headline text-white mb-2"
                variants={storyVariants.counter}
              >
                {slide.entity.name}
              </motion.h2>
              <motion.p
                className="text-xl text-white/80"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                {formatNumber(slide.entity.plays)} plays
              </motion.p>
            </>
          )}

          {slide.type === "track" && slide.entity && (
            <>
              <motion.p
                className="text-lg text-white/60 mb-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              >
                {slide.title}
              </motion.p>
              <motion.h2
                className="text-4xl md:text-6xl font-display text-white mb-2"
                variants={storyVariants.counter}
              >
                {slide.entity.title}
              </motion.h2>
              <motion.p
                className="text-xl text-white/80"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                by {slide.entity.artistName} • {formatNumber(slide.entity.plays)} plays
              </motion.p>
            </>
          )}

          {slide.type === "outro" && (
            <>
              <motion.h1
                className="story-headline text-white mb-4"
                variants={storyVariants.counter}
              >
                {slide.title}
              </motion.h1>
              <motion.p
                className="text-xl text-white/80 mb-8"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                {slide.subtitle}
              </motion.p>
              <motion.div
                className="flex gap-4"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
              >
                <Link
                  href="/story"
                  className="inline-flex items-center gap-2 px-6 py-3 bg-white text-black rounded-full font-medium hover:bg-white/90 transition-colors"
                >
                  View All Years
                </Link>
                <Link
                  href="/"
                  className="inline-flex items-center gap-2 px-6 py-3 bg-white/20 text-white rounded-full font-medium hover:bg-white/30 transition-colors"
                >
                  Explore Dashboard
                </Link>
              </motion.div>
            </>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="absolute bottom-8 left-0 right-0 flex items-center justify-center gap-4 z-50">
        <button
          onClick={goPrev}
          disabled={currentIndex === 0}
          className="p-3 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft className="h-6 w-6 text-white" />
        </button>
        
        <span className="text-white/60 text-sm min-w-[60px] text-center">
          {currentIndex + 1} / {story.slides.length}
        </span>
        
        <button
          onClick={goNext}
          disabled={currentIndex === story.slides.length - 1}
          className="p-3 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronRight className="h-6 w-6 text-white" />
        </button>
      </div>

      {/* Touch areas for mobile */}
      <button
        onClick={goPrev}
        className="absolute left-0 top-0 bottom-0 w-1/3 z-40"
        aria-label="Previous slide"
      />
      <button
        onClick={goNext}
        className="absolute right-0 top-0 bottom-0 w-1/3 z-40"
        aria-label="Next slide"
      />
    </div>
  );
}

