"""Product documentation for the in-app Documentation section. Public: articles contain no customer data."""
from fastapi import APIRouter, HTTPException, Query, status

from app import ratelimit
from app.request_context import client_ip
from app.services import help as docs

router = APIRouter(prefix="/help", tags=["help"])


@router.get("")
def help_index():
    return docs.index()


@router.get("/search")
def help_search(q: str = Query(min_length=2, max_length=200)):
    ratelimit.enforce("help-search", client_ip.get(), 120, 60)
    return {"results": docs.search(q)}


@router.get("/for-page")
def help_for_page(path: str = Query(max_length=300)):
    return {"article": docs.for_route(path)}


@router.get("/{slug}")
def help_article(slug: str):
    a = docs.get(slug)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    return a
