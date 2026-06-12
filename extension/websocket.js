export function updateElements(type) {
    if (type === 'ping') {
        document.getElementById("currentStatus").textContent = "Websocket active!";
        document.getElementById("uiBtn").disabled = false;

        const uiBtn = document.getElementById("uiBtn");

        uiBtn.addEventListener('click', function () {
            chrome.tabs.create({ url: "http://localhost:8080" });
        });
    }
}
