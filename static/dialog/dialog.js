// 目前是否已登入，checkSignInStatus 跑完會更新它
let isSignedIn = false;

// 會用到的元素抓下來，存成變數
const authNav = document.querySelector("#auth-nav");           // 右上角登入/註冊
const backdrop = document.querySelector(".dialog-backdrop");   // 遮罩層
const closeBtn = document.querySelector(".dialog-close");      // 關閉按鈕
const signinForm = document.querySelector("#signin-form");     // 登入表單
const signupForm = document.querySelector("#signup-form");     // 註冊表單
const toSignup = document.querySelector("#to-signup");         // 點此註冊
const toSignin = document.querySelector("#to-signin");         // 點此登入

// 打開彈窗，並且回到登入表單的狀態
function openDialog() {
    backdrop.classList.remove("hidden");
    showSignin();
}

// 關閉彈窗
function closeDialog() {
    backdrop.classList.add("hidden");
}

// 切換到登入表單
function showSignin() {
    signinForm.classList.remove("hidden");
    signupForm.classList.add("hidden");
}

// 切換到註冊表單
function showSignup() {
    signupForm.classList.remove("hidden");
    signinForm.classList.add("hidden");
}

authNav.addEventListener("click", openDialog);
closeBtn.addEventListener("click", closeDialog);
toSignup.addEventListener("click", showSignup);
toSignin.addEventListener("click", showSignin);

// 註冊：把三個欄位送到後端，成功或失敗都在彈窗底部顯示訊息
async function signup() {
    const name = document.querySelector("#signup-name").value;
    const email = document.querySelector("#signup-email").value;
    const password = document.querySelector("#signup-password").value;
    const message = document.querySelector("#signup-message");

    const response = await fetch("/api/user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password })
    });

    const result = await response.json();

    if (result.ok) {
        message.textContent = "註冊成功，請登入系統";
        message.style.color = "#448899";
    } else {
        message.textContent = result.message;
        message.style.color = "#dd4444";
    }
}

document.querySelector("#signup-btn").addEventListener("click", signup);

// 登入：驗證成功就把 token 存進瀏覽器，然後重新整理頁面
async function signin() {
    const email = document.querySelector("#signin-email").value;
    const password = document.querySelector("#signin-password").value;
    const message = document.querySelector("#signin-message");

    const response = await fetch("/api/user/auth", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
    });

    const result = await response.json();

    if (result.token) {
        // 把 token 存進瀏覽器的 LocalStorage，之後每次要驗證身分都從這裡拿
        localStorage.setItem("token", result.token);
        // 重新整理，讓頁面重跑一次登入狀態檢查
        window.location.reload();
    } else {
        message.textContent = result.message;
        message.style.color = "#dd4444";
    }
}

document.querySelector("#signin-btn").addEventListener("click", signin);

// 登出：把 token 從瀏覽器刪掉，然後重新整理
function signout() {
    localStorage.removeItem("token");
    window.location.reload();
}

// 頁面一載入就檢查登入狀態，決定右上角要顯示什麼
async function checkSignInStatus() {
    const token = localStorage.getItem("token");

    // 有 token 才需要問後端
    if (token) {
        const response = await fetch("/api/user/auth", {
            headers: { "Authorization": "Bearer " + token }
        });

        const result = await response.json();

        // data 有東西代表已登入，把右上角換成登出系統
        if (result.data) {
            isSignedIn = true;
            authNav.textContent = "登出系統";
            authNav.removeEventListener("click", openDialog);
            authNav.addEventListener("click", signout);
        }
    }

    // 狀態確定了才顯示出來，避免閃過錯誤的文字
    authNav.style.visibility = "visible";
}


// 點「預定行程」：沒登入開彈窗，有登入跳到預定行程頁
const bookingNav = document.querySelector("#booking-nav");

bookingNav.addEventListener("click", function () {
    if (isSignedIn) {
        window.location.href = "/booking";
    } else {
        openDialog();
    }
});

checkSignInStatus();