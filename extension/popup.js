document.addEventListener("DOMContentLoaded", () => {
    chrome.runtime.sendMessage({recipient: "service-worker", request: "ping"}, (response) => {
        console.log("Popup script received message: ", response);

        document.getElementById("currentStatus").textContent = "Websocket active!";
        document.getElementById("uiBtn").disabled = false;

        const uiBtn = document.getElementById("uiBtn");

        uiBtn.addEventListener('click', function () { 
            chrome.tabs.create({ url: "http://localhost:8080" });
        });
    });
});