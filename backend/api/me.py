"""The caller's private data: favourite places and trip history.

Every query is filtered by the authenticated user's id; another user's record
is reported as not found (no existence leak).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import current_user
from core.errors import NotFound
from db.models import FavouritePlace, Trip, User
from db.session import get_db

router = APIRouter(prefix="/v1/me", tags=["me"])


class FavouriteIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    name: Optional[str] = Field(None, max_length=200)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class FavouriteOut(FavouriteIn):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class TripOut(BaseModel):
    id: int
    origin_label: Optional[str]
    origin_lat: float
    origin_lon: float
    destination_label: Optional[str]
    destination_lat: float
    destination_lon: float
    vehicle: str
    preference: str
    depart_at: Optional[datetime]
    chosen_route: Optional[Dict[str, Any]]
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("/favourites", response_model=List[FavouriteOut])
def list_favourites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(FavouritePlace).where(FavouritePlace.user_id == user.id).order_by(FavouritePlace.id)).all()


@router.post("/favourites", response_model=FavouriteOut, status_code=201)
def add_favourite(body: FavouriteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = len(db.scalars(select(FavouritePlace.id).where(FavouritePlace.user_id == user.id)).all())
    if count >= 50:
        from core.errors import AppError

        raise AppError("Favourite limit (50) reached", code="limit_reached", status_code=409)
    fav = FavouritePlace(user_id=user.id, **body.model_dump())
    db.add(fav)
    db.commit()
    return fav


@router.delete("/favourites/{fav_id}", status_code=204)
def delete_favourite(fav_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fav = db.scalar(select(FavouritePlace).where(FavouritePlace.id == fav_id, FavouritePlace.user_id == user.id))
    if fav is None:
        raise NotFound("Favourite not found")
    db.delete(fav)
    db.commit()
    return Response(status_code=204)


@router.get("/trips", response_model=List[TripOut])
def list_trips(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc()).limit(limit)
    ).all()


@router.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id))
    if trip is None:
        raise NotFound("Trip not found")
    return trip


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id))
    if trip is None:
        raise NotFound("Trip not found")
    db.delete(trip)
    db.commit()
    return Response(status_code=204)


@router.delete("/trips", status_code=204)
def clear_trips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for trip in db.scalars(select(Trip).where(Trip.user_id == user.id)).all():
        db.delete(trip)
    db.commit()
    return Response(status_code=204)
