"""Role agents — importing this package registers the full roster.

Each module calls `base.register(...)` at import time, so simply importing
`stonkslib.agents.roles` populates the registry. Add a new role by creating a
module here and importing it below.
"""

from stonkslib.agents.roles import (  # noqa: F401
    fundamental,
    technical,
    researcher,
    portfolio_manager,
)
