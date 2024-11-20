// script.js

const Performance = {
    measurements: {},
    measureStart(label) {
        this.measurements[label] = performance.now();
    },
    measureEnd(label) {
        if (this.measurements[label]) {
            const duration = performance.now() - this.measurements[label];
            console.log(`Performance [${label}]: ${duration.toFixed(2)} ms`);
            delete this.measurements[label];
        }
    },
    logMetric(label, duration) {
        console.log(`Performance [${label}]: ${duration.toFixed(2)} ms`);
    }
};

let parsedDataJson = null; 

const CONFIG = {
    LM_STUDIO_URL: 'http://localhost:3000',
    STATUS_CHECK_INTERVAL: 30000,
    DEBOUNCE_DELAY: 100,
    MAX_CONTENT_HEIGHT: window.innerHeight * 3,
    MIN_CONTENT_HEIGHT: 150,
    FETCH_TIMEOUT: 10000,
    RETRY_LIMIT: 3
};

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
    get notificationArea() { return document.getElementById('notificationArea'); }
};

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        const later = () => {
            clearTimeout(timeout);
            func.apply(this, args);
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

function sanitizeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

async function fetchWithTimeoutAndRetry(url, options = {}, retries = CONFIG.RETRY_LIMIT) {
    const { FETCH_TIMEOUT } = CONFIG;
    for (let attempt = 0; attempt <= retries; attempt++) {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), FETCH_TIMEOUT);
        try {
            const response = await fetch(url, { ...options, signal: controller.signal });
            clearTimeout(id);
            if (!response.ok && attempt < retries) {
                continue;
            }
            return response;
        } catch (error) {
            clearTimeout(id);
            if (attempt >= retries) throw error;
        }
    }
}

function showNotification(message, type = 'info') {
    if (!Elements.notificationArea) return;
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    Elements.notificationArea.appendChild(notification);
    setTimeout(() => {
        notification.classList.add('hiding');
        notification.addEventListener('animationend', () => {
            notification.remove();
        });
    }, 4700);
}

function confirmAction(message) {
    return new Promise((resolve) => {
        const confirmed = confirm(message);
        resolve(confirmed);
    });
}

class ContentManager {
    constructor() {
        this.resizeObserver = null;
        this.mutationObserver = null;
        this.resizeFrame = null; // Added for cleanup
    }

    init() {
        this.autoGrowContent();
        this.highlightSyntax();
        this.updateCharCount();
        this.syncScroll();
        this.observeMutations();
    }

    updateCharCount() {
        if (!Elements.content || !Elements.charCount) return;
        const count = Elements.content.value.length;
        Elements.charCount.textContent = `${count.toLocaleString()} characters`;
    }

    autoGrowContent() {
        if (!Elements.content) return;
        this.resizeTextarea();
        this.resizeObserver = new ResizeObserver(() => {
            this.resizeTextarea();
        });
        this.resizeObserver.observe(Elements.content);
    }

    resizeTextarea() {
        const textarea = Elements.content;
        if (!textarea) return;
        textarea.style.height = 'auto';
        textarea.style.height = `${textarea.scrollHeight}px`;
        if (Elements.highlighting) {
            Elements.highlighting.style.height = `${textarea.scrollHeight}px`;
        }
        const currentHeight = textarea.scrollHeight;
        if (currentHeight > CONFIG.MAX_CONTENT_HEIGHT) {
            textarea.style.height = `${CONFIG.MAX_CONTENT_HEIGHT}px`;
            textarea.style.overflowY = 'scroll';
        } else if (currentHeight < CONFIG.MIN_CONTENT_HEIGHT) {
            textarea.style.height = `${CONFIG.MIN_CONTENT_HEIGHT}px`;
        } else {
            textarea.style.overflowY = 'auto';
        }
    }

