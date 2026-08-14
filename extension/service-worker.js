let websocket;
let presences = [];
let tabList = [];
let lastMessage = [];
let debounceTimer;
let keepAliveId;

connectWebSocket("ws://localhost:8765/");

async function connectWebSocket(url, reconnecting = false) {
    return new Promise((resolve, reject) => {
        websocket = new WebSocket(url);

        websocket.onopen = () => {
            console.log('Websocket connected successfully!');

            addListeners(websocket);

            wsSendMessage(websocket, 'hello', 'ping');
            wsSendMessage(websocket, 'enabledPresences');

            function keepAlive() { wsSendMessage(websocket, 'hello', 'keep alive'); }
            
            keepAliveId = setInterval(keepAlive, 20000);
            
            resolve();
        }

        websocket.onclose = (event) => {
            if (event.wasClean) { console.log('Websocket has closed.'); }
            else {
                if (reconnecting === false) {
                    console.warn('Websocket connection failed. Attempting reconnection in 30s...');
                    wsConnectionClosed();
                }

                reject('Unclean Websocket closure.');
            }
        }
    });
}

function wsConnectionClosed(startImmediately = false) {
    async function attemptReconnect() {
        try {
            await connectWebSocket("ws://localhost:8765/", true)
            clearInterval(reconnectIntervalID);
        } catch (error) { console.warn('Websocket connection failed. Attempting reconnection in 30s...'); }
    }

    if (startImmediately === true) {
        console.warn('Websocket is closed. Attempting to reconnect...');
        attemptReconnect();
    }
    const reconnectIntervalID = setInterval(attemptReconnect, 30000);
}

function wsSendMessage(websocket, type, message = '') {
    if (websocket.readyState === WebSocket.OPEN) { websocket.send(JSON.stringify({type: type, message: message})); } 
    else if (websocket.readyState === WebSocket.CLOSING || websocket.readyState === WebSocket.CLOSED) {
        if (keepAliveId) { clearInterval(keepAliveId); }
        wsConnectionClosed(true);
    }
}

