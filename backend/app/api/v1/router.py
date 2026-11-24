"""Version 1 API router registry."""

from fastapi import APIRouter

from app.api.v1 import auth, briefs, clusters, exports, keywords, projects, research, workflows

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(research.router)
api_router.include_router(keywords.router)
api_router.include_router(clusters.router)
api_router.include_router(workflows.router)
api_router.include_router(briefs.router)
api_router.include_router(exports.router)
