"use server";

import { createClient } from "@supabase/supabase-js";

export async function saveUserProfile(userData: {
  id: string;
  name: string;
  phone: string;
  state: string;
  city: string;
  cluster_id: number;
}) {
  try {
    const supabaseAdmin = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!
    );

    const { error } = await supabaseAdmin.from("users").upsert(userData);
    
    if (error) {
      console.error("[GridX] Server Action Error saving user profile:", error);
      return { success: false, error: error.message };
    }
    
    return { success: true };
  } catch (err: any) {
    console.error("[GridX] Server Action Exception:", err);
    return { success: false, error: err?.message || "Unknown error occurred" };
  }
}
