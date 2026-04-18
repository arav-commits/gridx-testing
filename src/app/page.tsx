"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { ClusterStatusBar } from "@/components/layout/ClusterStatusBar";
import { GridStatusPanel } from "@/components/dashboard/GridStatusPanel";
import { NextPricePanel } from "@/components/dashboard/NextPricePanel";
import { ActionEngine } from "@/components/dashboard/ActionEngine";
import { Footer } from "@/components/layout/Footer";
import { BsChevronUp } from "react-icons/bs";
import { getCurrentPricingData, PriceData } from "@/lib/pricing";
import { getSecondsUntilNextInterval } from "@/utils/time";

// Supplementary UI data from Supabase (grid lights, trend)
export type GridUiData = {
  gridStatusName: string;
  zoneColor: string;
  demandLevel: string;
  subtitle: string;
  trend: "rising" | "falling";
};

export default function Home() {
  // Price from Python pricing engine (via pricing.ts) — the source of truth
  const [livePrice, setLivePrice] = useState<PriceData | null>(null);
  // Supplementary UI grid health from Supabase (lights, trend)
  const [gridUi, setGridUi] = useState<GridUiData | null>(null);
  const [loading, setLoading] = useState(true);

  // Track which 30-min block we last pushed to Supabase
  const lastPushedBlockRef = useRef<number>(-1);

  /**
   * Compute the current 30-minute block index from IST clock.
   * Returns a unique integer per block (e.g. 28 for "2:00 PM").
   */
  const getCurrentBlockIndex = useCallback(() => {
    const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
    const totalMinutes = now.getHours() * 60 + now.getMinutes();
    // Returns the block number (0-47 for a 24h day in 30-min intervals)
    return Math.floor(totalMinutes / 30);
  }, []);

  /**
   * Push current price to Supabase via the cron endpoint.
   * This is called only when a new 30-minute block starts.
   */
  const pushPriceToSupabase = useCallback(async () => {
    try {
      await fetch('/api/cron/update-price');
      console.log("[GridX] Price pushed to Supabase at new 30-min block.");
    } catch (err) {
      console.error("[GridX] Failed to push price to Supabase:", err);
    }
  }, []);

  /**
   * Fetch supplementary grid health data from Supabase.
   * Only used for trend arrows, zone lights — NOT for the live price.
   */
  const fetchGridHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/prices/current');
      if (res.ok) {
        const json = await res.json();
        setGridUi({
          gridStatusName: json.ui?.gridStatusName || "Grid Stable",
          zoneColor: json.ui?.zoneColor || "green",
          demandLevel: json.ui?.demandLevel || "Low Demand",
          subtitle: json.ui?.subtitle || "",
          trend: json.trend || "falling",
        });
      }
    } catch (err) {
      console.error("[GridX] Failed to fetch grid health:", err);
    }
  }, []);

  /**
   * Core tick — runs every second.
   * 1. Reads price from pricing.ts (Python engine mirror) ← SOURCE OF TRUTH
   * 2. Detects new 30-min block and pushes to Supabase
   */
  const tick = useCallback(() => {
    // Step 1: Compute live price from the pricing engine (same logic as Python)
    const priceData = getCurrentPricingData();
    setLivePrice(priceData);
    if (loading) setLoading(false);

    // Step 2: Detect 30-min block boundary and push to Supabase
    const currentBlock = getCurrentBlockIndex();
    if (lastPushedBlockRef.current !== currentBlock) {
      lastPushedBlockRef.current = currentBlock;
      pushPriceToSupabase();
      // Also refresh grid health after a short delay (Supabase needs the insert to settle)
      setTimeout(fetchGridHealth, 3000);
    }
  }, [getCurrentBlockIndex, pushPriceToSupabase, fetchGridHealth, loading]);

  useEffect(() => {
    // Initial load
    tick();
    fetchGridHealth();

    // Tick every second to keep timer and live price in sync
    const interval = setInterval(tick, 1000);
    // Refresh grid health from Supabase every 60 seconds (trend / lights)
    const healthInterval = setInterval(fetchGridHealth, 60000);

    return () => {
      clearInterval(interval);
      clearInterval(healthInterval);
    };
  }, [tick, fetchGridHealth]);

  if (loading || !livePrice) {
    return (
      <div className="min-h-screen flex items-center justify-center text-lg">
        ⚡ Loading Grid Data...
      </div>
    );
  }

  // Build the UI props — live price always from pricing engine, lights from Supabase
  const uiData = {
    gridStatusName: gridUi?.gridStatusName || livePrice.status === "surplus" ? "Grid Stable" : livePrice.status === "shortage" ? "High Load" : "Moderate Load",
    zoneColor: gridUi?.zoneColor || (livePrice.status === "surplus" ? "green" : livePrice.status === "shortage" ? "red" : "yellow"),
    demandLevel: gridUi?.demandLevel || "Normal Demand",
    subtitle: gridUi?.subtitle || livePrice.message,
  };

  return (
    <div className="min-h-screen flex flex-col bg-[color:var(--background)] transition-colors duration-500 relative overflow-x-hidden">
      
      {/* Background ambient accents */}
      <div className="fixed top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-100/30 dark:bg-emerald-900/10 blur-[120px] -z-10 pointer-events-none"></div>
      <div className="fixed top-[20%] right-[-5%] w-[40%] h-[50%] rounded-full bg-blue-100/20 dark:bg-blue-900/10 blur-[120px] -z-10 pointer-events-none"></div>
      <div className="fixed bottom-[-10%] left-[30%] w-[30%] h-[40%] rounded-full bg-purple-100/20 dark:bg-purple-900/5 blur-[120px] -z-10 pointer-events-none"></div>

      <Navbar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6 w-full">
        
        {/* Cluster status */}
        <ClusterStatusBar />

        {/* Top Panels */}
        <div className="flex flex-col lg:flex-row gap-6 mt-2">
          
          <GridStatusPanel
            ui={uiData}
          />

          <NextPricePanel
            price={livePrice.price}
            trend={gridUi?.trend || (livePrice.status === "shortage" ? "rising" : "falling")}
          />
        </div>

        {/* Action Engine */}
        <ActionEngine />

        {/* Call to action bar */}
        <div className="flex justify-center mt-4">
          <button className="group flex items-center gap-3 bg-[color:var(--glass-bg)] hover:bg-white/60 dark:hover:bg-slate-800/60 transition-all backdrop-blur-md border border-[color:var(--glass-border)] shadow-md rounded-full px-8 py-3.5 hover:scale-105 active:scale-95">
            <BsChevronUp className="text-slate-400 group-hover:-translate-y-1 transition-transform" />
            <span className="font-bold text-[color:var(--color-azure)] font-display tracking-tight">
              View Deep Insights
            </span>
            <span className="px-3 py-1 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-sm font-black ml-2 animate-pulse">
              Live Grid Data
            </span>
          </button>
        </div>
      </main>

      <Footer />
    </div>
  );
}