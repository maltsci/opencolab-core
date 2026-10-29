# Lab Knowledge OS v1 Migration Runbook

## Scope and non-goals

This runbook validates Alembic revision `w4x5y6z7a8b9_add_lab_knowledge_foundation.py` against a sanitized, disposable PostgreSQL copy. The revision adds these empty Phase 0 tables:

- `research_directions`
- `research_direction_relations`
- `member_research_directions`
- `project_research_directions`
- `research_asset_directions`
- `research_object_directions`
- `research_group_stewards`
- `research_direction_stewards`
- `knowledge_suggestions`
- `knowledge_change_events`

The migration must start at revision `v3w4x5y6z7a8` and end at `w4x5y6z7a8b9`. It does not backfill Research Directions, relationships, stewards, suggestions, or change events. No application traffic, production database, raw research content, credentials, or benchmark data may be used in this procedure.

Run the PostgreSQL procedure only in an approved secure environment. Keep its output, backup identifier, and checksum in restricted operational records; do not add them to Git, tickets, logs, or this document.

## Required backup and restore proof

1. Obtain approval from the database owner and privacy reviewer for a sanitized source snapshot. The snapshot must exclude raw files, PDF contents, API keys, tokens, and unnecessary personal fields.
2. Record the backup identifier, SHA-256 digest, source revision, PostgreSQL version, and operator identity in the restricted sign-off record below.
3. A database administrator must restore the backup into a newly created, disposable PostgreSQL database. The database name must identify the migration dry run and must not be a production database.
4. Set only the disposable target connection string in `OPENCOLAB_DATABASE_URL` in the secured operator shell. Do not print or commit its value.
5. Prove restore usability before the migration: `psql "$OPENCOLAB_DATABASE_URL" -c 'SELECT 1'` must return one row, and `backend/.venv/bin/python -m alembic current` must report `v3w4x5y6z7a8`.
6. Retain the sanitized backup until the release rollback window closes. Destroy the disposable database and the backup according to the lab retention policy after sign-off.

## Pre-migration inventory queries

Run the following with `psql "$OPENCOLAB_DATABASE_URL"` before upgrading. Save only the aggregate results in restricted operational records.

```sql
SELECT 'users' AS metric, COUNT(*)::bigint AS count
FROM users
UNION ALL
SELECT 'active_research_group_memberships', COUNT(*)::bigint
FROM research_group_members
WHERE removed_at IS NULL
UNION ALL
SELECT 'projects', COUNT(*)::bigint
FROM projects
UNION ALL
SELECT 'access_policies', COUNT(*)::bigint
FROM access_policies
ORDER BY metric;

SELECT COALESCE(visibility_scope, 'null') AS visibility_scope, COUNT(*)::bigint AS count
FROM research_assets
GROUP BY visibility_scope
ORDER BY visibility_scope;

SELECT COALESCE(type, 'null') AS research_object_type, COUNT(*)::bigint AS count
FROM research_objects
GROUP BY type
ORDER BY research_object_type;

SELECT table_name,
       CASE WHEN to_regclass('public.' || table_name) IS NULL THEN 'absent' ELSE 'present' END AS state
FROM (VALUES
    ('research_directions'),
    ('research_direction_relations'),
    ('member_research_directions'),
    ('project_research_directions'),
    ('research_asset_directions'),
    ('research_object_directions'),
    ('research_group_stewards'),
    ('research_direction_stewards'),
    ('knowledge_suggestions'),
    ('knowledge_change_events')
) AS expected_new_tables(table_name)
ORDER BY table_name;
```

Expected result: every expected new table is `absent` before the upgrade. If any is present, stop and reconcile the target database history before proceeding.

## Duplicate and conflict report

Run the report before the upgrade. Any result row requires a data-owner decision recorded in the restricted sign-off record before the migration continues.

```sql
SELECT 'active_group_membership' AS conflict_type,
       group_id,
       user_id,
       COUNT(*)::bigint AS row_count
FROM research_group_members
WHERE removed_at IS NULL
GROUP BY group_id, user_id
HAVING COUNT(*) > 1
UNION ALL
SELECT 'research_asset_source' AS conflict_type,
       source_id AS group_id,
       NULL::text AS user_id,
       COUNT(*)::bigint AS row_count
FROM research_assets
WHERE source_id IS NOT NULL
GROUP BY source_id
HAVING COUNT(*) > 1;

SELECT research_asset_id,
       COALESCE(asset_revision_id, 'all-revisions') AS revision_scope,
       subject_type,
       COALESCE(subject_id, group_role, 'unspecified') AS subject_scope,
       effect,
       COUNT(*)::bigint AS row_count
FROM access_policies
WHERE enabled IS TRUE
GROUP BY research_asset_id,
         COALESCE(asset_revision_id, 'all-revisions'),
         subject_type,
         COALESCE(subject_id, group_role, 'unspecified'),
         effect
HAVING COUNT(*) > 1
ORDER BY research_asset_id, revision_scope, subject_type, subject_scope, effect;
```

