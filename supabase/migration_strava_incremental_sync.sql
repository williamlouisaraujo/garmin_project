-- Multi-account user model + Strava incremental sync tables
create extension if not exists pgcrypto;

create table if not exists user_accounts (
  user_id uuid primary key default gen_random_uuid(),
  strava_athlete_id bigint unique,
  garmin_user_id text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_accounts_at_least_one_account check (
    strava_athlete_id is not null or garmin_user_id is not null
  )
);

create table if not exists strava_activities (
  activity_id bigint primary key,
  user_id uuid not null references user_accounts(user_id) on delete cascade,
  name text,
  type text,
  distance_m double precision,
  moving_time_s integer,
  elapsed_time_s integer,
  total_elevation_gain_m double precision,
  start_date timestamptz,
  start_date_local text,
  timezone text,
  raw_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists strava_activity_details (
  activity_id bigint primary key references strava_activities(activity_id) on delete cascade,
  user_id uuid not null references user_accounts(user_id) on delete cascade,
  raw_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists strava_best_efforts (
  activity_id bigint not null references strava_activities(activity_id) on delete cascade,
  user_id uuid not null references user_accounts(user_id) on delete cascade,
  name text not null,
  distance double precision not null,
  elapsed_time integer,
  start_index integer not null,
  end_index integer not null,
  pr_rank integer,
  start_date_local text,
  raw_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (activity_id, name, distance, start_index, end_index)
);

create table if not exists strava_sync_state (
  user_id uuid primary key references user_accounts(user_id) on delete cascade,
  oldest_activity_date_loaded bigint,
  latest_activity_date_loaded bigint,
  backfill_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace view vw_strava_records as
with normalized as (
  select
    user_id,
    activity_id,
    name as distance_name,
    case
      when lower(name) = '1/2 mile' then 804.67
      when lower(name) = '1k' then 1000
      when lower(name) = '1 mile' then 1609.34
      when lower(name) = '2 mile' then 3218.69
      when lower(name) = '5k' then 5000
      when lower(name) = '10k' then 10000
      when lower(name) = '10 mile' then 16093.4
      when lower(name) = 'half-marathon' then 21097.5
      when lower(name) = 'marathon' then 42195
      when lower(name) = '50k' then 50000
      else distance
    end as normalized_distance,
    elapsed_time,
    start_date_local as start_date,
    start_index,
    end_index,
    pr_rank
  from strava_best_efforts
), ranked as (
  select *,
    row_number() over (
      partition by user_id, normalized_distance
      order by elapsed_time asc nulls last, start_date asc nulls last
    ) as rn
  from normalized
)
select
  user_id,
  distance_name,
  normalized_distance,
  elapsed_time as best_elapsed_time,
  activity_id,
  start_date,
  start_index,
  end_index,
  pr_rank
from ranked
where rn = 1;
