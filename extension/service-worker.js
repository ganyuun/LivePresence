import { updateElements } from "./websocket";

const websocket = new WebSocket("ws://localhost:8765/");
let presences = [];
let acceptedURLs = [];
let tabDict = [];
let websocketActive = false;

chrome.tabs.onActivated.addListener(getTabs);

async function getTabs(activeInfo) {
    try {
        await chrome.tabs.query({ currentWindow: true })

        tabDict = []

        if (tabs.length > 0) { tabs.foreach( (tab) => tabDict.push({'title': tab.title, 'url': tab.url}) ); }

        console.log("tabDict:", tabDict)
    } catch (error) { console.error("Error fetching tabs") }
}

function connectWebSocket(websocket) {
    return new Promise((resolve, reject) => {
        websocket.onopen = () => {
            console.log("Connected to WebSocket successfully!")

            websocket.send(JSON.stringify({type: "hello", message: "ping"}));

            websocket.send(JSON.stringify({type: "enabledPresences"}))
        };

        websocket.onerror = (error) => {
            console.error("WebSocket connection error:", error);
            reject(error);
        };
    });
}

websocket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data)

    if (msg.type === "hello") {
        websocketActive = true;
        console.log("Received hello:", msg);
        updateElements('ping');
    }

    if (msg.type === "enabledPresences") {
        presences = (msg.message).map((x) => x.toLowerCase());
        acceptedURLs = presences.map((presence) => `*://${presence}*`);

        console.log("Enabled presences:", presences);
        console.log(acceptedURLs);
    }
});

connectWebSocket(websocket)