function addListeners(websocket) {
    chrome.tabs.onUpdated.addListener(() => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => { 
            const tabs = await getTabs();
            if (tabs !== 'duplicate') {
                console.log("Tabs sent (duplicates = false):", tabs);
                wsSendMessage(websocket, 'tabs', tabs);
            }
        }, 1000);
    });

    chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
        if (removeInfo.isWindowClosing === true) {
            wsSendMessage(websocket, 'tabs', []);
        }
        else {
            if (tabList.length > 0) {
                const filterIndex = tabList.findIndex(tab => tabId === tab.tabId);

                if (filterIndex !== -1) {
                    tabList.splice(filterIndex, 1);
                    console.log("Updated tabList:", tabList);
                    wsSendMessage(websocket, 'tabs', tabList);
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

        else if (msg.type === "enabledPresences") {
            const response = msg.message
            const hostNames = response.map( (dict) => dict.hostName );

            presences = {
                acceptedURLs: hostNames.map( (host) => `*://*.${host}/*` ), 
                videoType: response.map( dict => {if (dict.type === 'video') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
                musicType: response.map( dict => {if (dict.type === 'music') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
                streamType: response.map( dict => {if (dict.type === 'stream') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
                playingType: response.map( dict => {if (dict.type === 'playing') { return dict.name.toLowerCase() } else {return 'N/A'}} ),
                
                videoURLs: response.map( (dict) => {if (dict.type === 'video') { return dict.hostName } else { return 'N/A' }} ),
                musicURLs: response.map( (dict) => {if (dict.type === 'music') { return dict.hostName } else { return 'N/A' }} ),
                streamURLs: response.map( (dict) => {if (dict.type === 'stream') { return dict.hostName } else { return 'N/A' }} ),
                playingURLs: response.map( (dict) => {if (dict.type === 'playing') { return dict.hostName } else { return 'N/A' }} )
            };

            presences.videoType = (presences.videoType).filter( presenceName => presenceName !== "N/A" );
            presences.musicType = (presences.musicType).filter( presenceName => presenceName !== "N/A" );
            presences.streamType = (presences.streamType).filter( presenceName => presenceName !== "N/A" );
            presences.playingType = (presences.playingType).filter( presenceName => presenceName !== "N/A" );

            presences.videoURLs = (presences.videoURLs).filter( presenceUrl => presenceUrl !== "N/A" );
            presences.musicURLs = (presences.musicURLs).filter( presenceUrl => presenceUrl !== "N/A" );
            presences.streamURLs = (presences.streamURLs).filter( presenceUrl => presenceUrl !== "N/A" );
            presences.playingURLs = (presences.playingURLs).filter( presenceUrl => presenceUrl !== "N/A" );

            console.log('Received enabledPresences from Python script:', presences);
        }

        else if (msg.type === 'tabs') {
            clearTimeout(debounceTimer);

            debounceTimer = setTimeout(async () => { 
                const tabs = await getTabs(true);
                console.log("Tabs sent (duplicates = true):", tabs);
                wsSendMessage(websocket, 'tabs', tabs);
            }, 1000);
        }

        else if (msg.type === 'exit') {
            console.log('System tray icon exiting.')
            wsSendMessage(websocket, 'exit', exit);
        }
    });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.request === 'ping') {
        try {
                wsSendMessage(websocket, 'hello', 'from extension popup');
                sendResponse({recipient: "popup.js", request: "pong"});
            } catch (error) {
                console.error("Unable to send message:", error)
            }
    }

    else if (msg.request === 'clear') {
        try {
            wsSendMessage(websocket, 'clear', 'clear');
            console.log("Sent message to Python script to clear status:", {type: "clear", message: "clear"})
        }
        catch (error) { console.error("Unable to send message:", error) }
    }  

    else if (msg.request === 'checkRPC') {
        try {
            wsSendMessage(websocket, 'checkRPC');
            console.log("Sent message to Python script to check RPC:", {type: "checkRPC", message: ""})
        }
        catch (error) { console.error("Unable to send message:", error) }
    }
    
    else if (msg.request === 'seeked') {
        try {
            if (msg.details) {
                wsSendMessage(websocket, 'seeked', msg.details);
                console.log("Sent message to Python script about video seeking:", {type: "seeked", message: msg.details})
            }
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
                        if (video.currentTime) { chrome.runtime.sendMessage({recipient: "service-worker", request: "seeked", details: video.currentTime}); }
                    }
                }
            }

            chrome.scripting.executeScript({ target: {tabId: tabId, allFrames: true}, func: videoActivityListeners });

            return new Promise((resolve) => {
                const check = async () => {
                    let currentTime = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('video')?.currentTime
                    });
                    
                    let duration = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('video')?.duration
                    });
                    
                    // currentTime is a list of dictionaries, but only the result key is needed
                    currentTime = currentTime.map(time => time.result).find(time => time != null);
                    duration = duration.map(dur => dur.result).find(dur => dur != null);

                    // if the duration and time has been found, send it back to activityFormatting(), otherwise start again
                    if (currentTime && duration) { resolve([currentTime, duration]); }
                    else { setTimeout(check, interval); }
                };
                check();
            });
        case 'youtube':
            return new Promise((resolve) => {
                const check = async () => {
                    const [{result: author}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('a.yt-simple-endpoint.style-scope.yt-formatted-string')?.textContent
                    });

                    if (author) { resolve(author); }
                    else { setTimeout(check, interval); }
                };
                check();
            });
        case 'youtubeMusic':
            return new Promise((resolve) => {
                const check = async () => {
                    const [{result: title}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('yt-formatted-string.title.style-scope.ytmusic-player-bar')?.textContent
                    });

                    const [{result: author}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('yt-formatted-string.byline.ytmusic-player-bar').getAttribute('title').split(' • ')[0].replace(' &', ',')
                    });

                    let [{result: thumbnail}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('img.style-scope.ytmusic-player-bar')?.src
                    });

                    thumbnail = thumbnail.replace( RegExp('\\?sqp.*', 'g'), '' );

                    if (title && author) { resolve([title, author, thumbnail]); }
                    else { setTimeout(check, interval); }
                };
                check();
            });
        case 'miruro':
            return new Promise((resolve) => {
                const check = async () => {
                    let thumbnail = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('._coverImg_2wrhc_89')?.src
                    });

                    thumbnail = thumbnail.map(thumbnail => thumbnail.result).find(thumbnail => thumbnail != null);

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

                        if (songCurrentTime) {
                            songCurrentTime = songCurrentTime.split(':').map(Number);
                            songCurrentTime = (songCurrentTime[0] * 60) + songCurrentTime[1];

                            chrome.runtime.sendMessage({recipient: "service-worker", request: "seeked", details: songCurrentTime})
                        }
                        
                    }
                }
            }

            chrome.scripting.executeScript({ target: {tabId: tabId}, func: soundcloudListener });

            return new Promise((resolve) => {
                const check = async () => {
                    let [{result: songCurrentTime}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('div.playbackTimeline__timePassed span[aria-hidden="true"]')?.textContent
                    });
                    
                    let [{result: songDuration}] = await chrome.scripting.executeScript({
                                target: { tabId: tabId },
                                func: () => document.querySelector('div.playbackTimeline__duration span[aria-hidden="true"]')?.textContent
                            });

                    let [{result: thumbnail}] = await chrome.scripting.executeScript({
                                target: { tabId: tabId },
                                func: () => document.querySelector('a.playbackSoundBadge__avatar div.image__lightOutline span')?.style.backgroundImage
                            });
                    
                    let [{result: url}] = await chrome.scripting.executeScript({
                                target: { tabId: tabId },
                                func: () => document.querySelector('a.playbackSoundBadge__avatar')?.href
                            });
                    
                    const [{result: author}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('a.playbackSoundBadge__lightLink')?.textContent
                    });

                    try {
                        songCurrentTime = songCurrentTime.split(':').map(Number);
                        songDuration = songDuration.split(':').map(Number);
                        thumbnail = thumbnail.split('"')[1];
                        url = url.replace(RegExp("(\\?).*", "g"), "");

                        songCurrentTime = (songCurrentTime[0] * 60) + songCurrentTime[1];
                        songDuration = (songDuration[0] * 60) + songDuration[1];

                        if (songCurrentTime && songDuration && thumbnail && url && author) { resolve([songCurrentTime, songDuration, thumbnail, url, author]); }
                        else { setTimeout(check, interval); }
                    } catch (error) {
                        if (!error instanceof TypeError) { console.log('Error in getting SoundCloud information.') }
                    }
                };
                check();
            });
        case 'twitch':
            return new Promise((resolve) => {
                const check = async () => {
                    let channel = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('h1.tw-title')?.textContent
                    });

                    let streamTitle = await chrome.scripting.executeScript({
                        target: { tabId: tabId, allFrames: true },
                        func: () => document.querySelector('p[data-a-target="stream-title"]')?.textContent
                    });

                    channel = channel.map(channel => channel.result).find(channel => channel != null);
                    streamTitle = streamTitle.map(title => title.result).find(title => title != null);

                    if (channel && streamTitle) { resolve([channel, streamTitle]); }
                    else { setTimeout(check, interval); }
                };
                check();
            });
    }
}

