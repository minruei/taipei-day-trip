from fastapi import *
from fastapi.responses import FileResponse, JSONResponse
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.getenv("DB_PASSWORD"),
    database="taipei_day_trip"
)


@app.get("/api/categories")
async def get_categories():
    cursor = db.cursor()

    try:
        cursor.execute("SELECT DISTINCT category FROM attractions")
        results = cursor.fetchall()

        categories = []

        for row in results:
            categories.append(row[0])

        return {"data": categories}

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "伺服器內部錯誤"
            }
        )

    finally:
        cursor.close()


@app.get("/api/mrts")
async def get_mrts():
    cursor = db.cursor()

    try:
        cursor.execute(
            """
            SELECT mrt
            FROM attractions
            WHERE mrt IS NOT NULL
            GROUP BY mrt
            ORDER BY COUNT(*) DESC
            """
        )

        results = cursor.fetchall()

        mrts = []

        for row in results:
            mrts.append(row[0])

        return {"data": mrts}

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "伺服器內部錯誤"
            }
        )

    finally:
        cursor.close()


@app.get("/api/attraction/{attractionId}")
async def get_attraction(attractionId: int):
    cursor = db.cursor()

    try:
        cursor.execute(
            "SELECT * FROM attractions WHERE id = %s",
            (attractionId,)
        )

        result = cursor.fetchone()

        if result is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "message": "景點編號不正確"
                }
            )

        cursor.execute(
            "SELECT url FROM attraction_images WHERE attraction_id = %s",
            (attractionId,)
        )

        image_rows = cursor.fetchall()

        images = []

        for row in image_rows:
            images.append(row[0])

        attraction = {
            "id": result[0],
            "name": result[1],
            "category": result[2],
            "description": result[3],
            "address": result[4],
            "transport": result[8],
            "mrt": result[5],
            "lat": result[6],
            "lng": result[7],
            "images": images
        }

        return {"data": attraction}

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "伺服器內部錯誤"
            }
        )

    finally:
        cursor.close()


@app.get("/api/attractions")
async def get_attractions(
    page: int = 0,
    keyword: str = None,
    category: str = None
):
    cursor = db.cursor()

    try:
        conditions = []
        values = []

        if keyword:
            conditions.append("(name LIKE %s OR mrt = %s)")
            values.append("%" + keyword + "%")
            values.append(keyword)

        if category:
            conditions.append("category = %s")
            values.append(category)

        where_sql = ""

        if conditions:
            where_sql = " WHERE " + " AND ".join(conditions)

        count_sql = "SELECT COUNT(*) FROM attractions" + where_sql

        cursor.execute(count_sql, tuple(values))
        total = cursor.fetchone()[0]

        sql = "SELECT * FROM attractions" + where_sql
        sql = sql + " LIMIT 12 OFFSET %s"

        query_values = values.copy()
        query_values.append(page * 12)

        cursor.execute(sql, tuple(query_values))
        results = cursor.fetchall()

        data = []

        for row in results:
            attraction_id = row[0]

            cursor.execute(
                "SELECT url FROM attraction_images WHERE attraction_id = %s",
                (attraction_id,)
            )

            image_rows = cursor.fetchall()

            images = []

            for image_row in image_rows:
                images.append(image_row[0])

            data.append({
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "description": row[3],
                "address": row[4],
                "transport": row[8],
                "mrt": row[5],
                "lat": row[6],
                "lng": row[7],
                "images": images
            })

        if (page + 1) * 12 < total:
            next_page = page + 1
        else:
            next_page = None

        return {
            "nextPage": next_page,
            "data": data
        }

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "伺服器內部錯誤"
            }
        )

    finally:
        cursor.close()


# Static Pages (Never Modify Code in this Block)

@app.get("/", include_in_schema=False)
async def index(request: Request):
    return FileResponse("./static/index.html", media_type="text/html")


@app.get("/attraction/{id}", include_in_schema=False)
async def attraction(request: Request, id: int):
    return FileResponse("./static/attraction.html", media_type="text/html")


@app.get("/booking", include_in_schema=False)
async def booking(request: Request):
    return FileResponse("./static/booking.html", media_type="text/html")


@app.get("/thankyou", include_in_schema=False)
async def thankyou(request: Request):
    return FileResponse("./static/thankyou.html", media_type="text/html")