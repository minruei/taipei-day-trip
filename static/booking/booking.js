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

document.querySelector("#delete-btn").addEventListener("click", deleteBooking);

initBookingPage();