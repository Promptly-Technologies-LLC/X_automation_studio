# x_automation_studio/auth.py
import os
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

# Load environment variables
load_dotenv()

def create_oauth1_auth() -> OAuth1:
    """Create OAuth1 authentication object for Twitter API requests."""
    required_vars = [
        ("X_API_KEY", os.environ.get("X_API_KEY")),
        ("X_API_SECRET", os.environ.get("X_API_SECRET")),
        ("X_ACCESS_TOKEN", os.environ.get("X_ACCESS_TOKEN")),
        ("X_ACCESS_TOKEN_SECRET", os.environ.get("X_ACCESS_TOKEN_SECRET"))
    ]
    
    missing_vars = [var_name for var_name, var_value in required_vars if not var_value]
    
    if missing_vars:
        raise ValueError(
            f"Missing required credentials in .env file: {', '.join(missing_vars)}. "
            "Please add them to your .env file."
        )
    
    return OAuth1(
        client_key=required_vars[0][1],      # X_API_KEY
        client_secret=required_vars[1][1],  # X_API_SECRET
        resource_owner_key=required_vars[2][1],  # X_ACCESS_TOKEN
        resource_owner_secret=required_vars[3][1]   # X_ACCESS_TOKEN_SECRET
    )