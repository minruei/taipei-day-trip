from fastapi import *
from fastapi.responses import FileResponse, JSONResponse
import mysql.connector
import os
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import jwt
import secrets
import requests
from datetime import datetime, timedelta, timezone
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers


load_dotenv()   # 讀取 .env 檔，把裡面的設定變成環境變數（例如資料庫密碼）

# MCP Server 提供給 AI Agent 使用，名稱依照規格設定
mcp = FastMCP("台北一日遊")

@mcp.tool(
    name="搜尋台北市景點",
    description="透過關鍵字和捷運站名搜尋台北市一日旅遊的景點"
)
def search_attractions(keyword: str) -> dict:
    """依照關鍵字或捷運站名搜尋景點，回傳景點清單。"""
    db = get_db()
    cursor = db.cursor()

    try:
        # 名稱用模糊比對，捷運站名用完全比對，兩者符合其一即可
        cursor.execute(
            """
            SELECT id, name, description
            FROM attractions
            WHERE name LIKE %s OR mrt = %s
            LIMIT 20
            """,
            ("%" + keyword + "%", keyword)
        )

        results = cursor.fetchall()

        data = []

        for row in results:
            data.append({
                "id": row[0],
                "name": row[1],
                "description": row[2]
            })

        return {"data": data}

    except Exception as error:
        print("搜尋景點失敗：", error)
        return {"error": True}

    finally:
        cursor.close()
        db.close()

@mcp.tool(
    name="預定景點導覽行程",
    description="根據景點編號、日期、時間、價格，預定一個景點導覽行程"
)
def add_to_cart(attraction_id: int, date: str, time: str, price: int) -> dict:
    """驗證 access token 後建立一筆預定行程。"""
    headers = get_http_headers(include_all=True)
    auth_header = headers.get("authorization", "")

    # 有些客戶端會自己拿掉 Bearer 前綴，兩種格式都接受
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
    else:
        token = auth_header

    if not token:
        return {"error": True}
    
    member_id = get_member_id_by_token(token)

    if member_id is None:
        return {"error": True}

    # 時段只接受 morning 和 afternoon，其他值一律拒絕
    correct_price = get_price_by_time(time)

    if correct_price is None:
        return {"error": True}

    # 價格由時段決定，跟送進來的值不一致就拒絕
    if price != correct_price:
        return {"error": True}

    # 日期必須是 YYYY-MM-DD 格式而且真的存在
    if not is_valid_date(date):
        return {"error": True}

    db = get_db()
    cursor = db.cursor()

    try:
        # 規格要求同時只能有一筆預訂，所以先把這個人舊的清掉
        cursor.execute(
            "DELETE FROM booking WHERE member_id = %s",
            (member_id,)
        )

        cursor.execute(
            """
            INSERT INTO booking (member_id, attraction_id, date, time, price)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (member_id, attraction_id, date, time, price)
        )

        db.commit()

        return {
            "ok": True,
            "message": "台北導覽行程，預定成功，請到 http://44.223.174.41:8000/booking 完成付款。"
        }

    except Exception as error:
        print("MCP 預定失敗：", error)
        return {"error": True}

    finally:
        cursor.close()
        db.close()

# 把 MCP Server 包成一個可以掛載的應用程式
mcp_app = mcp.http_app(path="/")

# 建立 FastAPI，並接手 MCP 的啟動流程，否則掛載後不會運作
app = FastAPI(lifespan=mcp_app.lifespan)

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

TAPPAY_PARTNER_KEY = os.getenv("TAPPAY_PARTNER_KEY")   # 從 .env 讀，能扣錢的鑰匙
TAPPAY_MERCHANT_ID = os.getenv("TAPPAY_MERCHANT_ID")   # 商家代號
TAPPAY_PAY_URL = "https://sandbox.tappaysdk.com/tpc/payment/pay-by-prime"

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

# 定義建立預定行程時前端要送來的資料格式
# 欄位名稱必須跟 API 規格一模一樣，attractionId 是駝峰式不是底線
class BookingInput(BaseModel):
    attractionId: int
    date: str
    time: str
    price: int

# Part 6 訂單用的資料格式，一層包一層，對應 Swagger 的巢狀結構
class Attraction(BaseModel):
    id: int
    name: str
    address: str
    image: str

class Trip(BaseModel):
    attraction: Attraction
    date: str
    time: str

class Contact(BaseModel):
    name: str
    email: str
    phone: str

class OrderInput(BaseModel):
    price: int
    trip: Trip
    contact: Contact

class OrderRequest(BaseModel):
    prime: str
    order: OrderInput


def get_member_id(request):
    """從 header 的 token 取出會員 id。沒有或無效就回 None。"""
    try:
        auth_header = request.headers.get("Authorization")

        if auth_header is None or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.replace("Bearer ", "")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        return payload["id"]

    except Exception:
        return None

def get_member_id_by_token(token):
    """用 MCP 的 access token 查出對應的會員 id。查不到回 None。"""
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute(
            "SELECT member_id FROM token WHERE token = %s",
            (token,)
        )

        result = cursor.fetchone()

        if result is None:
            return None

        return result[0]

    except Exception as error:
        print("查詢 token 失敗：", error)
        return None

    finally:
        cursor.close()
        db.close()

def get_price_by_time(time):
    """依照時段回傳導覽費用。時段不是morning或afternoon回 None。"""
    if time == "morning":
        return 2000

    if time == "afternoon":
        return 2500

    return None

def is_valid_date(date):
    """檢查日期是不是 YYYY-MM-DD 格式而且真的存在。"""
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True

    except Exception:
        return False

def pay_by_prime(prime, amount, details, contact):
    """
    帶著 prime 去跟 TapPay 請款。
    回傳 (status, message, rec_trade_id)，status 是 0 代表付款成功。
    """
    headers = {
        "Content-Type": "application/json",
        "x-api-key": TAPPAY_PARTNER_KEY
    }

    body = {
        "prime": prime,
        "partner_key": TAPPAY_PARTNER_KEY,
        "merchant_id": TAPPAY_MERCHANT_ID,
        "amount": amount,
        "details": details,
        "cardholder": {
            "phone_number": contact.phone,
            "name": contact.name,
            "email": contact.email
        }
    }

    try:
        response = requests.post(
            TAPPAY_PAY_URL,
            headers=headers,
            json=body,
            timeout=30   # 對方沒回應時最多等 30 秒
        )
        result = response.json()

        print("TapPay 回應：", result)   # 完整回應留著，查錯誤代碼時會用到

        return (
            result.get("status"),
            result.get("msg"),
            result.get("rec_trade_id")
        )

    except Exception as error:
        print("TapPay 連線失敗：", error)
        # 連都連不上，回一個不是 0 的值代表失敗
        return (-1, "無法連線到金流服務", None)


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


@app.post("/api/booking")
async def create_booking(request: Request, data: BookingInput):
    """
    建立預定行程。
    這支同時需要 header 的 token（你是誰）和 body 的內容（你要訂什麼），
    所以 request 和 data 兩個參數都要。
    """
    # 沒登入就直接擋掉，寫在這裡是為了不必要時不用碰資料庫
    member_id = get_member_id(request)

    if member_id is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "message": "未登入系統，拒絕存取"
            }
        )

    db = get_db()
    cursor = db.cursor()

    try:
        # 規格要求同時只能有一筆預訂，所以先把這個人舊的清掉
        cursor.execute(
            "DELETE FROM booking WHERE member_id = %s",
            (member_id,)
        )

        # 再寫入新的一筆
        # 左邊是資料表的欄位名（底線），右邊 data 是前端來的欄位名（駝峰）
        cursor.execute(
            """
            INSERT INTO booking (member_id, attraction_id, date, time, price)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (member_id, data.attractionId, data.date, data.time, data.price)
        )

        # 刪除和新增共用同一次 commit，要嘛都生效、要嘛都不算
        db.commit()

        return {"ok": True}

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


