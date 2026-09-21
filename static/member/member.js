const generateButton = document.querySelector("#generate-button");
const tokenDisplay = document.querySelector("#token-display");

generateButton.addEventListener("click", async function () {
    const response = await fetch("/api/token", {
        method: "PUT",
        headers: {
            "Authorization": "Bearer " + localStorage.getItem("token")
        }
    });

    const result = await response.json();

    if (result.error) {
        tokenDisplay.textContent = "請先登入";
        return;
    }

    tokenDisplay.textContent = result.token;
});

const signoutButton = document.querySelector("#signout-button");

signoutButton.addEventListener("click", function () {
    localStorage.removeItem("token");
    window.location.href = "/";

    
});

const greeting = document.querySelector("#greeting");

async function showGreeting() {
    const token = localStorage.getItem("token");

    if (!token) {
        return;
    }

    const response = await fetch("/api/user/auth", {
        headers: { "Authorization": "Bearer " + token }
    });

    const result = await response.json();

    if (result.data) {
        greeting.textContent = "您好，" + result.data.name + "：";
    }
}

showGreeting();

const copyButton = document.querySelector("#copy-button");

copyButton.addEventListener("click", async function () {
    const text = tokenDisplay.textContent;

    if (text === "尚未產生" || text === "請先登入") {
        return;
    }

    await navigator.clipboard.writeText(text);

    // 複製成功後短暫改變按鈕文字，讓使用者知道有反應
    copyButton.textContent = "已複製";

    setTimeout(function () {
        copyButton.textContent = "複製";
    }, 1500);
});