"""Registry of all SQLAlchemy models so that ``Base.metadata`` is complete (used by Alembic).

Add the ``models`` module of every new domain here.
"""

from anthology.core import changes, services
from anthology.jobs import models as jobs
from anthology.library import models as library
from anthology.library_import import models as library_import
from anthology.metadata_lookup import models as metadata_lookup
from anthology.playback import models as playback
from anthology.quality_analysis import models as quality_analysis
from anthology.review import models as review
from anthology.search import index as search_index  # installs the document maintenance
from anthology.search import models as search
from anthology.tagging import models as tagging
from anthology.transcoding import invalidation as transcoding_invalidation  # installs it
from anthology.transcoding import models as transcoding
from anthology.users import models as users

__all__ = [
    "changes",
    "jobs",
    "library",
    "library_import",
    "metadata_lookup",
    "playback",
    "quality_analysis",
    "review",
    "search",
    "search_index",
    "services",
    "tagging",
    "transcoding",
    "transcoding_invalidation",
    "users",
]