This report identifies duplicates and potentially overlapping active access-policy rules. It does not modify legacy data. A conflict does not authorize a data cleanup during this migration; defer any cleanup to a separately approved change.

## Upgrade command

In the repository root, after recording the pre-migration inventory and confirming the revision:

```bash
cd backend
OPENCOLAB_ENV=test .venv/bin/python -m alembic upgrade head
OPENCOLAB_ENV=test .venv/bin/python -m alembic current
OPENCOLAB_ENV=test .venv/bin/python -m alembic heads
```

Expected result: `current` and `heads` identify `w4x5y6z7a8b9` as the only head. Stop immediately on any failed command, unexpected revision, lock timeout, or schema error. Do not retry against production.

## Post-migration reconciliation queries

Rerun the legacy inventory queries from the pre-migration section and compare every aggregate result exactly. Then run the following queries:

```sql
SELECT 'research_directions' AS table_name, COUNT(*)::bigint AS count FROM research_directions
UNION ALL
SELECT 'research_direction_relations', COUNT(*)::bigint FROM research_direction_relations
UNION ALL
SELECT 'member_research_directions', COUNT(*)::bigint FROM member_research_directions
UNION ALL
SELECT 'project_research_directions', COUNT(*)::bigint FROM project_research_directions
UNION ALL
SELECT 'research_asset_directions', COUNT(*)::bigint FROM research_asset_directions
UNION ALL
SELECT 'research_object_directions', COUNT(*)::bigint FROM research_object_directions
UNION ALL
SELECT 'research_group_stewards', COUNT(*)::bigint FROM research_group_stewards
UNION ALL
SELECT 'research_direction_stewards', COUNT(*)::bigint FROM research_direction_stewards
UNION ALL
SELECT 'knowledge_suggestions', COUNT(*)::bigint FROM knowledge_suggestions
UNION ALL
SELECT 'knowledge_change_events', COUNT(*)::bigint FROM knowledge_change_events
ORDER BY table_name;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
      'research_directions',
      'research_direction_relations',
      'member_research_directions',
      'project_research_directions',
      'research_asset_directions',
      'research_object_directions',
      'research_group_stewards',
      'research_direction_stewards',
      'knowledge_suggestions',
      'knowledge_change_events'
  )
ORDER BY table_name;
```

Expected result:

- Every legacy aggregate is identical to the saved pre-migration result.
- All ten new tables exist.
- Every new-table count is zero because Phase 0 has no automatic backfill.
- Alembic reports only `w4x5y6z7a8b9` as the current head.

## Downgrade command

Downgrade only the disposable PostgreSQL copy, and only after confirming all ten new tables are empty:

```bash
cd backend
OPENCOLAB_ENV=test .venv/bin/python -m alembic downgrade v3w4x5y6z7a8
OPENCOLAB_ENV=test .venv/bin/python -m alembic current
```

After the downgrade, rerun the legacy inventory queries. Verify the aggregate results remain unchanged and verify that every entry in the expected-new-table query reports `absent`.

## Rollback decision criteria

Rollback the disposable copy to `v3w4x5y6z7a8` when any of the following occurs:

- an upgrade command fails or does not end at the required head;
- a legacy inventory aggregate changes;
- a required new table or index is missing;
- a new table contains rows immediately after upgrade;
- a reconciliation query produces an unexpected error;
- a security, privacy, or database owner withholds sign-off.

Do not run the production migration until a separate approved run has a clean upgrade, reconciliation, downgrade, and restore proof. After Phase 0 is released, do not edit the deployed migration; use a new Alembic revision for any correction.

## Sign-off record

Store completed values in the restricted operational record, not this repository.

| Field | Recorded value |
| --- | --- |
| Sanitized backup identifier | |
| Sanitized backup SHA-256 | |
| Source Alembic revision | |
| Target PostgreSQL version | |
| Upgrade operator | |
| Upgrade timestamp | |
| Pre/post inventory comparison | |
| New-table count verification | |
| Downgrade operator | |
| Downgrade timestamp | |
| Restore proof reviewer | |
| Database owner approval | |
| Privacy reviewer approval | |
