
document.addEventListener('DOMContentLoaded', function() {
    // Password strength indicator
    const passwordField = document.querySelector('input[type="password"][name*="password1"]');
    const confirmPasswordField = document.querySelector('input[type="password"][name*="password2"]');
    
    if (passwordField) {
        // Create password strength indicator
        const strengthIndicator = document.createElement('div');
        strengthIndicator.className = 'mt-2 text-xs';
        strengthIndicator.innerHTML = `
            <div class="flex items-center space-x-2">
                <div class="flex-1 bg-border rounded-full h-1">
                    <div id="strength-bar" class="h-1 rounded-full transition-all duration-300 bg-red-500" style="width: 0%"></div>
                </div>
                <span id="strength-text" class="text-muted">Weak</span>
            </div>
        `;
        passwordField.parentNode.appendChild(strengthIndicator);
        
        const strengthBar = document.getElementById('strength-bar');
        const strengthText = document.getElementById('strength-text');
        
        passwordField.addEventListener('input', function() {
            const password = this.value;
            let strength = 0;
            let strengthLabel = 'Weak';
            let strengthColor = 'bg-red-500';
            
            // Calculate password strength
            if (password.length >= 8) strength += 1;
            if (/[a-z]/.test(password)) strength += 1;
            if (/[A-Z]/.test(password)) strength += 1;
            if (/[0-9]/.test(password)) strength += 1;
            if (/[^A-Za-z0-9]/.test(password)) strength += 1;
            
            const strengthWidth = (strength / 5) * 100;
            
            if (strength >= 4) {
                strengthLabel = 'Strong';
                strengthColor = 'bg-green-500';
            } else if (strength >= 2) {
                strengthLabel = 'Medium';
                strengthColor = 'bg-yellow-500';
            }
            
            strengthBar.style.width = strengthWidth + '%';
            strengthBar.className = `h-1 rounded-full transition-all duration-300 ${strengthColor}`;
            strengthText.textContent = strengthLabel;
            strengthText.className = strength >= 4 ? 'text-green-600' : strength >= 2 ? 'text-yellow-600' : 'text-red-600';
        });
    }
    
    // Password confirmation validation
    if (confirmPasswordField && passwordField) {
        const validationMessage = document.createElement('div');
        validationMessage.className = 'mt-2 text-xs hidden';
        confirmPasswordField.parentNode.appendChild(validationMessage);
        
        function validatePasswordMatch() {
            const password = passwordField.value;
            const confirmPassword = confirmPasswordField.value;
            
            if (confirmPassword.length > 0) {
                if (password === confirmPassword) {
                    validationMessage.className = 'mt-2 text-xs text-green-600';
                    validationMessage.innerHTML = '✓ Passwords match';
                    confirmPasswordField.classList.remove('border-red-300');
                    confirmPasswordField.classList.add('border-green-300');
                } else {
                    validationMessage.className = 'mt-2 text-xs text-red-600';
                    validationMessage.innerHTML = '✗ Passwords do not match';
                    confirmPasswordField.classList.remove('border-green-300');
                    confirmPasswordField.classList.add('border-red-300');
                }
            } else {
                validationMessage.className = 'mt-2 text-xs hidden';
                confirmPasswordField.classList.remove('border-red-300', 'border-green-300');
            }
        }
        
        confirmPasswordField.addEventListener('input', validatePasswordMatch);
        passwordField.addEventListener('input', validatePasswordMatch);
    }
    
    // Form submission handling
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = `
                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Processing...
                `;
                
                // Re-enable after 5 seconds as fallback
                setTimeout(() => {
                    submitButton.disabled = false;
                    submitButton.innerHTML = submitButton.dataset.originalText || 'Submit';
                }, 5000);
            }
        });
    });
    
    // Store original button text
    document.querySelectorAll('button[type="submit"]').forEach(btn => {
        btn.dataset.originalText = btn.innerHTML;
    });
    
    // Auto-focus first input field
    const firstInput = document.querySelector('input[type="text"], input[type="email"]');
    if (firstInput) {
        firstInput.focus();
    }
    
    // Email validation feedback
    const emailField = document.querySelector('input[type="email"]');
    if (emailField) {
        emailField.addEventListener('blur', function() {
            const email = this.value;
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            
            if (email && !emailRegex.test(email)) {
                this.classList.add('border-red-300');
                this.classList.remove('border-green-300');
            } else if (email) {
                this.classList.add('border-green-300');
                this.classList.remove('border-red-300');
            } else {
                this.classList.remove('border-red-300', 'border-green-300');
            }
        });
    }
});
