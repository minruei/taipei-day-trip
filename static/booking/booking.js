let currentOrder = null;

// App ID 和 App Key 只能用來換 prime，不能扣錢，可以放前端
const TAPPAY_APP_ID = 171156;
const TAPPAY_APP_KEY = "app_S9ImGvD75riqGwafj4kh5wFZt1TD9pMAACssqKrmKxI503fudsFuFJQuWt2V";

// 第三個參數指定測試環境
TPDirect.setupSDK(TAPPAY_APP_ID, TAPPAY_APP_KEY, "sandbox");

// TapPay 會在這三個 div 裡面各塞一個 iframe，卡號不會經過頁面
// styles 是傳給 iframe 內部用的，跟外面的CSS無關
TPDirect.card.setup({
    fields: {
        number: {
            element: "#card-number",
            placeholder: "**** **** **** ****"
        },
        expirationDate: {
            element: "#card-expiry",
            placeholder: "MM / YY"
        },
        ccv: {
            element: "#card-cvv",
            placeholder: "***"
        }
    },
    styles: {
        "input": {
            "color": "#666666",
            "font-size": "16px"
        }
    }
});

// 進頁面先檢查登入狀態，沒登入就踢回首頁
async function initBookingPage() {
    const token = localStorage.getItem("token");

    // 連 token 都沒有，一定沒登入
    if (!token) {
        window.location.href = "/";
        return;
    }

    const response = await fetch("/api/user/auth", {
        headers: { "Authorization": "Bearer " + token }
    });

    const result = await response.json();

    // token 過期或無效，也算沒登入
    if (!result.data) {
        window.location.href = "/";
        return;
    }

    // 到這裡代表確定有登入，把名字填進 headline
    document.querySelector("#member-name").textContent = result.data.name;

    // 接著去拿預訂資料
    loadBooking();
}

// 抓預訂資料，有就渲染，沒有就顯示 empty state
async function loadBooking() {
    const token = localStorage.getItem("token");

    const response = await fetch("/api/booking", {
        headers: { "Authorization": "Bearer " + token }
    });

    const result = await response.json();

    // 沒有預訂資料，切換到 empty state
    if (!result.data) {
        document.querySelector("#booking-content").classList.add("hidden");
        document.querySelector("#empty-state").classList.remove("hidden");
        return;
    }

    // 有資料，把每一格填進去
    const booking = result.data;
    const attraction = booking.attraction;

    // 畫面上的字是給人看的，送 API 要用原始資料，另外存一份
    currentOrder = {
        price: booking.price,
        attraction: attraction,
        date: booking.date,
        time: booking.time
    };

    document.querySelector("#attraction-image").src = attraction.image;
    document.querySelector("#attraction-name").textContent = attraction.name;
    document.querySelector("#attraction-address").textContent = attraction.address;
    document.querySelector("#booking-date").textContent = booking.date;
    document.querySelector("#booking-time").textContent = booking.time === "morning" ? "早上 9 點到中午 12 點" : "下午 2 點到晚上 7 點";
    document.querySelector("#booking-price").textContent = `新台幣 ${booking.price} 元`;
    document.querySelector("#total-price").textContent = booking.price;
}

// 刪除預訂：打 DELETE API，成功後重新整理頁面
async function deleteBooking() {
    const token = localStorage.getItem("token");

    const response = await fetch("/api/booking", {
        method: "DELETE",
        headers: { "Authorization": "Bearer " + token }
    });

    const result = await response.json();

    if (result.ok) {
        window.location.reload();
    }
}

// 按下付款：先跟 TapPay 換 prime，拿到之後再送去後端建訂單
async function confirmOrder() {
    const name = document.querySelector("#contact-name").value;
    const email = document.querySelector("#contact-email").value;
    const phone = document.querySelector("#contact-phone").value;

    if (!name || !email || !phone) {
        alert("請填寫完整的聯絡資訊");
        return;
    }

    // 三個欄位都合法才拿得到 prime
    const cardStatus = TPDirect.card.getTappayFieldsStatus();

    if (!cardStatus.canGetPrime) {
        alert("請填寫正確的信用卡資訊");
        return;
    }

    // 結果由 callback 送回來
    TPDirect.card.getPrime(async function (result) {
        if (result.status !== 0) {
            alert("無法取得付款授權：" + result.msg);
            return;
        }

        const prime = result.card.prime;
        const token = localStorage.getItem("token");

        const response = await fetch("/api/orders", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                prime: prime,
                order: {
                    price: currentOrder.price,
                    trip: {
                        attraction: currentOrder.attraction,
                        date: currentOrder.date,
                        time: currentOrder.time
                    },
                    contact: {
                        name: name,
                        email: email,
                        phone: phone
                    }
                }
            })
        });

        const data = await response.json();

        if (data.error) {
            alert(data.message);
            return;
        }

        // 付款失敗也會拿到訂單編號，一樣跳轉，由 thankyou 頁顯示結果
        window.location.href = "/thankyou?number=" + data.data.number;
    });
}

document.querySelector("#delete-btn").addEventListener("click", deleteBooking);
document.querySelector("#confirm-btn").addEventListener("click", confirmOrder);

initBookingPage();