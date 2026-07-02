import os

# Feedback Email Settings
# Add these to your main settings.py file

# Frontend URL for feedback links (reads from .env or defaults to dev URL)
BASE_URL = os.environ.get('BASE_URL')  # Change in .env file

# Email settings for feedback requests
FEEDBACK_EMAIL_ENABLED = True  # Set to False to disable feedback emails
FEEDBACK_EMAIL_DELAY_MINUTES = 5  # Optional: delay before sending feedback email

# Default feedback questions for BusinessFeedbackView
DEFAULT_FEEDBACK_QUESTIONS = [
    "How would you rate the food quality?",
    "How would you rate the delivery time?", 
    "How would you rate the packaging?",
    "How would you rate the overall service?",
    "Would you recommend this restaurant to others?"
]

# Email template customization
FEEDBACK_EMAIL_SUBJECT_TEMPLATE = "How was your experience with {business_name}? - Order #{order_number}"
FEEDBACK_EMAIL_FROM_NAME = "Kirazee Team"