async function activityFormatting(tab, duplicateStatus) {
    let tabName = tab.url.replace( RegExp("^(https://)|(www.)|(.com).*|(.tv).*", "g") , "" );
    let hostName = tab.url.replace( RegExp("^(https://)|(www.)|(/.*)", "g") , "" );
    let activityType;

    // tab.audible condition excludes video tabs that are paused, same effect as tab.active but not as strict
    if ( (presences.videoType.includes(tabName) || presences.videoURLs.includes(hostName)) && tab.audible ) {
        activityType = 'WATCHING';

        const [currentTime, duration] = await getTabInfo(tab.id, 'video');

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
                'currentTime': currentTime, 
                'duration': duration,
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
                'currentTime': currentTime, 
                'duration': duration, 
                'timeSent': Date.now(),
                'duplicates': duplicateStatus 
            };
        }
        else { return undefined; }
    }
    else if ( (presences.musicType.includes(tabName) || presences.musicURLs.includes(hostName)) && tab.audible ) {
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
        else if ( tab.url.includes('music.youtube.com') && tab.audible ) {
            const [currentTime, duration] = await getTabInfo(tab.id, 'video');
            const [title, author, thumbnail] = await getTabInfo(tab.id, 'youtubeMusic');

            return {
                'tabId': tab.id,
                'name': 'YouTube Music',
                'details': title,
                'state': author,
                'url': undefined,
                'activityType': activityType,
                'thumbnail': thumbnail,
                'currentTime': currentTime,
                'duration': duration,
                'timeSent': Date.now(),
                'duplicates': duplicateStatus
            };
        }
        else { return undefined; }
    }
    else if ( presences.streamType.includes(tabName) && tab.audible ) {
        activityType = 'STREAMING';

        if ( tab.url.includes('twitch.tv') && tab.url.replace('https://twitch.tv/', '').length > 0 ) {
            let [channel, streamTitle] = await getTabInfo(tab.id, 'twitch');

            // thumbnail will be replaced with link to Twitch.png on GitHub after initial commit
            return {
                'tabId': tab.id, 
                'name': 'Twitch', 
                'details': channel, 
                'state': streamTitle,
                'activityType': activityType, 
                'thumbnail': 'https://raw.githubusercontent.com/ganyuun/LivePresence/refs/heads/master/assets/Twitch.png',
                'timeSent': Date.now(),
                'duplicates': duplicateStatus 
            };
        }
    }
    else if ( presences.playingType.includes(tabName) || presences.playingURLs.includes(hostName) ) {
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
            // compare the previously sent activities to the current
            // if they're the same (or their length are both 0), it won't be sent through the websocket
            const newDetails = tabList.map( (dict) => `${dict.details} ${dict.state}` );
            let lastDetails = [];

            if (lastMessage.length > 0) { lastDetails = lastMessage.map( (dict) => `${dict.details} ${dict.state}` ); }
            
            if (JSON.stringify(newDetails) !== JSON.stringify(lastDetails)) {
                lastMessage = tabList;
                return tabList;
            }
            else if (newDetails.length === 0 && lastDetails.length === 0) { return 'duplicate'; }
            else { return 'duplicate'; }
        }
    } catch (error) { 
        console.error("Error fetching tabs", error);
        return [];
    }
}