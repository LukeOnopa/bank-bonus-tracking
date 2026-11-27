-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
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

create policy "Users read their own data"   on public.user_data for select using (auth.uid() = user_id);
create policy "Users add their own data"    on public.user_data for insert with check (auth.uid() = user_id);
create policy "Users update their own data" on public.user_data for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users delete their own data" on public.user_data for delete using (auth.uid() = user_id);
