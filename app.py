from fastapi import *
from fastapi.responses import FileResponse, JSONResponse
import mysql.connector
import os
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta, timezone

load_dotenv()   # 讀取 .env 檔，把裡面的設定變成環境變數（例如資料庫密碼）

app = FastAPI()


def get_db():
    """建立一條連到 MySQL 的連線。每支 API 各自呼叫、各自關閉。"""
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.getenv("DB_PASSWORD"),   # 密碼不寫死在程式裡，從 .env 拿
        database="taipei_day_trip"
    )

JWT_SECRET = os.getenv("JWT_SECRET")   # 從 .env 讀出簽章用的鑰匙
JWT_ALGORITHM = "HS256"                # 簽章演算法
JWT_EXPIRE_DAYS = 7                    # token 有效期，規格要求七天

# 定義註冊時前端要送來的資料格式
# FastAPI 會照這個檢查欄位齊不齊、型別對不對，也會自動產生 /docs 的輸入框
class SignUpInput(BaseModel):
    name: str
    email: str 
    password: str

# 定義登入時前端要送來的資料格式
class SignInInput(BaseModel):
    email: str
    password: str

@app.get("/api/categories")
async def get_categories():
    """回傳所有景點分類，給首頁的分類選單用。"""
    db = get_db()          # 接通資料庫
    cursor = db.cursor()   # 拿起話筒，準備下 SQL

    try:
        # DISTINCT 去除重複
        cursor.execute("SELECT DISTINCT category FROM attractions")
        results = cursor.fetchall()   # fetchall 是拿全部，回傳一串 tuple

        categories = []

        # 每個 row 長得像 ("美食",)，所以取 row[0] 才是字串本身
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
        # 不管成功失敗都會執行，確保連線被關掉，否則連線數會用完
        cursor.close()
        db.close()


@app.get("/api/mrts")
async def get_mrts():
    """回傳捷運站名稱，依照該站的景點數量由多到少排序。"""
    db = get_db()
    cursor = db.cursor()

    try:
        # GROUP BY mrt 把同一站的景點併成一組
        # 再用 COUNT(*) 算每組有幾個景點，由多到少排
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
        db.close()


@app.get("/api/attraction/{attractionId}")
async def get_attraction(attractionId: int):
    """依照景點編號回傳單一景點的完整資料，給景點詳細頁用。"""
    db = get_db()
    cursor = db.cursor()

    try:
        # %s 是佔位符，值另外用 tuple 傳，可以防止 SQL Injection
        # 單一元素的 tuple 結尾一定要有逗號，(attractionId,) 少了逗號就不是 tuple
        cursor.execute(
            "SELECT * FROM attractions WHERE id = %s",
            (attractionId,)
        )

        result = cursor.fetchone()   # 只拿一筆，沒找到會是 None

        # 找不到代表網址上的編號不存在
        if result is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "message": "景點編號不正確"
                }
            )

        # 圖片存在另一張表，用 attraction_id 關聯回來，所以要再查一次
        cursor.execute(
            "SELECT url FROM attraction_images WHERE attraction_id = %s",
            (attractionId,)
        )

        image_rows = cursor.fetchall()

        images = []

        for row in image_rows:
            images.append(row[0])

        # result 是一個 tuple，順序照資料表的欄位順序
        # 這裡把它整理成前端好用的字典，注意 transport 是第 9 欄（index 8）
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
        db.close()


