document.addEventListener("DOMContentLoaded", () => {
    chrome.runtime.sendMessage({recipient: "service-worker", request: "ping"}, (response) => {
        console.log("Popup script received message: ", response);

        if (response.request === 'pong') {
            document.getElementById("currentStatus").textContent = "Websocket active!";
            document.getElementById("uiBtn").disabled = false;
            document.getElementById("clear").disabled = false;

            const uiBtn = document.getElementById("uiBtn");
            const clearBtn = document.getElementById("clear");

            uiBtn.addEventListener('click', function () { 
                chrome.tabs.create({ url: "http://localhost:8080" });
            });

            clearBtn.addEventListener('click', function () { 
                chrome.runtime.sendMessage({recipient: "service-worker", request: "clear"});
            });
        }
    });
});