"""Matching and ranking on PostgreSQL and SQLite (design: Matching and ranking).

Every free word matches a document word by prefix (PostgreSQL ``tsvector`` with a GIN index,
SQLite FTS5 with prefix indexes); a phrase matches its words in order. A word of three or more
characters that starts no vocabulary term is replaced by up to five similar terms (trigram
similarity, ``pg_trgm`` or the ``similarity`` function the engine registers on SQLite). All of
it is SQL, so the list query can be built without a round trip and the database resolves the
replacements once per query.

Rank buckets: 0 every word matches a whole word, 1 prefixes, 2 typo replacements were used.
"""

from dataclasses import dataclass

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    column,
    exists,
    false,
    func,
    literal,
    literal_column,
    or_,
    select,
    table,
    true,
)

from anthology.search.models import SearchDocument, SearchTerm
from anthology.search.query import RELEASE, TRACK, Filter, Query, Scope

TYPO_MIN_LENGTH = 3
TYPO_CANDIDATES = 5
# pg_trgm's default threshold.
TYPO_SIMILARITY = 0.3
# Upper bound of a prefix range: terms only contain [0-9a-z].
_AFTER_ALL = "{"

# The indexed expression (a literal configuration, so that the planner matches the index).
_TSV = func.to_tsvector(literal_column("'simple'::regconfig"), SearchDocument.text)
_DOC_FTS = table("search_documents_fts", column("rowid"), column("search_documents_fts"))
_TERM_FTS = table("search_terms_fts", column("rowid"), column("search_terms_fts"))
_TERM_ROWID = literal_column("search_terms.rowid")


def _starts_a_term(word: str) -> ColumnElement[bool]:
    return exists().where(SearchTerm.term >= word, SearchTerm.term < word + _AFTER_ALL)


def _parenthesized(expression) -> ColumnElement[str]:
    # NULL (no candidates) stays NULL, so COALESCE falls back to the word itself.
    return literal("(").op("||")(expression).op("||")(literal(")"))


@dataclass(frozen=True)
class Matcher:
    """Builds the conditions of a query for one engine."""

    postgresql: bool

    # --- words ----------------------------------------------------------------------------

    def _candidates(self, word: str) -> Select:
        if self.postgresql:
            score = func.similarity(SearchTerm.term, word)
            return (
                select(SearchTerm.term)
                .where(SearchTerm.term.op("%")(word), score >= TYPO_SIMILARITY)
                .order_by(score.desc(), SearchTerm.term)
                .limit(TYPO_CANDIDATES)
            )
        grams = " OR ".join(f'"{word[i : i + 3]}"' for i in range(len(word) - 2))
        shared = (
            select(_TERM_FTS.c.rowid)
            .where(_TERM_FTS.c.search_terms_fts.op("MATCH")(grams))
            .order_by(literal_column("rank"))
            .limit(200)
        )
        score = func.similarity(SearchTerm.term, word)
        return (
            select(SearchTerm.term)
            .where(_TERM_ROWID.in_(shared), score >= TYPO_SIMILARITY)
            .order_by(score.desc(), SearchTerm.term)
            .limit(TYPO_CANDIDATES)
        )

    def _expression(self, word: str) -> ColumnElement[str] | str:
        """The prefix expression of one word: literal, or resolved in SQL for typos."""
        plain = f"{word}:*" if self.postgresql else f'"{word}"*'
        if len(word) < TYPO_MIN_LENGTH:
            return plain
        candidates = self._candidates(word).subquery()
        if self.postgresql:
            joined = select(func.string_agg(candidates.c.term + ":*", " | ")).scalar_subquery()
            replaced = func.coalesce(_parenthesized(joined), word)
        else:
            quoted = '"' + candidates.c.term + '"*'
            joined = select(func.group_concat(quoted, " OR ")).scalar_subquery()
            replaced = func.coalesce(_parenthesized(joined), f'"{word}"')
        return case((_starts_a_term(word), plain), else_=replaced)

    def _phrase(self, phrase: tuple[str, ...]) -> str:
        if self.postgresql:
            return "(" + " <-> ".join(phrase) + ")"
        return '"' + " ".join(phrase) + '"'

    def _matches(self, expression) -> ColumnElement[bool]:
        if self.postgresql:
            return _TSV.op("@@")(func.to_tsquery("simple", expression))
        return SearchDocument.id.in_(
            select(_DOC_FTS.c.rowid).where(_DOC_FTS.c.search_documents_fts.op("MATCH")(expression))
        )

    def text(self, query: Query) -> list[ColumnElement[bool]]:
        conditions = [self._matches(self._expression(word)) for word in query.words]
        conditions += [self._matches(self._phrase(phrase)) for phrase in query.phrases]
        return conditions

    def bucket(self, query: Query) -> ColumnElement[int]:
        if not query.words:
            return literal(0)
        typo = or_(
            false(),
            *(~_starts_a_term(word) for word in query.words if len(word) >= TYPO_MIN_LENGTH),
        )
        # Whole words, checked on the matched rows only.
        padded = literal(" ") + SearchDocument.text + literal(" ")
        exact = and_(true(), *(padded.like(f"% {word} %") for word in query.words))
        return case((typo, 2), (exact, 0), else_=1)

    # --- filters and scope ----------------------------------------------------------------

    @staticmethod
    def _filter(item: Filter) -> ColumnElement[bool]:
        target = getattr(SearchDocument, item.field)
        if item.field in ("artist", "album", "composer", "genre"):
            padded = literal(" ") + target
            return and_(*(padded.like(f"% {word}%") for word in str(item.value).split()))
        if item.field == "year":
            match item.op:
                case ">":
                    return target > item.value
                case "<":
                    return target < item.value
            return target == item.value
        if item.field == "quality":
            return target.in_(item.value)
        return target == item.value

    def conditions(self, query: Query, scope: Scope, item_type: str) -> list[ColumnElement[bool]]:
        """WHERE conditions of ``query`` for the items of one type; ``[false()]`` if none apply."""
        if query.empty or item_type not in query.types or item_type not in scope.types:
            return [false()]
        # A literal type: the planner chooses the partial index of the type only for constants.
        conditions: list[ColumnElement[bool]] = [
            SearchDocument.item_type == literal_column(f"'{item_type}'")
        ]
        if scope.release_id is not None:
            conditions.append(SearchDocument.release_id == scope.release_id)
        if scope.artist_id is not None:
            if item_type == TRACK:
                conditions.append(
                    or_(
                        SearchDocument.artist_id == scope.artist_id,
                        SearchDocument.album_artist_id == scope.artist_id,
                    )
                )
            elif item_type == RELEASE:
                conditions.append(SearchDocument.album_artist_id == scope.artist_id)
        conditions += [self._filter(item) for item in query.filters]
        conditions += self.text(query)
        return conditions
