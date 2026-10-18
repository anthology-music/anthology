"""Registry of all SQLAlchemy models so that ``Base.metadata`` is complete (used by Alembic).

Add the ``models`` module of every new domain here.
"""

from anthology.core import changes, services
from anthology.jobs import models as jobs
from anthology.library import models as library
from anthology.users import models as users

__all__ = ["changes", "jobs", "library", "services", "users"]
