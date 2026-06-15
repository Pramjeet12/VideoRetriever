// ==================== DOM Elements ====================
const sourceInput = document.getElementById('source');
const languageSelect = document.getElementById('language');
const analyzeBtn = document.getElementById('analyzeBtn');
const loadingState = document.getElementById('loadingState');
const errorState = document.getElementById('errorState');
const errorMessage = document.getElementById('errorMessage');

// ==================== Event Listeners ====================
document.addEventListener('DOMContentLoaded', () => {
    analyzeBtn.addEventListener('click', handleAnalyze);
    sourceInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleAnalyze();
    });
});

// ==================== Main Functions ====================
async function handleAnalyze() {
    const source = sourceInput.value.trim();
    const language = languageSelect.value;

    // Validate input
    if (!source) {
        showError('Please enter a source URL or file path');
        return;
    }

    // Clear previous errors
    clearError();

    // Show loading state
    showLoading();

    try {
        // Make API request
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                source: source,
                language: language
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Analysis failed');
        }

        if (data.success) {
            // Store session ID in localStorage for reference
            localStorage.setItem('lastSessionId', data.session_id);
            
            // Redirect to results page with a small delay
            setTimeout(() => {
                window.location.href = `/results/${data.session_id}`;
            }, 1500);
        }

    } catch (error) {
        hideLoading();
        const message = error.message === 'Failed to fetch'
            ? 'Could not reach the Flask backend. Restart `python app.py` and try again.'
            : (error.message || 'An unexpected error occurred');
        showError(message);
        console.error('Analysis error:', error);
    }
}

// ==================== UI State Functions ====================
function showLoading() {
    analyzeBtn.disabled = true;
    sourceInput.disabled = true;
    languageSelect.disabled = true;
    loadingState.classList.remove('hidden');
    updateProgressSteps('audio');
    cycleProgressSteps();
}

function hideLoading() {
    analyzeBtn.disabled = false;
    sourceInput.disabled = false;
    languageSelect.disabled = false;
    loadingState.classList.add('hidden');
}

function showError(message) {
    errorState.classList.remove('hidden');
    errorMessage.textContent = message;
    
    // Auto-hide error after 5 seconds
    setTimeout(() => {
        clearError();
    }, 5000);
}

function clearError() {
    errorState.classList.add('hidden');
    errorMessage.textContent = '';
}

// ==================== Progress Tracking ====================
function updateProgressSteps(currentStep) {
    const steps = document.querySelectorAll('.step');
    const stepMap = {
        'audio': 0,
        'transcript': 1,
        'summary': 2,
        'rag': 3
    };

    steps.forEach((step, index) => {
        if (index < stepMap[currentStep]) {
            step.classList.add('done');
            step.classList.remove('active');
        } else if (index === stepMap[currentStep]) {
            step.classList.add('active');
            step.classList.remove('done');
        } else {
            step.classList.remove('active', 'done');
        }
    });
}

function cycleProgressSteps() {
    const sequence = ['audio', 'transcript', 'summary', 'rag'];
    let index = 0;
    const interval = setInterval(() => {
        if (loadingState.classList.contains('hidden')) {
            clearInterval(interval);
            return;
        }
        index = Math.min(index + 1, sequence.length - 1);
        updateProgressSteps(sequence[index]);
    }, 2200);
}

// ==================== Utility Functions ====================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== Local Storage Management ====================
function getSavedSettings() {
    try {
        const saved = localStorage.getItem('videoRetrieverSettings');
        return saved ? JSON.parse(saved) : {};
    } catch (error) {
        console.error('Error reading saved settings:', error);
        return {};
    }
}

function saveSettings() {
    try {
        const settings = {
            language: languageSelect.value,
            lastSource: sourceInput.value
        };
        localStorage.setItem('videoRetrieverSettings', JSON.stringify(settings));
    } catch (error) {
        console.error('Error saving settings:', error);
    }
}

// Load and restore previous settings
window.addEventListener('beforeunload', saveSettings);

document.addEventListener('DOMContentLoaded', () => {
    const settings = getSavedSettings();
    if (settings.language) languageSelect.value = settings.language;
    if (settings.lastSource) sourceInput.value = settings.lastSource;
});

// ==================== Keyboard Shortcuts ====================
document.addEventListener('keydown', (e) => {
    // Cmd/Ctrl + Enter to analyze
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleAnalyze();
    }
    
    // Escape to clear input
    if (e.key === 'Escape') {
        sourceInput.value = '';
        sourceInput.focus();
    }
});

// ==================== Network Status ====================
window.addEventListener('online', () => {
    console.log('Connection restored');
    clearError();
});

window.addEventListener('offline', () => {
    showError('No internet connection. Please check your network.');
});

// ==================== Performance Monitoring ====================
function logPerformance() {
    if (window.performance && window.performance.timing) {
        const perfData = window.performance.timing;
        const pageLoadTime = perfData.loadEventEnd - perfData.navigationStart;
        console.log('Page load time: ' + pageLoadTime + 'ms');
    }
}

window.addEventListener('load', logPerformance);
