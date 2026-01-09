import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Instrument_Serif } from "next/font/google";
import "./globals.css";
import { FloatingNav } from "@/components/layout/FloatingNav";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  weight: "400",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Unspooled | Your Music Journey",
  description: "A beautiful archive of your complete listening history. Explore patterns, discover insights, and relive musical memories.",
  keywords: ["music", "listening history", "spotify", "analytics", "wrapped", "unspooled"],
  openGraph: {
    title: "Unspooled | Your Music Journey",
    description: "A beautiful archive of your complete listening history.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} antialiased`}
      >
        {children}
        <FloatingNav />
      </body>
    </html>
  );
}
