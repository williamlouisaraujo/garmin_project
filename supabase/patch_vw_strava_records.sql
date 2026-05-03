-- Patch : ajout de activity_name dans vw_strava_records via join strava_activities
-- À appliquer dans l'éditeur SQL Supabase (Run once)
create or replace view vw_strava_records as
with normalized as (
  select
    be.user_id,
    be.activity_id,
    be.name as distance_name,
    case
      when lower(be.name) = '1/2 mile' then 804.67
      when lower(be.name) = '1k' then 1000
      when lower(be.name) = '1 mile' then 1609.34
      when lower(be.name) = '2 mile' then 3218.69
      when lower(be.name) = '5k' then 5000
      when lower(be.name) = '10k' then 10000
      when lower(be.name) = '10 mile' then 16093.4
      when lower(be.name) = 'half-marathon' then 21097.5
      when lower(be.name) = 'marathon' then 42195
      when lower(be.name) = '50k' then 50000
      else be.distance
    end as normalized_distance,
    be.elapsed_time,
    be.start_date_local as start_date,
    be.start_index,
    be.end_index,
    be.pr_rank
  from strava_best_efforts be
), ranked as (
  select *,
    row_number() over (
      partition by user_id, normalized_distance
      order by elapsed_time asc nulls last, start_date asc nulls last
    ) as rn
  from normalized
)
select
  r.user_id,
  r.distance_name,
  r.normalized_distance,
  r.elapsed_time as best_elapsed_time,
  r.activity_id,
  sa.name as activity_name,
  r.start_date,
  r.start_index,
  r.end_index,
  r.pr_rank
from ranked r
left join strava_activities sa on sa.activity_id = r.activity_id
where r.rn = 1;
