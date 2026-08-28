"""Directory of Open Access Books provider using its documented REST API."""

from scripts.providers.dspace_openbooks import DSpaceOpenBooksProvider


class DOABProvider(DSpaceOpenBooksProvider):
    name = "DOAB"
    base_url = "https://directory.doabooks.org"
    limit_env = "OPENBOOK_DOAB_LIMIT"
    query_env = "OPENBOOK_DOAB_QUERY"