    highlightSyntax() {
        if (!Elements.highlighting || !Elements.content) return;
        const text = Elements.content.value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        const patterns = [
            { regex: /(Subject:|To:|CC:|BCC:)/g, cls: 'keyword' },
            { regex: /([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g, cls: 'email' },
            { regex: /(\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b)/g, cls: 'phone' },
        ];
        let highlighted = text;
        patterns.forEach(pattern => {
            highlighted = highlighted.replace(pattern.regex, `<span class="${pattern.cls}">$1</span>`);
        });
        Elements.highlighting.innerHTML = highlighted + '<br />';
    }

    syncScroll() {
        if (Elements.highlighting && Elements.content) {
            Elements.highlighting.scrollTop = Elements.content.scrollTop;
            Elements.highlighting.scrollLeft = Elements.content.scrollLeft;
        }
    }

    observeMutations() {
        if (!Elements.results) return;
        this.mutationObserver = new MutationObserver((mutations) => {
            mutations.forEach(() => {});
        });
        this.mutationObserver.observe(Elements.results, { childList: true, subtree: true });
    }

    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.mutationObserver) {
            this.mutationObserver.disconnect();
            this.mutationObserver = null;
        }
        // Clear any remaining animations
        if (this.resizeFrame) {
            cancelAnimationFrame(this.resizeFrame);
            this.resizeFrame = null;
        }
    }
}

class UIManager {
    constructor() {
        this.contentManager = new ContentManager();
        this.statusCheckIntervalId = null;
        this.layoutCache = { lastWidth: 0, lastHeight: 0, lastContentHeight: 0 };
        this.scrollTimeout = null;
        this.isScrolling = false;
        this.parallaxCleanup = null; // Added for parallax cleanup
        this.layoutOptimizationFrame = null; // Ensure this is initialized
    }

    init() {
        Performance.measureStart('UIManager.init');
        this.contentManager.init();
        this.initializeButtons();
        this.initializeExportButtons();
        this.initializeTextareaEvents();
        this.initializeHoverEffects();
        this.initializeLoadingBar();
        this.initializeNotificationArea();
        this.checkLMStudioStatus();
        this.startStatusCheckInterval();
        this.initializeParallax();
        this.optimizeLayout();
        window.addEventListener('resize', debounce(() => {
            this.optimizeLayout();
        }, CONFIG.DEBOUNCE_DELAY));
        window.addEventListener('scroll', throttle(() => {
            this.handleScroll();
        }, 200));
        Performance.measureEnd('UIManager.init');
    }

    optimizeLayout() {
        if (this.layoutOptimizationFrame) {
            cancelAnimationFrame(this.layoutOptimizationFrame);
        }
        this.layoutOptimizationFrame = requestAnimationFrame(() => {
            Performance.measureStart('optimizeLayout');
            const currentWidth = window.innerWidth;
            const currentHeight = window.innerHeight;
            const currentContentHeight = Elements.content?.scrollHeight || 0;
            const needsUpdate = 
                Math.abs(currentWidth - this.layoutCache.lastWidth) > 10 ||
                Math.abs(currentHeight - this.layoutCache.lastHeight) > 10 ||
                Math.abs(currentContentHeight - this.layoutCache.lastContentHeight) > 10;
            if (!needsUpdate) {
                Performance.measureEnd('optimizeLayout');
                return;
            }
            this.layoutCache = { lastWidth: currentWidth, lastHeight: currentHeight, lastContentHeight: currentContentHeight };
            const container = document.querySelector('.container');
            if (container) {
                const style = container.style;
                style.cssText = `
                    max-width: ${currentWidth > 1600 ? '98vw' : currentWidth > 1200 ? '96vw' : '95vw'};
                    padding: ${currentWidth > 1600 ? '2rem 3rem' : currentWidth > 1200 ? '2rem' : '1rem'};
                `;
                const main = container.querySelector('main');
                if (main) {
                    main.style.cssText = `
                        gap: ${currentWidth > 1200 ? '3rem' : '1.5rem'};
                        flex-direction: ${currentWidth > 1200 ? 'row' : 'column'};
                    `;
                }
                const headerHeight = document.querySelector('header')?.offsetHeight || 0;
                CONFIG.MAX_CONTENT_HEIGHT = Math.max(currentHeight - headerHeight - 100, 300);
            }
            Performance.measureEnd('optimizeLayout');
        });
    }

