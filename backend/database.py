"""
SQLite Database Service for Bengaluru Pulse

Stores prediction history for analytics and dashboard.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "traffic.db"


class Database:

    def __init__(self):
        self.connection = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.create_table()

    def create_table(self):

        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp TEXT,

            location TEXT,

            traffic_volume INTEGER,

            average_speed REAL,

            weather TEXT,

            predicted_congestion REAL,

            traffic_status TEXT

        )
        """)

        self.connection.commit()

    def save_prediction(
        self,
        location,
        traffic_volume,
        average_speed,
        weather,
        predicted_congestion,
        traffic_status,
    ):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO predictions(

                timestamp,

                location,

                traffic_volume,

                average_speed,

                weather,

                predicted_congestion,

                traffic_status

            )

            VALUES(?,?,?,?,?,?,?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                location,
                traffic_volume,
                average_speed,
                weather,
                predicted_congestion,
                traffic_status,
            ),
        )

        self.connection.commit()

    def get_history(self):

        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT *
            FROM predictions
            ORDER BY id DESC
        """)

        return [dict(row) for row in cursor.fetchall()]

    def analytics(self):

        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM predictions
        """)

        total_predictions = cursor.fetchone()[0]

        cursor.execute("""
            SELECT AVG(predicted_congestion)
            FROM predictions
        """)

        avg_congestion = cursor.fetchone()[0]

        cursor.execute("""
            SELECT location, COUNT(*) as total
            FROM predictions
            GROUP BY location
            ORDER BY total DESC
            LIMIT 1
        """)

        row = cursor.fetchone()

        most_common_location = row[0] if row else "N/A"

        return {

            "total_predictions": total_predictions,

            "average_congestion": round(avg_congestion, 2)
            if avg_congestion
            else 0,

            "most_common_location": most_common_location,

        }

    def clear_history(self):

        cursor = self.connection.cursor()

        cursor.execute("DELETE FROM predictions")

        self.connection.commit()


database = Database()