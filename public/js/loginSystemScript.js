const authWrapper = document.querySelector('.auth-wrapper');
const loginTrigger = document.querySelectorAll('.login-trigger');
const registerTrigger = document.querySelector('.register-trigger');
const forgotTrigger = document.querySelector('.forgot-trigger');

const registerPanel = document.getElementById('registerPanel');
const registerWelcome = document.getElementById('registerWelcome');
const forgotPanel = document.getElementById('forgotPanel');
const forgotWelcome = document.getElementById('forgotWelcome');

// Check URL parameter to determine which form to show
const urlParams = new URLSearchParams(window.location.search);
const showRegister = urlParams.get('register') === 'true';
const showForgot = urlParams.get('forgot') === 'true';

// Function to show register panel
function showRegisterPanel() {
    if (registerPanel) {
        registerPanel.style.display = 'flex';
        registerPanel.style.zIndex = '100';
    }
    if (registerWelcome) {
        registerWelcome.style.display = 'flex';
        registerWelcome.style.zIndex = '100';
    }
    if (forgotPanel) {
        forgotPanel.style.display = 'none';
        forgotPanel.style.zIndex = '0';
    }
    if (forgotWelcome) {
        forgotWelcome.style.display = 'none';
        forgotWelcome.style.zIndex = '0';
    }
}

// Function to show forgot panel
function showForgotPanel() {
    if (registerPanel) {
        registerPanel.style.display = 'none';
        registerPanel.style.zIndex = '0';
    }
    if (registerWelcome) {
        registerWelcome.style.display = 'none';
        registerWelcome.style.zIndex = '0';
    }
    if (forgotPanel) {
        forgotPanel.style.display = 'flex';
        forgotPanel.style.zIndex = '100';
    }
    if (forgotWelcome) {
        forgotWelcome.style.display = 'flex';
        forgotWelcome.style.zIndex = '100';
    }
}

// Set initial state based on URL parameter
if (authWrapper) {
    if (showForgot) {
        authWrapper.classList.add('toggled');
        showForgotPanel();
    } else if (showRegister) {
        authWrapper.classList.add('toggled');
        showRegisterPanel();
    } else {
        showRegisterPanel(); // Default setup
    }
}

// Add toggle for register
if (registerTrigger) {
    registerTrigger.addEventListener('click', (e) => {
        e.preventDefault();
        if (authWrapper) {
            showRegisterPanel();
            authWrapper.classList.add('toggled');
            window.history.pushState({}, '', '?register=true');
        }
    });
}

// Add toggle for forgot password
if (forgotTrigger) {
    forgotTrigger.addEventListener('click', (e) => {
        e.preventDefault();
        if (authWrapper) {
            showForgotPanel();
            authWrapper.classList.add('toggled');
            window.history.pushState({}, '', '?forgot=true');
        }
    });
}

// Add toggle for login (handle multiple login triggers)
loginTrigger.forEach(trigger => {
    if (trigger) {
        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            if (authWrapper) {
                authWrapper.classList.remove('toggled');
                window.history.pushState({}, '', window.location.pathname);
                
                // Reset to register panel after animation completes
                setTimeout(() => {
                    showRegisterPanel();
                }, 1500);
            }
        });
    }
});