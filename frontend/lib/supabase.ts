import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export const supabaseConfig = {
  url: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? ""
};

let client: SupabaseClient | null = null;

/**
 * Browser Supabase client (singleton). Returns null when the project env
 * vars are not configured, so callers can degrade gracefully instead of
 * crashing at import time.
 */
export function getSupabaseClient(): SupabaseClient | null {
  if (!supabaseConfig.url || !supabaseConfig.anonKey) return null;
  if (!client) {
    client = createClient(supabaseConfig.url, supabaseConfig.anonKey, {
      auth: { persistSession: true, autoRefreshToken: true }
    });
  }
  return client;
}

/** The signed-in user's Supabase access token, or null when signed out. */
export async function getAccessToken(): Promise<string | null> {
  const supabase = getSupabaseClient();
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) return null;
  return data.session?.access_token ?? null;
}
