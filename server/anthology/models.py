"""Registry of all SQLAlchemy models so that ``Base.metadata`` is complete (used by Alembic).

Add the ``models`` module of every new domain here.
"""

from anthology.core import changes, services
from anthology.jobs import models as jobs
from anthology.library import models as library
from anthology.library_import import models as library_import
from anthology.metadata_lookup import models as metadata_lookup
from anthology.quality_analysis import models as quality_analysis
from anthology.review import models as review
from anthology.users import models as users

__all__ = [
    "changes",
    "jobs",
    "library",
    "library_import",
    "metadata_lookup",
    "quality_analysis",
    "review",
    "services",
    "users",
]
