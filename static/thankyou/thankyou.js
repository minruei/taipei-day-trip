// 從網址的 ?number=xxx 取出訂單編號
const params = new URLSearchParams(window.location.search);
const orderNumber = params.get("number");

// 沒有編號代表是直接打網址進來的，導回首頁
if (!orderNumber) {
    window.location.href = "/";
} else {
    document.querySelector("#order-number").textContent = orderNumber;
}