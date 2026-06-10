const websocket = new WebSocket("ws://localhost:8765/");

function connectWebSocket(websocket) {
    return new Promise((resolve, reject) => {
        websocket.onopen = () => {
            console.log("Connected to WebSocket successfully!")

            const hello = {type: "hello", message: "ping"};

            websocket.send(JSON.stringify(hello));
        };

        websocket.onerror = (error) => {
            console.error("WebSocket connection error:", error);
            reject(error);
        };
    });
}

websocket.addEventListener("message", ({ event }) => {
    const response = JSON.parse(event);

    console.log(response)

    if (response.type === "hello") {
        console.log("Received hello!")
        document.querySelector(".ping").textContent = "Websocket active!"
    }
})

connectWebSocket(websocket)