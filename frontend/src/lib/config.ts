export const config = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) || (import.meta.env.DEV ? 'http://127.0.0.1:8000/api/v1' : ''),
  supabaseUrl: (import.meta.env.VITE_SUPABASE_URL as string | undefined) || '',
  supabaseKey: (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined) || '',
}
