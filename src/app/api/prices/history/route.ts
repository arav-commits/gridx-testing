import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabaseClient';

export const revalidate = 0;

/**
 * GET /api/prices/history
 *
 * Returns today's price entries from dynamic_prices, ordered chronologically.
 * Used by the "View Deep Insights" timeline panel.
 */
export async function GET() {
  try {
    // Compute start of today in UTC (IST midnight = UTC 18:30 previous day)
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000; // IST is UTC+5:30
    const istNow = new Date(now.getTime() + istOffset);
    const istMidnight = new Date(istNow);
    istMidnight.setHours(0, 0, 0, 0);
    const utcMidnight = new Date(istMidnight.getTime() - istOffset);

    const { data: rows, error } = await supabase
      .from('dynamic_prices')
      .select('price, demand, supply, created_at')
      .gte('created_at', utcMidnight.toISOString())
      .order('created_at', { ascending: true });

    if (error) {
      console.error("Supabase history error:", error);
      return NextResponse.json({ slots: [] }, { status: 200 });
    }

    // Transform rows into timeline slots with IST labels
    const slots = (rows || []).map(row => {
      const dt = new Date(row.created_at);
      const istTime = new Date(dt.getTime() + istOffset);
      const h = istTime.getUTCHours();
      const m = istTime.getUTCMinutes();
      const pad = (n: number) => String(n).padStart(2, '0');
      const endM = m + 30;
      const endH = endM >= 60 ? h + 1 : h;
      const endMin = endM >= 60 ? 0 : endM;

      return {
        label: `${pad(h)}:${pad(m)}–${pad(endH % 24)}:${pad(endMin)}`,
        price: Number(row.price),
        demand: Number(row.demand),
        supply: Number(row.supply),
        created_at: row.created_at,
      };
    });

    return NextResponse.json({ slots });
  } catch (err: any) {
    console.error("History API error:", err);
    return NextResponse.json({ slots: [] }, { status: 200 });
  }
}
