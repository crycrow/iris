from fastapi import APIRouter
from . import risk_types, risks, indicators

router = APIRouter()
router.include_router(risk_types.router)
router.include_router(risks.router)
router.include_router(indicators.router)