    initializeButtons() {
        if (Elements.loadSampleBtn) {
            Elements.loadSampleBtn.addEventListener('click', debounce(async () => {
                const confirmed = await confirmAction("Are you sure you want to load the sample email? This will overwrite current content.");
                if (confirmed) {
                    this.loadSample();
                    showNotification("Sample email loaded successfully.", "success");
                }
            }, CONFIG.DEBOUNCE_DELAY));
        }

        if (Elements.clearBtn) {
            Elements.clearBtn.addEventListener('click', debounce(async () => {
                const confirmed = await confirmAction("Are you sure you want to clear the content? This action cannot be undone.");
                if (confirmed) {
                    this.clearContent();
                    showNotification("Content cleared successfully.", "success");
                }
            }, CONFIG.DEBOUNCE_DELAY));
        }

        if (Elements.parseButton) {
            Elements.parseButton.addEventListener('click', () => {
                this.parseEmail();
            });
        }
    }

    initializeExportButtons() {
        if (Elements.exportPdfButton) {
            Elements.exportPdfButton.addEventListener('click', () => {
                this.exportToPdf();
            });
        }

        if (Elements.exportCsvButton) {
            Elements.exportCsvButton.addEventListener('click', () => {
                this.exportToCsv();
            });
        }
    }

    initializeTextareaEvents() {
        if (Elements.content) {
            const debouncedUpdate = debounce(() => {
                requestAnimationFrame(() => {
                    this.contentManager.updateCharCount();
                    this.contentManager.highlightSyntax();
                    this.contentManager.resizeTextarea();
                });
            }, CONFIG.DEBOUNCE_DELAY);

            const throttledScroll = throttle(() => {
                requestAnimationFrame(() => {
                    this.contentManager.syncScroll();
                });
            }, 16);

            Elements.content.addEventListener('input', debouncedUpdate);
            Elements.content.addEventListener('scroll', throttledScroll, { passive: true });
            Elements.content.addEventListener('paste', debouncedUpdate);
        }
    }

    initializeParallax() {
        if ('requestIdleCallback' in window) {
            requestIdleCallback(() => {
                this.setupParallaxEvent();
            });
        } else {
            setTimeout(() => {
                this.setupParallaxEvent();
            }, 0);
        }
    }

    setupParallaxEvent() {
        const starsContainer = Elements.parallaxStars;
        if (!starsContainer) return;

        starsContainer.style.transform = 'translate3d(0, 0, 0)';
        starsContainer.style.willChange = 'transform';
        starsContainer.style.backfaceVisibility = 'hidden';
        starsContainer.style.perspective = '1000px';

        let ticking = false;
        let lastScrollY = window.scrollY;
        let lastMouseX = 0;
        let lastMouseY = 0;
        let animationFrame = null;

        const updateParallax = () => {
            if (!this.isScrolling) {
                const moveX = (lastMouseX - window.innerWidth / 2) * 0.01;
                const moveY = ((lastMouseY + lastScrollY) - window.innerHeight / 2) * 0.01;
                starsContainer.style.transform = `translate3d(${moveX}px, ${moveY}px, 0)`;
            }
            ticking = false;
            animationFrame = null;
        };

        const requestUpdate = () => {
            if (!ticking && !animationFrame) {
                animationFrame = requestAnimationFrame(updateParallax);
                ticking = true;
            }
        };

        const throttledMouseMove = throttle((e) => {
            lastMouseX = e.clientX;
            lastMouseY = e.clientY;
            requestUpdate();
        }, 33);

        const scrollHandler = () => {
            lastScrollY = window.scrollY;
            requestUpdate();
        };

        document.addEventListener('mousemove', throttledMouseMove, { passive: true });
        window.addEventListener('scroll', scrollHandler, { passive: true });

        // Store cleanup function
        this.parallaxCleanup = () => {
            document.removeEventListener('mousemove', throttledMouseMove);
            window.removeEventListener('scroll', scrollHandler);
            if (animationFrame) {
                cancelAnimationFrame(animationFrame);
            }
        };
    }

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

    initializeLoadingBar() {
        if (Elements.loadingBar) {
            Elements.loadingBar.classList.add('hidden');
        }
    }