@app.get("/api/booking")
async def get_booking(request: Request):
    """取得目前登入者的預定行程。沒有預訂就回 null。"""
    member_id = get_member_id(request)

    if member_id is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "message": "未登入系統，拒絕存取"
            }
        )

    db = get_db()
    cursor = db.cursor()

    try:
        # 用 JOIN 一次把 booking 和 attractions 的資料湊在一起
        cursor.execute(
            """
            SELECT b.date, b.time, b.price, a.id, a.name, a.address
            FROM booking b
            JOIN attractions a ON b.attraction_id = a.id
            WHERE b.member_id = %s
            """,
            (member_id,)
        )

        result = cursor.fetchone()

        # 沒有預訂不算錯誤，規格要求好好回一個 null
        if result is None:
            return {"data": None}

        # 圖片在另一張表，而且一個景點有很多張，規格只要一張
        cursor.execute(
            "SELECT url FROM attraction_images WHERE attraction_id = %s",
            (result[3],)
        )

        image_rows = cursor.fetchall()   # 拿全部，避免殘留資料卡住 cursor

        # 規格只要一張圖，取第一張。萬一沒有圖就給空字串
        if len(image_rows) == 0:
            image = ""
        else:
            image = image_rows[0][0]

        # result 的順序照 SELECT 寫的順序，不是資料表的順序
        return {
            "data": {
                "attraction": {
                    "id": result[3],
                    "name": result[4],
                    "address": result[5],
                    "image": image
                },
                "date": str(result[0]),
                "time": result[1],
                "price": result[2]
            }
        }

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


@app.delete("/api/booking")
async def delete_booking(request: Request):
    """刪除目前登入者的預定行程。"""
    member_id = get_member_id(request)

    if member_id is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "message": "未登入系統，拒絕存取"
            }
        )

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute(
            "DELETE FROM booking WHERE member_id = %s",
            (member_id,)
        )
        db.commit()   # 刪除是寫入動作，一定要 commit

        return {"ok": True}

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


