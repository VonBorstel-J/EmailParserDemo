// Constants
const CONFIG = {
    LM_STUDIO_URL: 'http://localhost:3000',
    STATUS_CHECK_INTERVAL: 30000, // 30 seconds
    SAMPLE_EMAIL: `
Subject: Re: Claim #BX-20230722 - Flood damage at Johnson residence

To: claims@insuranceco.com, field-team@insuranceco.com
CC: t.roberts@structuralexperts.com, mold-assessment@cleanair.org
BCC: legal@insuranceco.com

Hey team,

Just got back from the Johnson property - what a mess! 😱 You wouldn't believe the state of things. Anyway, here's the lowdown on claim #BX-20230722:

So, Mrs. Emily Johnson (emilyjohnson@email.com, 555-867-5309) has been renting this place at 456 Maple Avenue, Riverside, CA 92501 for about 3 years now. The poor woman was out of town when that freak rainstorm hit on July 22nd (last Saturday). Her neighbor, Mr. Thompson, called her when he saw water pouring out from under her front door. Talk about a nasty surprise to come home to!

I spoke with the property owner, Big City Rentals (contact: Sarah Lee, 555-123-4567), and they're insured under policy #BCR-2023-45678. They've already sent their maintenance guy, Joe, to start drying things out. He's set up some industrial fans, but honestly, I think we're looking at some serious remediation here.

I did a walkthrough yesterday (July 25th) with our go-to public adjuster, Frank Martinez from "Fair Claim Settlements Inc." (frank.martinez@fairclaim.com). We're both concerned about potential mold issues, especially in the basement where the water was about 2 feet deep. 😬 The living room carpet is completely ruined, and there's visible water damage on the walls up to about 18 inches.

Mrs. Johnson mentioned she's staying with her sister for now but is worried about her lease. I told her to document everything she's had to spend because of this - hotel, eating out, etc. Oh, and she's been trying to reach our claims hotline (800-555-9876) but keeps getting put on hold. Can someone look into that?

I'm thinking we need to get Tom Roberts (CC'd) from Structural Experts to take a look ASAP. There's some worrying cracks in the foundation that might have been exacerbated by the flooding. Also, I've CC'd the mold assessment team because, well, better safe than sorry, right?

Quick summary for the database (Jane, can you input this?):

Claim handler: Yours truly, Alex Rodriguez (alex.r@insuranceco.com, 555-246-8101)
Type of loss: Flood damage (possibly some wind damage to roof as well)
Occupancy: Tenant-occupied
Someone home during incident: No
Current repair status: Initial drying in progress
Inspection type: Initial assessment complete, waiting on specialist inspections
I've uploaded some photos and videos to our shared drive. Fair warning: the basement shots are pretty grim.

We should probably touch base with legal (BCC'd) about the lease situation. Also, heads up to the field team - the street is still partially flooded, so wear your waterproof boots if you're heading out there!

Let me know if you need anything else. I'll be in the office tomorrow trying to make sense of all this!

Cheers,
Alex

P.S. Does anyone know a good place for lunch near the office? I'm getting tired of the usual sandwich shop! 🥪😄
`
};

// DOM Elements Cache
const Elements = {
    get content() { return document.getElementById('emailContent'); },
    get charCount() { return document.getElementById('charCount'); },
    get parseButton() { return document.getElementById('parseButton'); },
    get progress() { return document.getElementById('progressIndicator'); },
    get loadingBar() { return document.querySelector('.loading-bar'); },
    get results() { return document.getElementById('results'); },
    get lmStatus() { return document.getElementById('lmStatus'); }
};

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

// App Initialization
function initializeApp() {
    updateCharCount();
    checkLMStudioStatus();
    startStatusCheckInterval();

    // Initialize buttons
    const loadSampleBtn = document.getElementById('loadSample');
    const clearBtn = document.getElementById('clearBtn');
    const parseBtn = document.getElementById('parseButton');

    if (loadSampleBtn) {
        loadSampleBtn.addEventListener('click', () => {
            loadSample();
            updateCharCount();
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            clearContent();
            updateCharCount();
        });
    }

    if (parseBtn) {
        parseBtn.addEventListener('click', parseEmail);
    }

    // Initialize textarea events
    if (Elements.content) {
        Elements.content.addEventListener('input', debounce(updateCharCount, 300));
    }

    // Initialize parallax
    initParallax();

    // Ensure loading-bar is hidden initially
    if (Elements.loadingBar) {
        Elements.loadingBar.classList.add('hidden');
    }

    // Add hover glow effect to buttons
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('mousemove', (e) => {
            const rect = button.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            button.style.setProperty('--x', `${x}px`);
            button.style.setProperty('--y', `${y}px`);
        });
    });
}

// LM Studio Status Management
function startStatusCheckInterval() {
    setInterval(checkLMStudioStatus, CONFIG.STATUS_CHECK_INTERVAL);
}

// LM Studio health check function
async function checkLMStudioStatus() {
    if (!Elements.lmStatus) return;

    try {
        // Use the models endpoint instead of /health
        const response = await fetch(`${CONFIG.LM_STUDIO_URL}/v1/models`, {
            headers: {
                'Authorization': 'Bearer lm-studio'
            }
        });
        updateStatusUI(response.ok ? 'connected' : 'error');
    } catch (error) {
        console.error('LM Studio connection error:', error);
        updateStatusUI('error');
    }
}

