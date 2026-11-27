-- Run in Supabase: SQL Editor -> New query -> paste -> Run. Safe to run again after changes.
-- One row per user holding their tracker data. Row-level security means each
-- signed-in user can only read and write their own row.
create table if not exists public.user_data (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  state      jsonb not null check (pg_column_size(state) < 1000000),
  updated_at timestamptz not null default now()
);

alter table public.user_data enable row level security;

-- Signed-in users need table access; the policies below still limit them to their own row.
-- (Newer Supabase projects don't grant this automatically.) Visitors who aren't signed in get nothing.
grant select, insert, update, delete on public.user_data to authenticated;

drop policy if exists "Users read their own data" on public.user_data;
create policy "Users read their own data"   on public.user_data for select using (auth.uid() = user_id);
drop policy if exists "Users add their own data" on public.user_data;
create policy "Users add their own data"    on public.user_data for insert with check (auth.uid() = user_id);
drop policy if exists "Users update their own data" on public.user_data;
create policy "Users update their own data" on public.user_data for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "Users delete their own data" on public.user_data;
create policy "Users delete their own data" on public.user_data for delete using (auth.uid() = user_id);

-- Quick refreshes from the site's "Refresh offers" button (the refresh-offers Edge Function) are saved here.
-- Everyone can read it (it's the public offer list); only the Edge Function, using the service key, can write.
create table if not exists public.site_data (
  key        text primary key,
  data       jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.site_data enable row level security;
drop policy if exists "Anyone can read site data" on public.site_data;
create policy "Anyone can read site data" on public.site_data for select using (true);
grant select on public.site_data to anon, authenticated;