@app.get("/api/attractions")
async def get_attractions(
    page: int = 0,
    keyword: str = None,
    category: str = None
):
    """
    回傳分頁的景點列表，可依關鍵字和分類篩選。
    三個參數都有預設值，代表前端可以不傳，例如 /api/attractions?page=1
    """
    db = get_db()
    cursor = db.cursor()

    per_page = 8   # 一頁固定 8 筆，規格要求

    try:
        # 篩選條件是動態的，使用者可能只給關鍵字、只給分類、兩個都給、都不給
        # 所以先蒐集成兩個清單，最後再組成 SQL
        conditions = []   # 放條件字串，例如 "category = %s"
        values = []       # 放對應的值，順序要跟 conditions 一致

        if keyword:
            # 名稱用模糊比對，捷運站名用完全比對，兩者符合其一即可
            conditions.append("(name LIKE %s OR mrt = %s)")
            values.append("%" + keyword + "%")   # LIKE 的 % 是萬用字元
            values.append(keyword)

        if category:
            conditions.append("category = %s")
            values.append(category)

        where_sql = ""

        # 有條件才加 WHERE，沒有的話 where_sql 保持空字串
        # join 會把多個條件用 AND 串起來
        if conditions:
            where_sql = " WHERE " + " AND ".join(conditions)

        # 先算符合條件的總筆數，等一下判斷還有沒有下一頁要用
        count_sql = "SELECT COUNT(*) FROM attractions" + where_sql

        cursor.execute(count_sql, tuple(values))
        total = cursor.fetchone()[0]   # COUNT 回傳的是 (數字,)，所以取 [0]

        # 真正撈資料的 SQL，多了分頁用的 LIMIT 和 OFFSET
        sql = "SELECT * FROM attractions" + where_sql
        sql = sql + " LIMIT %s OFFSET %s"

        # copy 是為了不動到原本的 values，因為上面 count 還用同一份
        query_values = values.copy()
        query_values.append(per_page)          # LIMIT：一次拿幾筆
        query_values.append(page * per_page)   # OFFSET：跳過前面幾筆

        cursor.execute(sql, tuple(query_values))
        results = cursor.fetchall()

        data = []

        for row in results:
            attraction_id = row[0]

            # 每個景點都要再查一次它的圖片
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

        # 判斷還有沒有下一頁：已經拿到的筆數還沒超過總數，就代表還有
        if (page + 1) * per_page < total:
            next_page = page + 1
        else:
            next_page = None   # 沒有下一頁，前端看到 null 就停止載入

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
        db.close()


@app.post("/api/user")
async def signup(data: SignUpInput):
    """註冊新會員。email 不可重複。"""
    # 資料已經被 FastAPI 依照 SignUpInput 拆好，用點的方式取值
    name = data.name
    email = data.email
    password = data.password

    db = get_db()
    cursor = db.cursor()

    try:
        # 先查這個 email 有沒有人用過
        cursor.execute("SELECT * FROM member WHERE email = %s", (email,))
        result = cursor.fetchone()

        # 查得到代表重複，註冊失敗
        # 註冊和登入對 result 的判斷方向相反，這裡容易寫錯
        if result is not None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "message": "重複的電子郵件"
                }
            )

        # 查不到代表可以用，寫進資料庫
        # id 不用填，建表時設了 AUTO_INCREMENT 會自動編號
        cursor.execute(
            "INSERT INTO member (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )
        db.commit()   # 有寫入動作一定要 commit，等於按下儲存。只有 SELECT 不用

        return {"ok": True}

    except Exception as error:
        print("錯誤內容：", error)   # debug 用，真正的錯誤會印在終端機
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "伺服器內部錯誤"
            }
        )

    finally:
        cursor.close()
        db.close()

@app.put("/api/user/auth")
async def signin(data: SignInInput):
    """驗證帳號密碼，正確就發一張 JWT token 給前端。"""
    email = data.email
    password = data.password

    db = get_db()
    cursor = db.cursor()

    try:
        # email 和密碼要同時符合才算登入成功
        cursor.execute(
            "SELECT * FROM member WHERE email = %s AND password = %s",
            (email, password)
        )
        result = cursor.fetchone()

        # 查不到代表帳號或密碼錯了
        if result is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "message": "帳號或密碼錯誤"
                }
            )

        # 要寫在票面上的內容，絕對不放密碼，因為 JWT 內容是公開可讀的
        # exp 是 PyJWT 認得的特定欄位，驗票時會自動檢查有沒有過期
        payload = {
            "id": result[0],
            "name": result[1],
            "email": result[2],
            "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
        }

        # 印票：把 payload 用 secret 簽章，產生一長串 token
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        return {"token": token}

    except Exception as error:
        print("錯誤內容：", error)
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "伺服器內部錯誤"
            }
        )

    finally:
        cursor.close()
        db.close()
        
        
@app.get("/api/user/auth")
async def get_current_user(request: Request):
    """驗證 header 裡的 token，回傳目前登入的會員資料。沒登入就回 null。"""
    try:
        # 從 header 取出 Authorization 這一行，沒有的話會是 None
        auth_header = request.headers.get("Authorization")

        # 完全沒帶 token，或格式不對，都當作沒登入
        if auth_header is None or not auth_header.startswith("Bearer "):
            return {"data": None}

        # 切掉開頭的 "Bearer " 七個字，剩下的才是 token
        token = auth_header.replace("Bearer ", "")

        # 驗票並解開，回傳的就是當初包進去的 payload
        # 驗不過（簽章錯、過期）會直接丟出錯誤，被下面的 except 接住
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        return {
            "data": {
                "id": payload["id"],
                "name": payload["name"],
                "email": payload["email"]
            }
        }

    except Exception as error:
        # token 無效或過期，一律當作沒登入
        return {"data": None}

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

app.mount("/static", StaticFiles(directory="static"), name="static")