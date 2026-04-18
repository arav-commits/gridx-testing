import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabaseClient';
import { getCurrentPricingData, PRICING_DATA } from '@/lib/pricing';

export const revalidate = 0;

export async function GET(request: Request) {
  try {
    // Generate price from local logic
    const { price, time } = getCurrentPricingData(); // we will ignore the `status` from this since we redefined it
    
    // Find the demand and supply for the matching time to store in DB
    const matchedRow = PRICING_DATA.find((r) => r.time === time);
    const demand = matchedRow?.demand || 10;
    const supply = matchedRow?.supply || 10;

    // Insert into Supabase
    const { data, error } = await supabase
      .from('dynamic_prices')
      .insert({
        price: price,
        demand: demand,
        supply: supply
      })
      .select()
      .single();

    if (error) {
      console.error("Supabase Insert Error:", error);
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ success: true, message: "Price updated", data });
  } catch (error: any) {
    console.error("API error:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
