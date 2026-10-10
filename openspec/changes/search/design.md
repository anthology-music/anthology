# Design

## Context

PostgreSQL in production, SQLite in development (ADR 0010); progressive loading with subscriptions, counts first and selection rules (sync-protocol); local cache in the client (Dexie on web, SQLite on Tauri/Capacitor). See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Fast, tolerant search without an extra search server.
- One query model for text syntax, chips, selection rules and offline search.

**Non-Goals:**
- Semantic/similarity search ("sounds like").
- Searching inside sheet-music notes or lyrics.

## Decisions

### Search documents

A denormalised table `search_document(item_type, item_id, title, people, extra, normalized_text, tsv, sort_key, change_seq)` with one row per searchable item, maintained by the owning domains' write path (same transaction). `normalized_text` is lower-cased, `unaccent`ed and German-folded (ä→ae, ö→oe, ü→ue, ß→ss applied to both document and query), so "Mueller" and "Müller" match.

Alternative considered: querying domain tables directly. Rejected: joins across recordings, releases, artists and works per keystroke cannot meet 300 ms at 500,000 tracks.

Alternative considered: an external search server (Meilisearch, OpenSearch). Rejected: extra container and synchronisation for a household-scale dataset that PostgreSQL handles.

### Matching and ranking (PostgreSQL)

- Prefix and full-text: `tsv @@ to_tsquery('simple', 'term:*')`, GIN index.
- Typo tolerance: `pg_trgm` similarity on `normalized_text` (GIN trigram index) for terms with no exact/prefix hits.
- Ranking: exact > prefix > full-text rank > trigram similarity, then `sort_key`; results per type are keyset-paged on `(rank_bucket, sort_key, item_id)`.
- Counts per type: computed with capped counting (`LIMIT 10001` → shown as "10,000+") to keep the 300 ms target; exact counts load in the background.

SQLite (dev/tests): FTS5 with prefix indexes and the same normalisation; trigram matching via FTS5's `trigram` tokenizer.

### Query model and syntax

The client parses text syntax into the same structure the chips produce: `{text, filters: [{field, op, value}], context}`. Supported fields and operators are listed in `docs/architecture/search-syntax.md` (e.g. `artist`, `album`, `work`, `arranger`, `publisher`, `genre`, `year`, `format`, `quality`, `source`, `type`; operators `:`, `:>`, `:<`, `:"…"`). The server validates and reports unknown fields per token. The structure is also the selection rule for bulk actions.

### Search as a subscription

`search` is a subscription type: `snapshot_meta` with counts per type, then chunks per type for the requested window. Typing sends a new `subscribe` (debounced 100 ms) and cancels the previous one.

### Offline search

The client indexes its cached and offline items in its local store (SQLite FTS5 on Tauri/Capacitor, a prefix + n-gram index in Dexie on web) with the same normalisation; the same parser produces the query. Results carry `local: true`.

### Progressive loading

Counts first (capped), per-type keyset paging, debounced re-subscription, cancellation of stale queries on the server.

## Risks / Trade-offs

- [Trigram fallback is slow for very short terms] → trigram only from 3 characters; shorter input uses prefix search only.
- [German folding can create false matches in other languages] → folding only adds matches, ranking prefers exact matches.
- [Web offline index size] → only cached/offline items are indexed; capped by the offline limit.
