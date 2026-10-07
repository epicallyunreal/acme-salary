from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """`?page=&page_size=` with `{count, next, previous, results}` (SPEC section 8)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
