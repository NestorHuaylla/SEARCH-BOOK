"""OAPEN Library provider using its documented REST search API."""

from scripts.providers.dspace_openbooks import DSpaceOpenBooksProvider


class OAPENProvider(DSpaceOpenBooksProvider):
    name = "OAPEN Library"
    base_url = "https://library.oapen.org"
    limit_env = "OPENBOOK_OAPEN_LIMIT"
    query_env = "OPENBOOK_OAPEN_QUERY"
