import React from "react";
import { GlassCard } from "../ui/GlassCard";
import { BsLightningFill, BsSunFill, BsBatteryFull } from "react-icons/bs";

interface GridStatusPanelProps {
  ui?: {
    gridStatusName: string;
    zoneColor: string;
    demandLevel: string;
    subtitle: string;
  };
}

export function GridStatusPanel({ ui }: GridStatusPanelProps) {
  // Determine color themes based on zoneColor
  const isGreen = ui?.zoneColor === "green";
  const isRed = ui?.zoneColor === "red";
  const isYellow = ui?.zoneColor === "yellow";

  const ringColor = isRed ? "border-red-300" : isYellow ? "border-amber-300" : "border-emerald-300";
  const bgColor = isRed ? "bg-red-100/60" : isYellow ? "bg-amber-100/60" : "bg-emerald-100/60";
  const iconColor = isRed ? "text-red-500" : isYellow ? "text-amber-500" : "text-emerald-500";
  const badgeBg = isRed ? "bg-red-50" : isYellow ? "bg-amber-50" : "bg-emerald-50";
  const badgeText = isRed ? "text-red-600" : isYellow ? "text-amber-600" : "text-emerald-600";
  const badgeBorder = isRed ? "border-red-200" : isYellow ? "border-amber-200" : "border-emerald-200";

  return (
    <GlassCard className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 flex-1">
      <div className="flex items-center gap-5">
        <div className={`w-20 h-20 rounded-full ${bgColor} border-4 ${badgeBorder} flex items-center justify-center shrink-0 shadow-sm relative`}>
          {/* Subtle pulse ring */}
          <div className={`absolute inset-0 rounded-full border-2 ${ringColor} animate-ping opacity-20`}></div>
          <BsLightningFill className={`${iconColor} text-3xl`} />
        </div>
        
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-2xl font-bold font-display text-[color:var(--color-azure)]">{ui?.gridStatusName || "Grid Stable"}</h2>
            <span className={`px-3 py-1 rounded-full ${badgeBg} ${badgeText} text-xs font-bold border ${badgeBorder}`}>
              {ui?.demandLevel || "Low Demand"}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-500">
            {ui?.subtitle.toLowerCase().includes("high load increasing demand") ? (
              <TrendingUpIcon className="text-red-500" />
            ) : (
              <TrendingDownIcon className="text-emerald-500" />
            )}
            <span className={isRed ? "text-red-500 font-medium" : ""}>{ui?.subtitle || "Load ↓ 4% in last 10 min · Voltage stable at 231V"}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-8 pl-4 md:pl-8 md:border-l border-slate-200">
        <div className="flex flex-col items-center">
          <div className="flex items-center gap-2 mb-1">
            <BsSunFill className="text-orange-400" />
            <span className="text-xl font-bold text-[color:var(--color-azure)]">78%</span>
          </div>
          <span className="text-xs font-medium text-slate-400">Solar</span>
        </div>
        
        <div className="flex flex-col items-center">
          <div className="flex items-center gap-2 mb-1">
            <BsBatteryFull className="text-[color:var(--color-azure)]" />
            <span className="text-xl font-bold text-[color:var(--color-azure)]">84%</span>
          </div>
          <span className="text-xs font-medium text-slate-400">Battery</span>
        </div>
      </div>
    </GlassCard>
  );
}

function TrendingDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} stroke="currentColor" fill="none" strokeWidth="2" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" height="1em" width="1em" xmlns="http://www.w3.org/2000/svg"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"></polyline><polyline points="17 18 23 18 23 12"></polyline></svg>
  );
}

function TrendingUpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} stroke="currentColor" fill="none" strokeWidth="2" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" height="1em" width="1em" xmlns="http://www.w3.org/2000/svg"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>
  );
}