    initializeNotificationArea() {
        if (!Elements.notificationArea) {
            const notificationArea = document.createElement('div');
            notificationArea.id = 'notificationArea';
            notificationArea.className = 'fixed top-4 right-4 z-50 pointer-events-none';
            document.body.appendChild(notificationArea);
        }
    }

    loadSample() {
        if (!Elements.content) return;
        Elements.content.value = `Subject: Meeting Invitation
To: john.doe@example.com
CC: jane.smith@example.com
BCC: boss@example.com

Hi Team,

I hope this message finds you well. I'd like to invite you all to our quarterly meeting scheduled for next Monday at 10:00 AM. Please find the agenda attached.

Looking forward to your participation.

Best regards,
Alice Johnson
Phone: 123-456-7890
Email: alice.johnson@example.com`;
        this.contentManager.highlightSyntax();
        this.contentManager.updateCharCount();
        this.contentManager.resizeTextarea();
    }

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

    clearResults() {
        if (Elements.results) {
            Elements.results.innerHTML = '<span class="default-text">Parsed content will appear here...</span>';
        }
    }

    startStatusCheckInterval() {
        this.statusCheckIntervalId = setInterval(() => this.checkLMStudioStatus(), CONFIG.STATUS_CHECK_INTERVAL);
    }

    async checkLMStudioStatus() {
        if (!Elements.lmStatus) return;
        Performance.measureStart('checkLMStudioStatus');
        try {
            const response = await fetchWithTimeoutAndRetry(`${CONFIG.LM_STUDIO_URL}/v1/models`, {
                headers: { 'Authorization': 'Bearer lm-studio' }
            });
            this.updateStatusUI(response.ok ? 'connected' : 'error');
        } catch (error) {
            this.updateStatusUI('error');
        }
        Performance.measureEnd('checkLMStudioStatus');
    }

    updateStatusUI(status) {
        const statusMap = {
            'connected': { text: 'Connected', class: 'connected' },
            'error': { text: 'Disconnected', class: 'error' }
        };
        const { text, class: className } = statusMap[status] || { text: 'Unknown', class: 'error' };
        Elements.lmStatus.textContent = text;
        Elements.lmStatus.className = `status-badge ${className}`;
    }

    async parseEmail() {
        if (!this.validateInput()) return;
        if (Elements.parseButton.disabled) return;
        try {
            this.setParsingState(true);
            await new Promise(resolve => requestAnimationFrame(resolve));
            Performance.measureStart('fetchParseResults');
            const response = await this.fetchParseResults();
            Performance.measureEnd('fetchParseResults');
            this.handleParseResponse(response);
        } catch (error) {
            this.handleParseError(error);
        } finally {
            requestAnimationFrame(() => {
                this.setParsingState(false);
            });
        }
    }

    validateInput() {
        if (!Elements.content?.value.trim()) {
            this.showError("Please enter email content!");
            return false;
        }
        return true;
    }

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

    handleParseError(error) {
        console.error('Parsing error:', error);
        this.showError(`Error parsing email: ${sanitizeHTML(error.message)}`);
    }

    setParsingState(isParsing) {
        if (!Elements.parseButton) return;
        const updateState = () => {
            Elements.parseButton.disabled = isParsing;
            Elements.parseButton.classList.toggle('loading-state', isParsing);
            if (Elements.progress) {
                Elements.progress.classList.toggle('hidden', !isParsing);
            }
            if (Elements.loadingBar) {
                Elements.loadingBar.classList.toggle('hidden', !isParsing);
            }
            if (!isParsing) {
                requestAnimationFrame(() => {
                    this.contentManager.updateCharCount();
                });
            }
        };
        requestAnimationFrame(() => {
            requestAnimationFrame(updateState);
        });
    }

    showError(message) {
        if (Elements.results) {
            Elements.results.innerHTML = `
                <div class="error-message text-red-500">
                    <p>${sanitizeHTML(message)}</p>
                </div>
            `;
        }
    }

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

