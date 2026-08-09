import json
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.getenv("DB_PASSWORD"),
    database="taipei_day_trip"
)

cursor = db.cursor()

with open("data/taipei-attractions.json", encoding="utf-8") as file:
    raw = json.load(file)

attractions = raw["list"]

for attraction in attractions:
    sql = """
    INSERT INTO attractions
    (id, name, category, description, address, mrt, lat, lng, transport)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        attraction["_id"],
        attraction["name"],
        attraction["CAT"],
        attraction["description"],
        attraction["address"],
        attraction["MRT"],
        attraction["latitude"],
        attraction["longitude"],
        attraction["direction"]
    )

    cursor.execute(sql, values)

    imgurls = attraction["imgurls"]
    parts = imgurls.split(".jpg")

    for part in parts:
        if part != "":
            image_url = part + ".jpg"

            img_sql = """
            INSERT INTO attraction_images
            (attraction_id, url)
            VALUES (%s, %s)
            """

            img_values = (
                attraction["_id"],
                image_url
            )

            cursor.execute(img_sql, img_values)

db.commit()

cursor.close()
db.close()

print("全部寫入完成")