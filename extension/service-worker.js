let websocket = new WebSocket("ws://localhost:8765/");
let presences = [];
let tabList = [];
let lastMessage = [];
let debounceTimer;

connectWebSocket(websocket);

function connectWebSocket(websocket) {
    return new Promise((resolve, reject) => {
        websocket.onopen = () => {
            resolve("Connected to WebSocket successfully!");
            addListeners(websocket);

            websocket.send(JSON.stringify({type: "hello", message: "ping"}));
            websocket.send(JSON.stringify({type: "enabledPresences"}));

            const keepAliveId = setInterval( () => { 
                if (websocket.readyState === WebSocket.OPEN) {
                    websocket.send(JSON.stringify({type: "hello", message: "keep alive"})); 
                }
            }, 20000 );
        };

        websocket.onerror = (error) => {
            console.error("WebSocket connection error:", error);
            reject(error);
        };
    });
}

function addListeners(websocket) {
    chrome.tabs.onUpdated.addListener(() => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => { 
            const tabs = await getTabs();
            if (tabs !== 'duplicate') {
                console.log("Tabs sent (duplicates = false):", tabs);
                websocket.send( JSON.stringify( {type: "tabs", message: tabs} ));
            }
        }, 1000);
    });

    chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
        if (removeInfo.isWindowClosing === true) { websocket.send( JSON.stringify( {type: "tabs", message: []} )); }
        else {
            if (tabList.length > 0) {
                const filterIndex = tabList.findIndex(tab => tabId === tab.tabId);

                if (filterIndex !== -1) {
                    tabList.splice(filterIndex, 1);
                    console.log("Updated tabList:", tabList);
                    websocket.send( JSON.stringify( {type: "tabs", message: tabList} ));
                }
                else { console.log("tabList unchanged."); }
            }
            else { console.log("tabList unchanged."); }
        }
    });

    websocket.addEventListener("message", (event) => {
        const msg = JSON.parse(event.data)

        if (msg.type === "hello") {
            if ( !msg.message.includes('silent') ) { console.log("Received hello:", msg); }
        }

        if (msg.type === "enabledPresences") {
            const response = msg.message
            const hostNames = response.map( (dict) => dict.hostName );

            presences = {
                acceptedURLs: hostNames.map( (host) => `*://*.${host}/*` ), 
                videoType: response.map( dict => {if (dict.type === 'video') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
                musicType: response.map( dict => {if (dict.type === 'music') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
                streamType: response.map( dict => {if (dict.type === 'stream') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
                playingType: response.map( dict => {if (dict.type === 'playing') { return dict.name.toLowerCase() } else {return 'N/A'} } )
            };

            presences.videoType = (presences.videoType).filter( presenceName => presenceName !== "N/A" );
            presences.musicType = (presences.musicType).filter( presenceName => presenceName !== "N/A" );
            presences.streamType = (presences.musicType).filter( presenceName => presenceName !== "N/A" );
            presences.playingType = (presences.playingType).filter( presenceName => presenceName !== "N/A" );
        }

        if (msg.type === 'tabs') {
            clearTimeout(debounceTimer);

            debounceTimer = setTimeout(async () => { 
                const tabs = await getTabs(true);
                console.log("Tabs sent (duplicates = true):", tabs);
                websocket.send( JSON.stringify( {type: "tabs", message: tabs} ));
            }, 1000);
        }

        if (msg.type === 'exit') {
            console.log('System tray icon exiting.')
            websocket.send( JSON.stringify({type: "exit", message: "exit"}) )
        }
    });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    switch (msg.request) {
        case 'ping':
            try {
                websocket.send(JSON.stringify({type: "hello", message: "from extension popup"}));
                sendResponse({recipient: "popup.js", request: "pong"});
            } catch (error) {
                console.error("Unable to send message:", error)
            }
        case 'clear':
            try {
                websocket.send( JSON.stringify({type: "clear", message: "clear"}) );
                console.log("Sent message to Python script to clear status:", {type: "clear", message: "clear"})
            }
            catch (error) { console.error("Unable to send message:", error) }
        case 'checkRPC':
            try {
                websocket.send( JSON.stringify({type: "checkRPC", message: ""}) );
                console.log("Sent message to Python script to check RPC:", {type: "checkRPC", message: ""})
            }
            catch (error) { console.error("Unable to send message:", error) }
        case 'seeked':
            try {
                websocket.send( JSON.stringify({type: "seeked", message: msg.details}) );
                console.log("Sent message to Python script about video seeking:", {type: "seeked", message: msg.details})
            }
            catch (error) { console.error("Unable to send message:", error) }
    }
});

const getTabInfo = (tabId, infoType) => {
    let interval = 1000;

    switch (infoType) {
        case 'video':
            function videoActivityListeners() {
                const video = document.querySelector('video')

                if (video) {
                    let webpageFirstLoadPlaying = true;
                    let webpageFirstLoadPause = true;

                    // if RPC was cleared after pausing, then it should be set after the video has started playing again
                    // using "checkRPC" so that the python script can determine whether RPC is already active (and ignore this request if it is)
                    video.onplaying = (event) => { 
                        if (webpageFirstLoadPlaying) {
                            webpageFirstLoad = false;
                            return;
                        }

                        chrome.runtime.sendMessage({recipient: "service-worker", request: "checkRPC"});
                    }
                    
                    // RPC should clear when video is paused
                    video.onpause = (event) => { 
                        if (webpageFirstLoadPause) {
                            webpageFirstLoad = false;
                            return;
                        }

                        chrome.runtime.sendMessage({recipient: "service-worker", request: "clear"});
                    }

                    video.onseeked = (event) => {
                        chrome.runtime.sendMessage({recipient: "service-worker", request: "seeked", details: video.currentTime});
                    }
                    
                }
            }

            chrome.scripting.executeScript({ target: {tabId: tabId, allFrames: true}, func: videoActivityListeners });

            return new Promise((resolve) => {
                const check = async () => {
                    let result1 = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('video')?.currentTime
                    });
                    
                    let result2 = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('video')?.duration
                    });
                    
                    // result1 is a list of dictionaries, but only the result key is needed
                    result1 = result1.map(currentTime => currentTime.result)
                    result2 = result2.map(duration => duration.result)

                    let vidCurrentTime = result1.find((time) => time != null);
                    let vidDuration = result2.find((duration) => duration != null);

                    // if the duration and time has been found, send it back to activityFormatting(), otherwise start again
                    if (vidDuration != undefined && vidCurrentTime != undefined) { resolve([vidCurrentTime, vidDuration]); }
                    else { setTimeout(check, interval); }
                };
                check();
            });
        case 'youtube':
            return new Promise((resolve) => {
                const check = async () => {
                    const [{result}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('a.yt-simple-endpoint.style-scope.yt-formatted-string')?.src
                    });

                    let author = result;

                    if (author) { resolve(author); }
                    else { setTimeout(check, interval); }
                };
                check();
            });  
        case 'miruro':
            return new Promise((resolve) => {
                const check = async () => {
                    let result = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('._coverImg_2wrhc_89')?.src
                    });

                    result = result.map(thumbnail => thumbnail.result)

                    let thumbnail = result.find((thumbnail) => thumbnail != null);

                    if (thumbnail) { resolve(thumbnail); }
                    else { setTimeout(check, interval); }
                };
                check();
            });
        case 'soundcloud':
            function soundcloudListener() {
                    const progressBar = document.querySelector('.playbackTimeline__progressWrapper')

                    if (progressBar) {
                        progressBar.onclick = (event) => {
                            let songCurrentTime = document.querySelector('div.playbackTimeline__timePassed span[aria-hidden="true"]')?.textContent
                            songCurrentTime = songCurrentTime.split(':').map(Number);
                            songCurrentTime = (songCurrentTime[0] * 60) + songCurrentTime[1];

                            chrome.runtime.sendMessage({recipient: "service-worker", request: "seeked", details: songCurrentTime})
                        }
                    }
                }

            chrome.scripting.executeScript({ target: {tabId: tabId}, func: soundcloudListener });

            return new Promise((resolve) => {
                const check = async () => {
                    const [{result: result1}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('div.playbackTimeline__timePassed span[aria-hidden="true"]')?.textContent
                    });
                    
                    const [{result: result2}] = await chrome.scripting.executeScript({
                                target: { tabId: tabId },
                                func: () => document.querySelector('div.playbackTimeline__duration span[aria-hidden="true"]')?.textContent
                            });

                    const [{result: result3}] = await chrome.scripting.executeScript({
                                target: { tabId: tabId },
                                func: () => document.querySelector('a.playbackSoundBadge__avatar div.image__lightOutline span')?.style.backgroundImage
                            });
                    const [{result: result4}] = await chrome.scripting.executeScript({
                                target: { tabId: tabId },
                                func: () => document.querySelector('a.playbackSoundBadge__avatar')?.href
                            });
                    
                    const [{result: result5}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('a.playbackSoundBadge__lightLink')?.textContent
                    });

                    try {
                        let songCurrentTime = result1.split(':').map(Number);
                        let songDuration = result2.split(':').map(Number);
                        let thumbnail = result3.split('"')[1];
                        let url = result4.replace(RegExp("(\\?).*", "g"), "");
                        let author = result5

                        songCurrentTime = (songCurrentTime[0] * 60) + songCurrentTime[1];
                        songDuration = (songDuration[0] * 60) + songDuration[1];

                        if (songCurrentTime && songDuration && thumbnail && url) { resolve([songCurrentTime, songDuration, thumbnail, url, author]); }
                        else { setTimeout(check, interval); }
                    } catch (error) {
                        if (!error instanceof TypeError) { console.log('Error in getting SoundCloud information.') }
                    }
                };
                check();
            });
    }
}

