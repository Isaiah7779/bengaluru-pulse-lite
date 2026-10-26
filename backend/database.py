"""Legacy prediction-history store, now backed by the main SQLAlchemy database.

Interface kept identical for services.ModelBundle and the legacy endpoints.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from db.models import LegacyPrediction
from db.session import session_scope


class Database:
    def save_prediction(
        self,
        location,
        traffic_volume,
        average_speed,
        weather,
        predicted_congestion,
        traffic_status,
    ):
        with session_scope() as session:
            session.add(
                LegacyPrediction(
                    location=location,
                    traffic_volume=int(traffic_volume),
                    average_speed=float(average_speed),
                    weather=weather,
                    predicted_congestion=float(predicted_congestion),
                    traffic_status=traffic_status,
                )
            )

    def get_history(self, limit: int = 500):
        with session_scope() as session:
            rows = session.scalars(
                select(LegacyPrediction).order_by(LegacyPrediction.id.desc()).limit(limit)
            ).all()
            return [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "location": r.location,
                    "traffic_volume": r.traffic_volume,
                    "average_speed": r.average_speed,
                    "weather": r.weather,
                    "predicted_congestion": r.predicted_congestion,
                    "traffic_status": r.traffic_status,
                }
                for r in rows
            ]

    def analytics(self):
        with session_scope() as session:
            total = session.scalar(select(func.count(LegacyPrediction.id))) or 0
            avg = session.scalar(select(func.avg(LegacyPrediction.predicted_congestion)))
            row = session.execute(
                select(LegacyPrediction.location, func.count().label("n"))
                .group_by(LegacyPrediction.location)
                .order_by(func.count().desc())
                .limit(1)
            ).first()
        return {
            "total_predictions": total,
            "average_congestion": round(avg, 2) if avg else 0,
            "most_common_location": row[0] if row else "N/A",
        }

    def clear_history(self):
        with session_scope() as session:
            session.execute(delete(LegacyPrediction))


database = Database()
