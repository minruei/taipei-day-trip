let currentPage = 0;
let isLoading = false;

async function loadAttractions() {
    // 正在載入中則中止，避免重複發出請求
    if (isLoading) {
        return;
    }

    // currentPage 為 null 表示沒有下一頁，中止
    if (currentPage === null) {
        return;
    }

    // 設定載入狀態為 true
    isLoading = true;

    const response = await fetch(`/api/attractions?page=${currentPage}`);
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

    // 把 img、name、info 裝進 card
    card.appendChild(img);
    card.appendChild(name);
    card.appendChild(info);

    return card;
}

loadAttractions();

// 建立 IntersectionObserver，當目標進入畫面時觸發
const observer = new IntersectionObserver((entries) => {
    // 判斷目標是否進入畫面，是的話載入下一頁
    if (entries[0].isIntersecting) {
        loadAttractions();
    }
});

// 選取 sentinel 元素，讓 observer 開始監看
const sentinel = document.querySelector(".sentinel");
observer.observe(sentinel);