async function activityFormatting(tab, duplicateStatus) {
    let tabName = tab.url.replace( RegExp("^(https://)|(www.)|(.com).*|(.tv).*", "g") , "");
    let activityType;

    // tab.audible condition excludes video tabs that are paused, same effect as tab.active but not as strict
    if ( presences.videoType.includes(tabName) && tab.audible ) {
        activityType = 'WATCHING';

        const [vidCurrentTime, vidDuration] = await getTabInfo(tab.id, 'video');

        if ( tab.url.includes("youtube.com/watch") ) {
            const author = await getTabInfo(tab.id, 'youtube');

            return {
                'tabId': tab.id, 
                'name': 'YouTube', 
                'details': (tab.title).replace(RegExp("^(\\(\\d+\\)\\s)|(\\s-\\sYouTube$)|(\\u200b)", "g"), ''), 
                'state': author,
                'url': (tab.url).replace(RegExp("&.*", "g"), ""), 
                'activityType': activityType, 
                'thumbnail': `https://img.youtube.com/vi/${(tab.url).replace(RegExp(".*(\\?v=)|(&).*", "g"), "")}/hqdefault.jpg`,
                'currentTime': vidCurrentTime, 
                'duration': vidDuration,
                'timeSent': Date.now(),
                'duplicates': duplicateStatus
            };
        }
        else if (tab.url.includes("miruro.tv/watch")) {
            const thumbnail = await getTabInfo(tab.id, 'miruro');
            const epNumber = tab.url.replace( RegExp('.*ep=', 'g'), "" );

            return {
                'tabId': tab.id, 
                'name': 'Miruro', 
                'details': (tab.title).replace(RegExp(".*(Watch\\s)|(\\s·\\sMiruro)", "g"), ''), 
                'state': `Episode ${epNumber}`,
                'url': tab.url,
                'activityType': activityType, 
                'thumbnail': thumbnail,
                'currentTime': vidCurrentTime, 
                'duration': vidDuration, 
                'timeSent': Date.now(),
                'duplicates': duplicateStatus 
            };
        }
        else { return undefined; }
    }
    else if ( presences.musicType.includes(tabName) && tab.audible ) {
        activityType = 'LISTENING';
        let details;

        // soundcloud tabs are usually "{song title} by {artist}" if not in a playlist, or "{song title} in {playlist name}"
        if (tab.url.includes("soundcloud.com") && ( tab.title.includes(' by ') || tab.title.includes(' in ') )) {
            const [musicCurrentTime, musicDuration, thumbnail, url, author] = await getTabInfo(tab.id, 'soundcloud')

            if (tab.title.includes(' by ')) { details = tab.title.replace(RegExp("\\s(?!.*\\sby\\s).*", "g"), "") }
            else if (tab.title.includes(' in ')) { details = tab.title.replace(RegExp("\\s(?!.*\\sin\\s).*", "g"), "") }

            return {
                'tabId': tab.id,
                'name': 'SoundCloud',
                'details': details,
                'state': author,
                'url': url,
                'activityType': activityType,
                'thumbnail': thumbnail,
                'currentTime': musicCurrentTime,
                'duration': musicDuration,
                'timeSent': Date.now(),
                'duplicates': duplicateStatus
            };
        }
        else { return undefined; }
    }
    // else if ( presences.streamType.includes(tabName) && tab.audible ) {} (will implement this later)
    else if ( presences.playingType.includes(tabName) ) {
        activityType = 'PLAYING';

        return {
            'tabId': tab.id, 
            'name': tab.title, 
            'details': '',
            'state': '',
            'url': tab.url, 
            'activityType': activityType,
            'duplicates': duplicateStatus
        };
    }
    else { return undefined; }
}

async function getTabs(duplicates = false) {
    try {
        const tabs = await chrome.tabs.query({ url: presences.acceptedURLs });

        tabList = [];

        if (tabs.length > 0) {
            for (const tab of tabs) {
                let activity = await activityFormatting(tab, duplicates);

                if (activity != null) { tabList.push(activity) }
            }
        }

        if (duplicates === true) {
            lastMessage = tabList;
            return tabList;
        }
        else {
            const newDetails = tabList.map( (dict) => `${dict.details} ${dict.state}` );
            let lastDetails = [];

            if (lastMessage.length > 0) { lastDetails = lastMessage.map( (dict) => `${dict.details} ${dict.state}` ); }
            
            if (lastMessage.length === 0 || JSON.stringify(newDetails) !== JSON.stringify(lastDetails)) {
                lastMessage = tabList;
                return tabList;
            }
            else { 
                return "duplicate";
            }
        }
    } catch (error) { 
        console.error("Error fetching tabs", error);
        return [];
    }
}