@app.post("/api/orders")
async def create_order(request: Request, data: OrderRequest):
    """建立訂單並完成付款。付款失敗也回 200，用 payment.status 表達結果。"""
    member_id = get_member_id(request)

    if member_id is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "message": "未登入系統，拒絕存取"
            }
        )

    # 訂單編號用下單當下的時間，格式 YYYYMMDDHHMMSS
    number = datetime.now().strftime("%Y%m%d%H%M%S")

    db = get_db()
    cursor = db.cursor()

    try:
        # 訂單先建起來，status 給 0 表示還沒付款
        # 資料是巢狀的，所以取值要一層一層走進去
        cursor.execute(
            """
            INSERT INTO `order`
            (number, member_id, attraction_id, date, time, price,
             contact_name, contact_email, contact_phone, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """,
            (
                number,
                member_id,
                data.order.trip.attraction.id,
                data.order.trip.date,
                data.order.trip.time,
                data.order.price,
                data.order.contact.name,
                data.order.contact.email,
                data.order.contact.phone
            )
        )

        # 訂單建好了，帶著 prime 去請款
        payment_status, payment_message, rec_trade_id = pay_by_prime(
            data.prime,
            data.order.price,
            data.order.trip.attraction.name,
            data.order.contact
        )

        # 付款成功才把訂單改成已付款，並清掉購物車那筆預訂
        # 失敗的話兩件都不做，讓使用者可以重刷
        if payment_status == 0:
            cursor.execute(
                "UPDATE `order` SET status = 1 WHERE number = %s",
                (number,)
            )
            cursor.execute(
                "DELETE FROM booking WHERE member_id = %s",
                (member_id,)
            )

        # 不管成功或失敗都留一筆付款紀錄
        cursor.execute(
            """
            INSERT INTO payment (order_number, status, message, rec_trade_id)
            VALUES (%s, %s, %s, %s)
            """,
            (number, payment_status, payment_message, rec_trade_id)
        )

        # 建單、更新、刪除、付款紀錄共用同一次 commit
        db.commit()

        return {
            "data": {
                "number": number,
                "payment": {
                    "status": payment_status,
                    "message": payment_message
                }
            }
        }

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


@app.get("/api/order/{orderNumber}")
async def get_order(request: Request, orderNumber: str):
    """依訂單編號回傳訂單資訊。查不到就回 null。"""
    member_id = get_member_id(request)

    if member_id is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "message": "未登入系統，拒絕存取"
            }
        )

    db = get_db()
    cursor = db.cursor()

    try:
        # 加上 member_id 條件，別人的訂單編號查不到
        cursor.execute(
            """
            SELECT o.number, o.price, o.date, o.time, o.status,
                   o.contact_name, o.contact_email, o.contact_phone,
                   a.id, a.name, a.address
            FROM `order` o
            JOIN attractions a ON o.attraction_id = a.id
            WHERE o.number = %s AND o.member_id = %s
            """,
            (orderNumber, member_id)
        )

        result = cursor.fetchone()

        # 查不到不算錯誤，規格要求回 null
        if result is None:
            return {"data": None}

        # 圖片在另一張表，取第一張
        cursor.execute(
            "SELECT url FROM attraction_images WHERE attraction_id = %s",
            (result[8],)
        )

        image_rows = cursor.fetchall()

        if len(image_rows) == 0:
            image = ""
        else:
            image = image_rows[0][0]

        return {
            "data": {
                "number": result[0],
                "price": result[1],
                "trip": {
                    "attraction": {
                        "id": result[8],
                        "name": result[9],
                        "address": result[10],
                        "image": image
                    },
                    "date": str(result[2]),
                    "time": result[3]
                },
                "contact": {
                    "name": result[5],
                    "email": result[6],
                    "phone": result[7]
                },
                "status": result[4]
            }
        }

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
        
        
@app.put("/api/token")
async def create_token(request: Request):
    """為目前登入的會員產生一組新的 access token，取代舊的那一組。"""
    member_id = get_member_id(request)

    if member_id is None:
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "message": "未登入系統，拒絕存取"
            }
        )

    # 產生 32 個位元組的隨機值，轉成 64 個字元的十六進位字串
    new_token = secrets.token_hex(32)

    db = get_db()
    cursor = db.cursor()

    try:
        # 一個會員只能有一組有效的 token，先清掉舊的那筆
        cursor.execute(
            "DELETE FROM token WHERE member_id = %s",
            (member_id,)
        )

        cursor.execute(
            "INSERT INTO token (member_id, token) VALUES (%s, %s)",
            (member_id, new_token)
        )

        # 刪除和新增共用同一次 commit，要嘛都生效、要嘛都不算
        db.commit()

        return {"ok": True, "token": new_token}

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


@app.get("/member", include_in_schema=False)
async def member(request: Request):
    return FileResponse("./static/member.html", media_type="text/html")


app.mount("/static", StaticFiles(directory="static"), name="static")

# 把 MCP Server 掛在 /mcp 位置，給 AI Agent 使用
app.mount("/mcp", mcp_app)

