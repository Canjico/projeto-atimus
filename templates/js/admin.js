const token = localStorage.getItem("token");
const status = document.getElementById("status");

if (!token) {
    window.location.href = "admin_login.html";
}

fetch("http://127.0.0.1:8000/admin/protected", {
    headers: {
        "Authorization": "Bearer " + token
    }
})
.then(res => {
    if (!res.ok) {
        throw new Error("Sem acesso");
    }
    return res.json();
})
.then(data => {
    status.innerText = data.msg;
})
.catch(() => {
    localStorage.removeItem("token");
    window.location.href = "admin_login.html";
});

document.getElementById("logout").addEventListener("click", () => {
    localStorage.removeItem("token");
    window.location.href = "admin_login.html";
});
