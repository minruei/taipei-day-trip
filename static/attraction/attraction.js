let currentImageIndex = 0;
let currentImages = [];
let currentPrice = 2000;   // 目前選的價格，預設上半天

async function loadAttraction() {
    // 從網址路徑挖出景點 id（例如 /attraction/14 -> "14"）
    const parts = window.location.pathname.split("/");
    const attractionId = parts.at(-1);

    // 帶著 id 去問伺服器要這個景點的資料
    const response = await fetch(`/api/attraction/${attractionId}`);
    const result = await response.json();
    const attraction = result.data;

    // 景點名稱
    document.querySelector(".attraction-name").textContent = attraction.name;

    // 分類 + 捷運站，中間用 at 連接
    document.querySelector(".attraction-category-mrt").textContent = `${attraction.category} at ${attraction.mrt}`;

    // 景點描述
    document.querySelector(".attraction-description").textContent = attraction.description;

    // 景點地址
    document.querySelector(".attraction-address").textContent = attraction.address;

    // 交通方式
    document.querySelector(".attraction-transport").textContent = attraction.transport;

    // 把景點的圖片陣列存進輪播用的變數，然後顯示第一張
    currentImages = attraction.images;
    showImage();
}

function showImage() {
    const carouselImg = document.querySelector(".carousel-img");
    carouselImg.src = currentImages[currentImageIndex];
    showIndicators();
}

function showIndicators() {
    const indicatorBar = document.querySelector(".indicator-bar");
    indicatorBar.innerHTML = "";  // 先清空，避免舊的方塊疊加

    for (let i = 0; i < currentImages.length; i++) {
        const dot = document.createElement("div");
        dot.className = "indicator-dot";

        // 如果這一個的索引剛好等於現在顯示的那張，就加上 active 樣式
        if (i === currentImageIndex) {
            dot.classList.add("active");
        }

        indicatorBar.appendChild(dot);
    }
}

function nextImage() {
    if (currentImageIndex === currentImages.length - 1) {
        currentImageIndex = 0;
    } else {
        currentImageIndex = currentImageIndex + 1;
    }
    showImage();
}

function prevImage() {
    if (currentImageIndex === 0) {
        currentImageIndex = currentImages.length - 1;
    } else {
        currentImageIndex = currentImageIndex - 1;
    }
    showImage();
}

// 點「開始預約行程」：沒登入開彈窗，有登入就建立預訂
async function createBooking() {
    // 沒登入就開彈窗，直接結束
    if (!isSignedIn) {
        openDialog();
        return;
    }

    // 把要送的資料撈出來
    const parts = window.location.pathname.split("/");
    const attractionId = parts.at(-1);
    const date = document.querySelector("#booking-date").value;
    const checkedTime = document.querySelector('input[name="time"]:checked');
    const price = currentPrice;

    // 日期或時段沒填就擋下來
    if (!date || !checkedTime) {
        alert("請選擇日期和時間");
        return;
    }

    const time = checkedTime.value;

    // 帶著 token 送出預訂
    const token = localStorage.getItem("token");

    const response = await fetch("/api/booking", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token
        },
        body: JSON.stringify({ attractionId, date, time, price })
    });

    const result = await response.json();

    // 成功就跳到預定行程頁
    if (result.ok) {
        window.location.href = "/booking";
    }
}

// 抓所有時段選項的 radio 按鈕
const timeRadios = document.querySelectorAll('input[name="time"]');

// 每個 radio 都綁上點擊事件：點了就換價格文字
timeRadios.forEach(function (radio) {
    radio.addEventListener("click", function () {
        if (this.value === "morning") {
            currentPrice = 2000;
            document.querySelector(".price-value").textContent = "NTD 2000";
        } else {
            currentPrice = 2500;
            document.querySelector(".price-value").textContent = "NTD 2500";
        }
    });
});

document.querySelector(".carousel-arrow-right").addEventListener("click", nextImage);
document.querySelector(".carousel-arrow-left").addEventListener("click", prevImage);
document.querySelector(".booking-btn").addEventListener("click", createBooking);

loadAttraction();