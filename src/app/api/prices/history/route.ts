import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabaseClient';

export const revalidate = 0;

/**
 * GET /api/prices/history
 *
 * Returns the FULL 48-slot daily timeline for "View Deep Insights".
 * - Past slots → actual price from `price_logs`
 * - Future slots → `pending: true` (rendered as "Coming Soon" in UI)
 * - Always returns exactly 48 entries, regardless of how many DB rows exist.
 */
export async function GET() {
  try {
    // ── Compute today's date in IST ───────────────────────────────────────
    const now = new Date();
    const istNow = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
    const year = istNow.getFullYear();
    const month = String(istNow.getMonth() + 1).padStart(2, '0');
    const day = String(istNow.getDate()).padStart(2, '0');
    const todayIST = `${year}-${month}-${day}`; // e.g. "2026-04-19"

    // Current slot index in IST
    const currentSlotIndex = istNow.getHours() * 2 + (istNow.getMinutes() >= 30 ? 1 : 0);

    // ── Fetch all rows for today from price_logs ──────────────────────────
    const { data: rows, error } = await supabase
      .from('price_logs')
      .select('slot_index, price, demand, supply')
      .eq('slot_date', todayIST)
      .order('slot_index', { ascending: true });

    if (error) {
      console.error('Supabase history error:', error);
    }

    // Build a lookup map: slot_index → row data
    const slotMap = new Map<number, { price: number; demand: number; supply: number }>();
    if (rows) {
      for (const row of rows) {
        slotMap.set(row.slot_index, {
          price: Number(row.price),
          demand: Number(row.demand),
          supply: Number(row.supply),
        });
      }
    }

    // ── Generate full 48-slot grid ────────────────────────────────────────
    const pad = (n: number) => String(n).padStart(2, '0');
    const slots = [];

    for (let i = 0; i < 48; i++) {
      const startH = Math.floor(i / 2);
      const startM = (i % 2) * 30;
      const endH = Math.floor((i + 1) / 2);
      const endM = ((i + 1) % 2) * 30;
      const label = `${pad(startH)}:${pad(startM)}–${pad(endH % 24)}:${pad(endM)}`;

      const dbRow = slotMap.get(i);
      const isFuture = i > currentSlotIndex;

      if (dbRow && !isFuture) {
        // Past or current slot with data
        slots.push({
          label,
          slotIndex: i,
          price: dbRow.price,
          demand: dbRow.demand,
          supply: dbRow.supply,
          pending: false,
        });
      } else if (!isFuture && dbRow) {
        // Has data (backfilled) — show it
        slots.push({
          label,
          slotIndex: i,
          price: dbRow.price,
          demand: dbRow.demand,
          supply: dbRow.supply,
          pending: false,
        });
      } else if (!isFuture && !dbRow) {
        // Past slot but data missing (worker was down) — show as missing
        slots.push({
          label,
          slotIndex: i,
          price: null,
          demand: null,
          supply: null,
          pending: false,
          missing: true,
        });
      } else {
        // Future slot — Coming Soon
        slots.push({
          label,
          slotIndex: i,
          price: null,
          demand: null,
          supply: null,
          pending: true,
        });
      }
    }

    return NextResponse.json({
      date: todayIST,
      currentSlotIndex,
      totalSlots: 48,
      slots,
    });
  } catch (err: unknown) {
    console.error('History API error:', err);
    return NextResponse.json({ slots: [], date: null, currentSlotIndex: -1, totalSlots: 48 }, { status: 200 });
  }
}
