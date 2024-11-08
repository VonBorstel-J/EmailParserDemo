/* =========================
   Performance Utility
   ========================= */
   const Performance = {
    measurements: {},

    /**
     * Start measuring the time for a given label.
     * @param {string} label - The label for the measurement.
     */
    measureStart(label) {
        this.measurements[label] = performance.now();
    },

    /**
     * End measuring the time for a given label and log the duration.
     * @param {string} label - The label for the measurement.
     */
    measureEnd(label) {
        if (this.measurements[label]) {
            const duration = performance.now() - this.measurements[label];
            console.log(`Performance [${label}]: ${duration.toFixed(2)} ms`);
            delete this.measurements[label];
        } else {
            console.warn(`Performance.end called without a matching Performance.start for label: ${label}`);
        }
    },

    /**
     * Log a performance metric.
     * @param {string} label - The label for the metric.
     * @param {number} duration - The duration in milliseconds.
     */
    logMetric(label, duration) {
        console.log(`Performance [${label}]: ${duration.toFixed(2)} ms`);
    }
};

/* =========================
   Global Variables
   ========================= */
let parsedDataJson = null; 

/* =========================
   Configuration Object
   ========================= */
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
`,
    DEBOUNCE_DELAY: 100,
    MAX_CONTENT_HEIGHT: window.innerHeight * 3,
    MIN_CONTENT_HEIGHT: 150,
    FETCH_TIMEOUT: 10000, // 10 seconds for fetch operations
    RETRY_LIMIT: 3 // Number of retries for failed fetch operations
};

/* =========================
   DOM Elements Cache
   ========================= */
const Elements = {
    get content() { return document.getElementById('emailContent'); },
    get highlighting() { return document.getElementById('highlighting'); },
    get charCount() { return document.getElementById('charCount'); },
    get parseButton() { return document.getElementById('parseButton'); },
    get progress() { return document.getElementById('progressIndicator'); },
    get loadingBar() { return document.querySelector('.loading-bar'); },
    get results() { return document.getElementById('results'); },
    get lmStatus() { return document.getElementById('lmStatus'); },
    get loadSampleBtn() { return document.getElementById('loadSample'); },
    get clearBtn() { return document.getElementById('clearBtn'); },
    get exportPdfButton() { return document.getElementById('exportPdfButton'); },
    get exportCsvButton() { return document.getElementById('exportCsvButton'); },
    get parallaxStars() { return document.querySelector('.parallax-stars'); },
    get notificationArea() { return document.getElementById('notificationArea'); } // New for notifications
};

/* =========================
   Utility Functions
   ========================= */

/**
 * Debounce function to limit the rate at which a function can fire.
 * @param {Function} func - The function to debounce.
 * @param {number} wait - The debounce delay in milliseconds.
 * @returns {Function}
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func.apply(this, args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Throttle function to limit the rate at which a function can fire.
 * @param {Function} func - The function to throttle.
 * @param {number} limit - The time limit in milliseconds.
 * @returns {Function}
 */
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

/**
 * Sanitize HTML to prevent XSS attacks.
 * @param {string} str - The string to sanitize.
 * @returns {string}
 */
function sanitizeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Fetch wrapper with timeout and retry logic.
 * @param {string} url - The URL to fetch.
 * @param {object} options - Fetch options.
 * @param {number} retries - Number of retries.
 * @returns {Promise<Response>}
 */
async function fetchWithTimeoutAndRetry(url, options = {}, retries = CONFIG.RETRY_LIMIT) {
    const { FETCH_TIMEOUT } = CONFIG;
    for (let attempt = 0; attempt <= retries; attempt++) {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), FETCH_TIMEOUT);
        try {
            const response = await fetch(url, { ...options, signal: controller.signal });
            clearTimeout(id);
            if (!response.ok && attempt < retries) {
                continue; // Retry on non-OK response
            }
            return response;
        } catch (error) {
            clearTimeout(id);
            if (attempt >= retries) throw error;
        }
    }
}

/**
 * Display a notification to the user.
 * @param {string} message - The message to display.
 * @param {string} type - The type of notification ('success', 'error', 'info').
 */
function showNotification(message, type = 'info') {
    if (!Elements.notificationArea) return;

    const notification = document.createElement('div');
    notification.className = `notification ${type} p-4 mb-4 rounded-lg`;
    notification.textContent = message;

    Elements.notificationArea.appendChild(notification);

    // Automatically remove after 5 seconds
    setTimeout(() => {
        notification.classList.add('hiding');
        notification.addEventListener('animationend', () => {
            notification.remove();
        });
    }, 4700); // Slightly earlier than removal to allow for animation
}

/**
 * Confirm action with the user.
 * @param {string} message - The confirmation message.
 * @returns {Promise<boolean>}
 */
function confirmAction(message) {
    return new Promise((resolve) => {
        const confirmed = confirm(message);
        resolve(confirmed);
    });
}

/* =========================
   ContentManager Class
   ========================= */
class ContentManager {
    constructor() {
        this.resizeObserver = null;
        this.mutationObserver = null;
    }

    /**
     * Initialize ContentManager functionalities.
     */
    init() {
        this.autoGrowContent();
        this.highlightSyntax();
        this.updateCharCount();
        this.syncScroll();
        this.observeMutations();
    }

    /**
     * Update the character count display.
     */
    updateCharCount() {
        if (!Elements.content || !Elements.charCount) return;

        const count = Elements.content.value.length;
        Elements.charCount.textContent = `${count.toLocaleString()} characters`;
    }

    /**
     * Automatically grow the textarea based on content.
     */
    autoGrowContent() {
        if (!Elements.content) return;

        // Initial auto-resize
        this.resizeTextarea();

        // Setup ResizeObserver for dynamic resizing
        this.resizeObserver = new ResizeObserver(() => {
            this.resizeTextarea();
        });
        this.resizeObserver.observe(Elements.content);
    }

    /**
     * Resize the textarea and highlighting layer.
     */
    resizeTextarea() {
        const textarea = Elements.content;
        if (!textarea) return;

        textarea.style.height = 'auto'; // Reset height
        textarea.style.height = `${textarea.scrollHeight}px`; // Set to scrollHeight

        // Adjust highlighting layer height
        if (Elements.highlighting) {
            Elements.highlighting.style.height = `${textarea.scrollHeight}px`;
        }

        // Enforce max and min height
        const currentHeight = textarea.scrollHeight;
        if (currentHeight > CONFIG.MAX_CONTENT_HEIGHT) {
            textarea.style.height = `${CONFIG.MAX_CONTENT_HEIGHT}px`;
            textarea.style.overflowY = 'scroll';
        } else if (currentHeight < CONFIG.MIN_CONTENT_HEIGHT) {
            textarea.style.height = `${CONFIG.MIN_CONTENT_HEIGHT}px`;
        } else {
            textarea.style.overflowY = 'hidden';
        }
    }

    /**
     * Apply syntax highlighting to the email content.
     */
    highlightSyntax() {
        if (!Elements.highlighting || !Elements.content) return;

        const text = Elements.content.value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Define regex patterns
        const patterns = [
            { regex: /(Subject:|To:|CC:|BCC:)/g, cls: 'keyword' },
            { regex: /([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g, cls: 'email' },
            { regex: /(\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b)/g, cls: 'phone' },
        ];

        let highlighted = text;

        patterns.forEach(pattern => {
            highlighted = highlighted.replace(pattern.regex, `<span class="${pattern.cls}">$1</span>`);
        });

        Elements.highlighting.innerHTML = highlighted + '<br />'; // Add a line break to prevent textarea height issues
    }

    /**
     * Synchronize scrolling between textarea and highlighting layer.
     */
    syncScroll() {
        if (Elements.highlighting && Elements.content) {
            Elements.highlighting.scrollTop = Elements.content.scrollTop;
            Elements.highlighting.scrollLeft = Elements.content.scrollLeft;
        }
    }

    /**
     * Observe mutations in the results area.
     */
    observeMutations() {
        if (!Elements.results) return;

        this.mutationObserver = new MutationObserver((mutations) => {
            mutations.forEach(mutation => {
                // Handle mutations if needed
                // Placeholder for future enhancements
            });
        });

        this.mutationObserver.observe(Elements.results, { childList: true, subtree: true });
    }

    /**
     * Cleanup method to prevent memory leaks
     */
    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.mutationObserver) {
            this.mutationObserver.disconnect();
            this.mutationObserver = null;
        }
    }
}

/* =========================
   UIManager Class
   ========================= */
class UIManager {
    constructor() {
        this.contentManager = new ContentManager();
        this.statusCheckIntervalId = null;
        // Add layout cache
        this.layoutCache = {
            lastWidth: 0,
            lastHeight: 0,
            lastContentHeight: 0
        };
    }

    /**
     * Initialize UIManager functionalities.
     */
    init() {
        Performance.measureStart('UIManager.init');

        this.initializeButtons();
        this.initializeExportButtons();
        this.initializeTextareaEvents();
        this.initializeHoverEffects();
        this.initializeLoadingBar();
        this.initializeNotificationArea();
        this.contentManager.init();
        this.checkLMStudioStatus();
        this.startStatusCheckInterval();
        this.initializeParallax(); // Moved inside init to allow for requestIdleCallback
        this.optimizeLayout(); // Initial layout optimization

        // Add window resize event with debounce and layout optimization
        window.addEventListener('resize', debounce(() => {
            this.optimizeLayout();
        }, CONFIG.DEBOUNCE_DELAY));

        Performance.measureEnd('UIManager.init');
    }

    /**
     * Optimize the layout of the UI based on window size and cached layout.
     */
    optimizeLayout() {
        Performance.measureStart('optimizeLayout');
    
        const currentWidth = window.innerWidth;
        const currentHeight = window.innerHeight;
        const currentContentHeight = Elements.content ? Elements.content.scrollHeight : 0;
    
        // Check if layout needs to be recalculated based on threshold
        const widthChanged = Math.abs(currentWidth - this.layoutCache.lastWidth) > 10;
        const heightChanged = Math.abs(currentHeight - this.layoutCache.lastHeight) > 10;
        const contentHeightChanged = Math.abs(currentContentHeight - this.layoutCache.lastContentHeight) > 10;
    
        if (!widthChanged && !heightChanged && !contentHeightChanged) {
            Performance.measureEnd('optimizeLayout');
            return;
        }
    
        // Update cache
        this.layoutCache = {
            lastWidth: currentWidth,
            lastHeight: currentHeight,
            lastContentHeight: currentContentHeight
        };
    
        const container = document.querySelector('.container');
        if (container) {
            // More aggressive width scaling based on screen size
            if (currentWidth > 1600) {
                container.style.maxWidth = '98vw';
                container.style.padding = '2rem 3rem';
            } else if (currentWidth > 1200) {
                container.style.maxWidth = '96vw';
                container.style.padding = '2rem';
            } else {
                container.style.maxWidth = '95vw';
                container.style.padding = '1rem';
            }
    
            // Adjust main layout if it exists
            const main = container.querySelector('main');
            if (main) {
                if (currentWidth > 1200) {
                    main.style.gap = '3rem';
                    main.style.flexDirection = 'row';
                } else {
                    main.style.gap = '1.5rem';
                    main.style.flexDirection = 'column';
                }
            }
    
            // Calculate optimal content height
            const headerHeight = document.querySelector('header')?.offsetHeight || 0;
            const optimalHeight = currentHeight - headerHeight - 100; // Leave some margin
            CONFIG.MAX_CONTENT_HEIGHT = Math.max(optimalHeight, 300);
        }
    
        Performance.measureEnd('optimizeLayout');
    }

    /**
     * Initialize button event listeners.
     */
    initializeButtons() {
        if (Elements.loadSampleBtn) {
            Elements.loadSampleBtn.addEventListener('click', async () => {
                Performance.measureStart('loadSample');
                const confirmed = await confirmAction("Are you sure you want to load the sample email? This will overwrite current content.");
                if (confirmed) {
                    this.loadSample();
                    showNotification("Sample email loaded successfully.", "success");
                }
                Performance.measureEnd('loadSample');
            });
        }

        if (Elements.clearBtn) {
            Elements.clearBtn.addEventListener('click', async () => {
                Performance.measureStart('clearContent');
                const confirmed = await confirmAction("Are you sure you want to clear the content? This action cannot be undone.");
                if (confirmed) {
                    this.clearContent();
                    showNotification("Content cleared successfully.", "success");
                }
                Performance.measureEnd('clearContent');
            });
        }

        if (Elements.parseButton) {
            Elements.parseButton.addEventListener('click', () => {
                Performance.measureStart('parseEmail');
                this.parseEmail();
                Performance.measureEnd('parseEmail');
            });
        }
    }

    /**
     * Initialize export buttons event listeners.
     */
    initializeExportButtons() {
        if (Elements.exportPdfButton) {
            Elements.exportPdfButton.addEventListener('click', () => {
                Performance.measureStart('exportToPdf');
                this.exportToPdf();
                Performance.measureEnd('exportToPdf');
            });
        }

        if (Elements.exportCsvButton) {
            Elements.exportCsvButton.addEventListener('click', () => {
                Performance.measureStart('exportToCsv');
                this.exportToCsv();
                Performance.measureEnd('exportToCsv');
            });
        }
    }

    /**
     * Initialize textarea input and scroll events.
     */
    initializeTextareaEvents() {
        if (Elements.content) {
            Elements.content.addEventListener('input', debounce(() => {
                Performance.measureStart('contentInput');
                this.contentManager.updateCharCount();
                this.contentManager.highlightSyntax();
                this.contentManager.resizeTextarea();
                Performance.measureEnd('contentInput');
            }, CONFIG.DEBOUNCE_DELAY));

            Elements.content.addEventListener('scroll', () => {
                Performance.measureStart('contentScroll');
                this.contentManager.syncScroll();
                Performance.measureEnd('contentScroll');
            });

            // Handle paste events
            Elements.content.addEventListener('paste', debounce(() => {
                Performance.measureStart('contentPaste');
                this.contentManager.updateCharCount();
                this.contentManager.highlightSyntax();
                this.contentManager.resizeTextarea();
                Performance.measureEnd('contentPaste');
            }, CONFIG.DEBOUNCE_DELAY));
        }
    }

    /**
     * Initialize parallax effect using requestIdleCallback for better performance.
     */
    initializeParallax() {
        Performance.measureStart('initializeParallax');

        if ('requestIdleCallback' in window) {
            requestIdleCallback(() => {
                this.createParallaxStars();
                this.setupParallaxEvent();
                Performance.measureEnd('initializeParallax');
            });
        } else {
            // Fallback for browsers that do not support requestIdleCallback
            setTimeout(() => {
                this.createParallaxStars();
                this.setupParallaxEvent();
                Performance.measureEnd('initializeParallax');
            }, 0);
        }
    }

    /**
     * Create parallax stars.
     */
    createParallaxStars() {
        const starsContainer = Elements.parallaxStars;
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
    }

    /**
     * Setup parallax mousemove event.
     */
    setupParallaxEvent() {
        const starsContainer = Elements.parallaxStars;
        if (!starsContainer) return;

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

    /**
     * Initialize hover glow effects on buttons.
     */
    initializeHoverEffects() {
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

    /**
     * Initialize loading bar visibility.
     */
    initializeLoadingBar() {
        if (Elements.loadingBar) {
            Elements.loadingBar.classList.add('hidden');
        }
    }

    /**
     * Initialize notification area if it doesn't exist.
     * Creates a notification area div at the top of the body.
     */
    initializeNotificationArea() {
        if (!Elements.notificationArea) {
            const notificationArea = document.createElement('div');
            notificationArea.id = 'notificationArea';
            notificationArea.className = 'fixed top-4 right-4 z-50';
            document.body.appendChild(notificationArea);
        }
    }

    /**
     * Load sample email content.
     */
    loadSample() {
        if (!Elements.content) return;

        Elements.content.value = CONFIG.SAMPLE_EMAIL;
        this.contentManager.highlightSyntax();
        this.contentManager.updateCharCount();
        this.contentManager.resizeTextarea();
    }

    /**
     * Clear the email content and results.
     */
    clearContent() {
        if (!Elements.content) return;

        Elements.content.value = '';
        if (Elements.highlighting) {
            Elements.highlighting.innerHTML = '<br />';
        }
        this.clearResults();
        this.contentManager.updateCharCount();
        this.contentManager.resizeTextarea();
    }

    /**
     * Clear the results display area.
     */
    clearResults() {
        if (Elements.results) {
            Elements.results.innerHTML = '<span class="default-text">Parsed content will appear here...</span>';
        }
    }

    /**
     * Start the interval for LM Studio status checks.
     */
    startStatusCheckInterval() {
        this.statusCheckIntervalId = setInterval(() => this.checkLMStudioStatus(), CONFIG.STATUS_CHECK_INTERVAL);
    }

    /**
     * Check the LM Studio connection status.
     */
    async checkLMStudioStatus() {
        if (!Elements.lmStatus) return;

        Performance.measureStart('checkLMStudioStatus');

        try {
            // Use the models endpoint instead of /health
            const response = await fetchWithTimeoutAndRetry(`${CONFIG.LM_STUDIO_URL}/v1/models`, {
                headers: {
                    'Authorization': 'Bearer lm-studio'
                }
            });
            this.updateStatusUI(response.ok ? 'connected' : 'error');
        } catch (error) {
            console.error('LM Studio connection error:', error);
            this.updateStatusUI('error');
        } finally {
            Performance.measureEnd('checkLMStudioStatus');
        }
    }

    /**
     * Update the status UI based on LM Studio connection.
     * @param {string} status - 'connected' or 'error'
     */
    updateStatusUI(status) {
        const statusMap = {
            'connected': { text: 'Connected', class: 'connected' },
            'error': { text: 'Disconnected', class: 'error' }
        };

        const { text, class: className } = statusMap[status] || { text: 'Unknown', class: 'error' };
        Elements.lmStatus.textContent = text;
        Elements.lmStatus.className = `status-badge ${className}`;
    }

    /**
     * Parse the email content.
     */
    async parseEmail() {
        if (!this.validateInput()) return;

        this.setParsingState(true);

        try {
            Performance.measureStart('fetchParseResults');
            const response = await this.fetchParseResults();
            Performance.measureEnd('fetchParseResults');
            this.handleParseResponse(response);
        } catch (error) {
            this.handleParseError(error);
        } finally {
            this.setParsingState(false);
        }
    }

    /**
     * Validate the email input.
     * @returns {boolean}
     */
    validateInput() {
        if (!Elements.content?.value.trim()) {
            this.showError("Please enter email content!");
            return false;
        }
        return true;
    }

    /**
     * Fetch parse results from the server with timeout and retry.
     * @returns {Promise<Object>}
     */
    async fetchParseResults() {
        const response = await fetchWithTimeoutAndRetry('/parse_email', {
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

    /**
     * Handle the parse response from the server.
     * @param {Object} data - The response data.
     */
    handleParseResponse(data) {
        if (data.result) {
            parsedDataJson = data.result; 
            this.showResults(data.result);
            showNotification("Email parsed successfully.", "success");
        } else if (data.error) {
            this.showError(data.error);
        } else {
            this.showError("No valid results returned from parser.");
        }
    }

    /**
     * Handle parse errors.
     * @param {Error} error 
     */
    handleParseError(error) {
        console.error('Parsing error:', error);
        this.showError(`Error parsing email: ${sanitizeHTML(error.message)}`);
    }

    /**
     * Set the parsing state (loading or not).
     * @param {boolean} isParsing 
     */
    setParsingState(isParsing) {
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
            this.contentManager.updateCharCount();
        }
    }

    /**
     * Display error messages in the results area.
     * @param {string} message 
     */
    showError(message) {
        if (Elements.results) {
            Elements.results.innerHTML = `
                <div class="error-message text-red-500">
                    <p>${sanitizeHTML(message)}</p>
                </div>
            `;
        }
    }

    /**
     * Display parsed results in the results area.
     * @param {Object} result 
     */
    showResults(result) {
        if (!Elements.results) return;

        try {
            const html = this.renderParsedData(result);
            Elements.results.innerHTML = html;
        } catch (error) {
            console.error('Error displaying results:', error);
            this.showError(`Error displaying results: ${sanitizeHTML(error.message)}`);
        }
    }

    /**
     * Render parsed data into HTML.
     * @param {Object} parsedData 
     * @returns {string}
     */
    renderParsedData(parsedData) {
        let html = '<div class="results-container">';
        for (const section in parsedData) {
            if (parsedData.hasOwnProperty(section)) {
                html += `
                    <div class="result-section">
                        <h3>${sanitizeHTML(this.formatSectionName(section))}</h3>
                        <div class="result-content">
                            ${this.renderSectionContent(parsedData[section])}
                        </div>
                    </div>
                `;
            }
        }
        html += '</div>';
        return html;
    }

    /**
     * Format section names for display.
     * @param {string} section 
     * @returns {string}
     */
    formatSectionName(section) {
        return section.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    /**
     * Render section content into HTML.
     * @param {Object} fields 
     * @returns {string}
     */
    renderSectionContent(fields) {
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

    /**
     * Export parsed data to PDF.
     */
    async exportToPdf() {
        if (!parsedDataJson) {
            this.showError("No parsed data available for export.");
            return;
        }

        showNotification("Exporting to PDF...", "info");

        try {
            Performance.measureStart('fetchExportToPdf');
            const response = await fetchWithTimeoutAndRetry('/export_pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ parsed_data: parsedDataJson })
            });
            Performance.measureEnd('fetchExportToPdf');

            if (!response.ok) throw new Error("Failed to generate PDF");

            const blob = await response.blob();
            this.downloadFile(blob, 'exported_data.pdf');
            showNotification("PDF exported successfully.", "success");
        } catch (error) {
            console.error("PDF Export Error:", error);
            this.showError("Failed to export PDF");
        }
    }

    /**
     * Export parsed data to CSV.
     */
    async exportToCsv() {
        if (!parsedDataJson) {
            this.showError("No parsed data available for export.");
            return;
        }

        showNotification("Exporting to CSV...", "info");

        try {
            Performance.measureStart('fetchExportToCsv');
            const response = await fetchWithTimeoutAndRetry('/export_csv', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ parsed_data: parsedDataJson })
            });
            Performance.measureEnd('fetchExportToCsv');

            if (!response.ok) throw new Error("Failed to generate CSV");

            const blob = await response.blob();
            this.downloadFile(blob, 'exported_data.csv');
            showNotification("CSV exported successfully.", "success");
        } catch (error) {
            console.error("CSV Export Error:", error);
            this.showError("Failed to export CSV");
        }
    }

    /**
     * Download a file given a blob and filename.
     * @param {Blob} blob 
     * @param {string} filename 
     */
    downloadFile(blob, filename) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();

        setTimeout(() => window.URL.revokeObjectURL(url), 100);
    }

    /**
     * Cleanup method to prevent memory leaks
     */
    destroy() {
        Performance.measureStart('destroy');
        
        // Clear intervals
        if (this.statusCheckIntervalId) {
            clearInterval(this.statusCheckIntervalId);
            this.statusCheckIntervalId = null;
        }
        
        // Clean up content manager
        this.contentManager.destroy();
        
        // Clean up performance measurements
        Object.keys(Performance.measurements).forEach(key => {
            delete Performance.measurements[key];
        });
        
        // Remove event listeners
        window.removeEventListener('resize', this.debouncedResize);
        document.removeEventListener('mousemove', this.throttledMouseMove);
        
        Performance.measureEnd('destroy');
    }
}

/* =========================
   Initialization Code
   ========================= */
document.addEventListener('DOMContentLoaded', () => {
    const uiManager = new UIManager();
    uiManager.init();

    // Add cleanup on page unload
    window.addEventListener('unload', () => {
        uiManager.destroy();
    });
});
