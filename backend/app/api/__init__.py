from fastapi import APIRouter

from app.api.routes import analytics, assets, auth, bridge, cameras, citizen, demo, events, fleet, ingest, maps, notifications, perception, settings, users, work_orders, ws

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(fleet.router)
api_router.include_router(events.router)
api_router.include_router(assets.router)
api_router.include_router(work_orders.router)
api_router.include_router(analytics.router)
api_router.include_router(bridge.router)
api_router.include_router(ingest.router)
api_router.include_router(cameras.router)
api_router.include_router(maps.router)
api_router.include_router(demo.router)
api_router.include_router(users.router)
api_router.include_router(settings.router)
api_router.include_router(perception.router)
api_router.include_router(ws.router)
api_router.include_router(citizen.router)
api_router.include_router(notifications.router)
