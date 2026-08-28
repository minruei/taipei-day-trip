let currentPage = 0;
let isLoading = false;
let currentCategory = "";
let currentKeyword = "";

// sentinel 移到最上面，因為 loadAttractions 裡面要用到它
const sentinel = document.querySelector(".sentinel");

async function loadAttractions() {
    // 正在「載入中」則中止，避免重複發出請求
    if (isLoading) {
        return;
    }

    // currentPage 為 null 表示沒有下一頁，中止
    if (currentPage === null) {
        return;
    }

    // 設定載入狀態為 true
    isLoading = true;

    // 帶上分類和關鍵字條件去查詢
    const response = await fetch(`/api/attractions?page=${currentPage}&keyword=${currentKeyword}&category=${currentCategory}`);
    const result = await response.json();

    const attractions = result.data;

    const list = document.querySelector(".attraction-list");

    for (const attraction of attractions) {
        const card = createCard(attraction);
        list.appendChild(card);
    }

    currentPage = result.nextPage;

    // 載入完成，設定載入狀態為 false
    isLoading = false;

    // 載完之後檢查 sentinel 是否還在畫面內
    // 若是，代表內容還不夠長，繼續載下一頁
    if (sentinel.getBoundingClientRect().top < window.innerHeight) {
        loadAttractions();
    }
}

function createCard(attraction) {
    // 最外層的 div.card
    const card = document.createElement("div");
    card.className = "card";

    // 圖片
    const img = document.createElement("img");
    img.className = "card-img";
    img.src = attraction.images[0];
    img.alt = attraction.name;

    //做名稱
    const name = document.createElement("h3");
    name.className = "card-name";
    name.textContent = attraction.name;

    // 下面那條資訊列（捷運 + 分類）
    const info = document.createElement("div");
    info.className = "card-info";

    const mrt = document.createElement("span");
    mrt.className = "card-mrt";
    mrt.textContent = attraction.mrt;

    const category = document.createElement("span");
    category.className = "card-category";
    category.textContent = attraction.category;

    // 把 mrt 和 category 裝進 info
    info.appendChild(mrt);
    info.appendChild(category);

    // 圖片容器：包住圖片和景點名，當作景點名的定位基準
    const imgWrapper = document.createElement("div");
    imgWrapper.className = "card-img-wrapper";

    // 圖片和景點名裝進容器
    imgWrapper.appendChild(img);
    imgWrapper.appendChild(name);

    // 容器和資訊列裝進 card
    card.appendChild(imgWrapper);
    card.appendChild(info);

    card.addEventListener("click", function () {
        window.location.href = `/attraction/${attraction.id}`;
    });

    return card;

}

// 執行搜尋：重置狀態、清空清單、重新載入
function searchAttractions() {
    currentPage = 0;
    isLoading = false;

    const list = document.querySelector(".attraction-list");
    list.innerHTML = "";

    loadAttractions();
}

loadAttractions();

// 建立 IntersectionObserver，當目標進入畫面時觸發
const observer = new IntersectionObserver((entries) => {
    // 判斷目標是否進入畫面，是的話載入下一頁
    if (entries[0].isIntersecting) {
        loadAttractions();
    }
});

// 讓 observer 開始監看 sentinel
observer.observe(sentinel);

async function loadCategories() {
    const response = await fetch("/api/categories");
    const result = await response.json();

    const categories = result.data;

    // 抓面板容器（放迴圈外，只抓一次）
    const panel = document.querySelector(".category-panel");

    // 每個分類做成一個選項，放進面板
    for (const category of categories) {
        const item = document.createElement("div");
        item.className = "category-item";
        item.textContent = category;

        // 點這個分類時，記住它、更新按鈕文字、關閉面板
        item.addEventListener("click", function () {
            currentCategory = category;
            categoryBtn.textContent = category + " ▼";
            categoryPanel.style.display = "none";
        });

        panel.appendChild(item);
    }
}

loadCategories();

// 點分類按鈕，切換面板顯示或隱藏
const categoryBtn = document.querySelector(".category-btn");
const categoryPanel = document.querySelector(".category-panel");

categoryBtn.addEventListener("click", function () {
    if (categoryPanel.style.display === "grid") {
        categoryPanel.style.display = "none";
    } else {
        categoryPanel.style.display = "grid";
    }
});

// 點搜尋按鈕，讀取關鍵字並執行搜尋
const searchBtn = document.querySelector(".search-btn");
const searchInput = document.querySelector(".search-input");

searchBtn.addEventListener("click", function (event) {
    event.preventDefault();
    currentKeyword = searchInput.value;
    searchAttractions();
});

// 在搜尋框按 Enter 也能搜尋
searchInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.isComposing) {
        currentKeyword = searchInput.value;
        searchAttractions();
    }
});

// 抓 MRT 列表容器和左右箭頭（放最上面，讓下面共用）
const mrtList = document.querySelector(".mrt-list");
const arrowLeft = document.querySelector(".mrt-arrow-left");
const arrowRight = document.querySelector(".mrt-arrow-right");

async function loadMrts() {
    const response = await fetch("/api/mrts");
    const result = await response.json();

    const mrts = result.data;

    // 每個站名做成一個 li，放進列表
    for (const mrt of mrts) {
        const item = document.createElement("li");
        item.textContent = mrt;

        // 點站名：填進搜尋框、當關鍵字、執行搜尋
        item.addEventListener("click", function () {
            searchInput.value = mrt;
            currentKeyword = mrt;
            searchAttractions();
        });

        mrtList.appendChild(item);
    }
}

loadMrts();

// 點右箭頭，列表往左捲
arrowRight.addEventListener("click", function () {
    mrtList.scrollLeft = mrtList.scrollLeft + 200;
});

// 點左箭頭，列表往右捲
arrowLeft.addEventListener("click", function () {
    mrtList.scrollLeft = mrtList.scrollLeft - 200;
});