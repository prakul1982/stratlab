"""Every route an app answers, flattened (LIVE4-016).

Newer FastAPI keeps an included router as one `_IncludedRouter` entry in `app.routes` instead of copying its routes in, so a
loop over `app.routes` sees only the routes declared on the app itself. The self-healing sweep looked its remedies up that way
and answered "No route /admin/ipos/refresh" for a route that exists (it lives on the IPO router), eight times a day, and emailed
the owner about a fault in the fixer. Anything that needs to find a route by its path goes through here."""
from __future__ import annotations

from typing import Any, Iterable


def every_route(routes: Iterable[Any]) -> list[Any]:
    """Each route with its full path (an included router's prefix applied). The items answer `.path`, `.methods`, `.endpoint`
    and `.dependant` like a route does; `.original_route` (where present) is the route as declared, for isinstance checks."""
    routes = list(routes or [])
    try:
        from fastapi.routing import iter_route_contexts        # FastAPI that keeps included routers unflattened
    except ImportError:                                         # older FastAPI copies every route into app.routes
        iter_route_contexts = None
    if iter_route_contexts is not None:
        return list(iter_route_contexts(routes))
    out: list[Any] = []
    for r in routes:
        inner = getattr(r, "original_router", None)
        out += every_route(inner.routes) if inner is not None else [r]
    return out


def declared(route: Any) -> Any:
    """The route as it was declared (an APIRoute for an ordinary endpoint)."""
    return getattr(route, "original_route", route)


def find(app: Any, path: str, method: str = "POST") -> Any | None:
    """The route answering `method path` exactly (path as written in the route, e.g. "/admin/ipos/refresh"), or None."""
    for r in every_route(getattr(app, "routes", None) or []):
        if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or ()):
            return r
    return None