function updateStatusUI(status) {
    const statusMap = {
        'connected': { text: 'Connected', class: 'connected' },
        'error': { text: 'Disconnected', class: 'error' }
    };

    const { text, class: className } = statusMap[status];
    Elements.lmStatus.textContent = text;
    Elements.lmStatus.className = `status-badge ${className}`;
}

// Content Management
function updateCharCount() {
    if (!Elements.content || !Elements.charCount) return;

    const count = Elements.content.value.length;
    Elements.charCount.textContent = `${count.toLocaleString()} characters`;
}

function clearContent() {
    if (!Elements.content) return;

    Elements.content.value = '';
    clearResults();
    updateCharCount();
}

function loadSample() {
    if (!Elements.content) return;

    Elements.content.value = CONFIG.SAMPLE_EMAIL;
    updateCharCount();
}

// Email Parsing
async function parseEmail() {
    if (!validateInput()) return;

    setParsingState(true);

    try {
        const response = await fetchParseResults();
        handleParseResponse(response);
    } catch (error) {
        handleParseError(error);
    } finally {
        setParsingState(false);
    }
}

function validateInput() {
    if (!Elements.content || !Elements.content.value.trim()) {
        showError("Please enter email content!");
        return false;
    }
    return true;
}

async function fetchParseResults() {
    const response = await fetch('/parse_email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email_content: Elements.content.value })
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
    }

    return response.json();
}

function handleParseResponse(data) {
    if (data.result) {
        showResults(data.result);
    } else if (data.error) {
        showError(data.error);
    } else {
        showError("No valid results returned from parser.");
    }
}

function handleParseError(error) {
    console.error('Parsing error:', error);
    showError(`Error parsing email: ${sanitizeHTML(error.message)}`);
}

function setParsingState(isParsing) {
    if (Elements.parseButton) {
        Elements.parseButton.disabled = isParsing;
    }
    if (Elements.progress) {
        Elements.progress.classList.toggle('hidden', !isParsing);
    }
    if (Elements.loadingBar) {
        Elements.loadingBar.classList.toggle('hidden', !isParsing);
    }
    if (!isParsing) {
        updateCharCount();
    }
}

// Results Display
function clearResults() {
    if (Elements.results) {
        Elements.results.innerHTML = '';
    }
}

function showError(message) {
    if (Elements.results) {
        Elements.results.innerHTML = `
            <div class="error-message text-red-500">
                <p>${sanitizeHTML(message)}</p>
            </div>
        `;
    }
}

function showResults(result) {
    if (!Elements.results) return;

    try {
        const html = renderParsedData(result);
        Elements.results.innerHTML = html;
    } catch (error) {
        console.error('Error displaying results:', error);
        showError(`Error displaying results: ${sanitizeHTML(error.message)}`);
    }
}

function renderParsedData(parsedData) {
    let html = '<div class="results-container">';
    for (const section in parsedData) {
        if (parsedData.hasOwnProperty(section)) {
            html += `
                <div class="result-section">
                    <h3>${sanitizeHTML(formatSectionName(section))}</h3>
                    <div class="result-content">
                        ${renderSectionContent(parsedData[section])}
                    </div>
                </div>
            `;
        }
    }
    html += '</div>';
    return html;
}

function formatSectionName(section) {
    return section.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function renderSectionContent(fields) {
    let content = '';
    for (const key in fields) {
        if (fields.hasOwnProperty(key)) {
            const displayKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const value = fields[key];
            content += `
                <div class="result-row flex">
                    <span class="result-key font-semibold">${sanitizeHTML(displayKey)}:</span>
                    <span class="result-value ml-2">${sanitizeHTML(value)}</span>
                </div>
            `;
        }
    }
    return content;
}

// Security: Sanitize HTML content
function sanitizeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Parallax Effect
function initParallax() {
    const starsContainer = document.querySelector('.parallax-stars');
    if (!starsContainer) return;

    // Create multiple stars
    for (let i = 0; i < 100; i++) {
        const star = document.createElement('div');
        star.className = 'star';

        // Random position
        star.style.left = `${Math.random() * 100}%`;
        star.style.top = `${Math.random() * 100}%`;

        // Random size
        const size = Math.random() * 3;
        star.style.width = `${size}px`;
        star.style.height = `${size}px`;

        // Random animation duration and delay
        star.style.setProperty('--duration', `${2 + Math.random() * 3}s`);
        star.style.setProperty('--delay', `${Math.random() * 2}s`);

        starsContainer.appendChild(star);
    }

    // Throttle mousemove events for performance
    const throttledMouseMove = throttle((e) => {
        const moveX = (e.clientX - window.innerWidth / 2) * 0.01;
        const moveY = (e.clientY - window.innerHeight / 2) * 0.01;
        requestAnimationFrame(() => {
            starsContainer.style.transform = `translate(${moveX}px, ${moveY}px)`;
        });
    }, 1000 / 60); // 60fps

    document.addEventListener('mousemove', throttledMouseMove);
}
