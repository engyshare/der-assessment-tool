from fastapi import APIRouter
router = APIRouter()
@router.get('/a')
def a(): return {}
