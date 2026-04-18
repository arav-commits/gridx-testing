import { createClient } from "@supabase/supabase-js";

const supabaseUrl = "https://jijcogmlrmiznurassuc.supabase.co";
const supabaseAnonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImppamNvZ21scm1pem51cmFzc3VjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY0NzQ0MjAsImV4cCI6MjA5MjA1MDQyMH0.te0EdjcZomWd5z-IlzAsO1VYr2TvYlZmQY-jrHvroiY";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);