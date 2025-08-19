
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
import re

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Business email address",
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Your business email address',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label="Password", 
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })
    )

    error_messages = {
        'invalid_login': 'Please enter a correct email and password. Note that both fields may be case-sensitive.',
        'inactive': 'This account is inactive.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = "Business email address"

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Normalize email to lowercase
            username = username.lower().strip()
            # Basic email validation
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', username):
                raise ValidationError('Please enter a valid email address.')
        return username

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            # Try to authenticate
            self.user_cache = authenticate(
                self.request, 
                username=username, 
                password=password
            )
            if self.user_cache is None:
                # Check if user exists
                try:
                    user = User.objects.get(username=username)
                    # User exists but password is wrong
                    raise ValidationError('Incorrect password. Please try again.')
                except User.DoesNotExist:
                    # User doesn't exist
                    raise ValidationError('No account found with this email address.')
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

class CustomUserCreationForm(UserCreationForm):
    username = forms.EmailField(
        label="Business email address",
        help_text="This will be your login email address.",
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Your business email address',
            'autocomplete': 'email',
        })
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Create a strong password',
            'autocomplete': 'new-password',
        }),
        help_text="Your password must be at least 8 characters long and contain a mix of letters, numbers, and symbols."
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
        }),
        strip=False,
        help_text="Enter the same password as before, for verification."
    )

    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove default help text
        for field_name in self.fields:
            if field_name != 'username':
                self.fields[field_name].help_text = None

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Normalize email to lowercase
            username = username.lower().strip()
            
            # Validate email format
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', username):
                raise ValidationError('Please enter a valid email address.')
            
            # Check if email is already taken
            if User.objects.filter(username=username).exists():
                raise ValidationError('An account with this email address already exists.')
                
            # Optional: Check for business email domains
            business_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
            domain = username.split('@')[1].lower()
            if domain in business_domains:
                # Just a warning, not blocking
                pass
                
        return username

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        
        if password1:
            # Custom password validation
            if len(password1) < 8:
                raise ValidationError('Password must be at least 8 characters long.')
            
            if password1.isdigit():
                raise ValidationError('Password cannot be entirely numeric.')
            
            if password1.lower() in ['password', '12345678', 'qwerty', 'abc123']:
                raise ValidationError('This password is too common.')
            
            # Check for at least one letter and one number
            has_letter = re.search(r'[A-Za-z]', password1)
            has_digit = re.search(r'\d', password1)
            
            if not has_letter:
                raise ValidationError('Password must contain at least one letter.')
            
            if not has_digit:
                raise ValidationError('Password must contain at least one number.')

        return password1

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        
        if password1 and password2:
            if password1 != password2:
                raise ValidationError("The two password fields didn't match.")
        
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        # Set email field as well
        user.email = self.cleaned_data["username"]
        if commit:
            user.save()
        return user
