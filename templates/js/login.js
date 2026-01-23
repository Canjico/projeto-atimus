const form = document.getElementById("loginForm");
const msg = document.getElementById("msg");

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById("email").value;
    const senha = document.getElementById("senha").value;

    try {
        const response = await fetch("http://127.0.0.1:8000/admin/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ email, senha })
        });

        if (!response.ok) {
            msg.innerText = "Login inválido";
            return;
        }

        const data = await response.json();

        // salva token
        localStorage.setItem("token", data.access_token);

        msg.innerText = "Login bem-sucedido!";

        // redireciona
        window.location.href = "admin_dashboard.html";

    } catch (err) {
        msg.innerText = "Erro ao conectar com a API";
    }
});
