-- Create api_keys table
create table public.api_keys (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  key_hash text not null,
  name text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  last_used_at timestamp with time zone,
  
  -- Prevent duplicate keys for safety (though unlikely with random generation)
  constraint api_keys_key_hash_key unique (key_hash)
);

-- Index for faster lookups during auth
create index api_keys_key_hash_idx on public.api_keys (key_hash);
create index api_keys_user_id_idx on public.api_keys (user_id);

-- RLS Policies
alter table public.api_keys enable row level security;

-- Users can view their own keys
create policy "Users can view own api keys"
  on public.api_keys for select
  using (auth.uid() = user_id);

-- Users can delete their own keys
create policy "Users can delete own api keys"
  on public.api_keys for delete
  using (auth.uid() = user_id);

-- Users can create keys (insert)
create policy "Users can create own api keys"
  on public.api_keys for insert
  with check (auth.uid() = user_id);