    renderParsedData = (parsedData) => {
        // Make a deep copy to avoid modifying the original data
        const dataCopy = JSON.parse(JSON.stringify(parsedData));
        
        // Explicitly define section order with assignment_info first
        const sectionOrder = [
            'assignment_info',    // Ensure this is first
            'claim_details',
            'contact_info',
            'damage_assessment',
            'policy_info',
            'property_info',
            'timeline',
            'additional_notes',
            'party_information', 
            'incident_details',
            'location_details',
            'status_updates'
        ];
        
        let html = '<div class="results-container">';
        
        // First, explicitly render assignment_info if it exists
        if (dataCopy.assignment_info) {
            html += `
                <div class="result-section">
                    <h3>${this.formatSectionName('assignment_info')}</h3>
                    <div class="result-content">
                        ${this.renderSectionContent(dataCopy.assignment_info)}
                    </div>
                </div>
            `;
            delete dataCopy.assignment_info;
        }
        
        // Then process remaining sections in order
        sectionOrder.slice(1).forEach(sectionKey => {
            if (dataCopy[sectionKey]) {
                html += `
                    <div class="result-section">
                        <h3>${this.formatSectionName(sectionKey)}</h3>
                        <div class="result-content">
                            ${this.renderSectionContent(dataCopy[sectionKey])}
                        </div>
                    </div>
                `;
                delete dataCopy[sectionKey];
            }
        });
        
        // Finally, process any remaining sections not in the order list
        Object.keys(dataCopy).forEach(section => {
            html += `
                <div class="result-section">
                    <h3>${this.formatSectionName(section)}</h3>
                    <div class="result-content">
                        ${this.renderSectionContent(dataCopy[section])}
                    </div>
                </div>
            `;
        });
    
        html += '</div>';
        return html;
    };
    
    renderSectionContent(fields) {
        let content = '';
        for (const key in fields) {
            if (fields.hasOwnProperty(key)) {
                const displayKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                const value = fields[key];
                // Reduced vertical spacing by removing margins and adjusting flex layout
                content += `
                    <div class="result-row flex items-center py-1">
                        <span class="result-key font-semibold min-w-[150px]">${sanitizeHTML(displayKey)}:</span>
                        <span class="result-value">${sanitizeHTML(value)}</span>
                    </div>
                `;
            }
        }
        return content;
    }


    formatSectionName(section) {
        return section.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }


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

    handleScroll() {
        if (!this.isScrolling) {
            requestAnimationFrame(() => {
                document.body.classList.add('is-scrolling');
                if (Elements.parallaxStars) {
                    Elements.parallaxStars.style.willChange = 'auto';
                    Elements.parallaxStars.style.transform = 'translate3d(0, 0, 0)';
                }
            });
            this.isScrolling = true;
        }

        if (this.scrollTimeout) {
            clearTimeout(this.scrollTimeout);
        }

        this.scrollTimeout = setTimeout(() => {
            requestAnimationFrame(() => {
                document.body.classList.remove('is-scrolling');
                if (Elements.parallaxStars) {
                    Elements.parallaxStars.style.willChange = 'transform';
                }
                this.isScrolling = false;
                this.scrollTimeout = null;
            });
        }, 150);
    }

    destroy() {
        Performance.measureStart('destroy');
        
        // Cleanup parallax effects
        if (this.parallaxCleanup) {
            this.parallaxCleanup();
            this.parallaxCleanup = null;
        }
        
        // Clear all timeouts and frames
        if (this.scrollTimeout) {
            clearTimeout(this.scrollTimeout);
            this.scrollTimeout = null;
        }
        if (this.layoutOptimizationFrame) {
            cancelAnimationFrame(this.layoutOptimizationFrame);
            this.layoutOptimizationFrame = null;
        }
        
        // Existing cleanup
        if (this.statusCheckIntervalId) {
            clearInterval(this.statusCheckIntervalId);
            this.statusCheckIntervalId = null;
        }
        
        this.contentManager.destroy();
        
        // Remove event listeners
        window.removeEventListener('resize', this.optimizeLayout);
        window.removeEventListener('scroll', this.handleScroll);
        
        Performance.measureEnd('destroy');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const uiManager = new UIManager();
    uiManager.init();
    window.addEventListener('unload', () => {
        uiManager.destroy();
    });
});
