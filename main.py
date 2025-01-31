import os
import logging
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from requests import Response
from starlette.templating import _TemplateResponse

from x_automation_studio.auth import (
    refresh_token_if_needed,
    initialize_oauth_flow,
    exchange_code_for_token,
    is_token_expired,
)
from x_automation_studio.tweet import submit_tweet, handle_tweet_response
from x_automation_studio.utils import get_temp_dir
from x_automation_studio.session import save_token, get_user_session
from x_automation_studio.suggestion import get_suggestion

# Configure logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv(override=True)

# FastAPI application
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Global state
oauth_states: Dict[str, Dict[str, Any]] = {}
# Add flash messages storage
flash_messages: Dict[str, Dict[str, str]] = {}

# Try to load existing session for demo user
current_session, current_token = get_user_session(os.getenv("USERNAME"))
if current_session and current_token:
    logger.info("Loaded existing Twitter session with token expiry: %s", current_token.get("expires_at"))
else:
    logger.info("No existing Twitter session found")

@app.get("/", response_class=HTMLResponse)
def show_form(request: Request) -> _TemplateResponse:
    """
    Serve a basic form (index.html) for posting tweets.
    Also handles displaying flash messages after redirects.
    """
    # Get and clear any flash messages for this session
    messages = flash_messages.pop(os.getenv("USERNAME"), {})
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            **messages  # Unpack message and tweet_link if they exist
        }
    )

@app.post("/tweet", response_class=HTMLResponse, response_model=None)
async def post_tweet(
    request: Request,
    text: str = Form(...),
    image: Optional[UploadFile] = File(None)
) -> RedirectResponse:
    """
    Handle the form submission:
      - Try to use saved session if available
      - Otherwise begin OAuth flow with Twitter
    Always returns a redirect response.
    """
    global current_session, current_token
    
    logger.info("Processing tweet request: text='%s', has_image=%s", text, bool(image))
    
    # Process image if provided
    image_path = None
    if image and image.filename:
        temp_dir = get_temp_dir()
        image_path = os.path.join(temp_dir, image.filename)
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())
        logger.info("Saved uploaded image to: %s", image_path)

    # If we have a saved session, try to use it
    if current_session and current_token:
        try:
            # Try to refresh token if needed
            if is_token_expired(current_token):
                new_token = refresh_token_if_needed(current_session, current_token)
                if new_token:
                    current_token = new_token
                    save_token(os.getenv("USERNAME"), current_token)
                    logger.info("Successfully refreshed token, new expiry: %s", current_token.get("expires_at"))
                else:
                    logger.warning("Token refresh failed, will start new OAuth flow")
                    current_session = None
                    current_token = None
            
            if current_token:  # Only try posting if we still have a valid token
                response = submit_tweet(text=text, media_path=image_path, new_token=current_token)
                
                message, tweet_link = handle_tweet_response(response)
                flash_messages[os.getenv("USERNAME")] = {
                    "message": message,
                    "tweet_link": tweet_link if response.ok else None
                }
                return RedirectResponse(url="/", status_code=303)

        except Exception as e:
            logger.error("Error using saved session: %s", str(e))
            flash_messages[os.getenv("USERNAME")] = {
                "message": f"Error posting tweet: {str(e)}"
            }
            return RedirectResponse(url="/", status_code=303)

    # Only start new OAuth flow if we don't have valid tokens
    if not current_token:
        twitter_session, code_verifier, authorization_url, oauth_state = initialize_oauth_flow()
        logger.info("Starting new OAuth2 flow with Twitter")

        # Store everything needed for the callback
        oauth_states[oauth_state] = {
            "text": text,
            "image_path": image_path,
            "twitter_session": twitter_session,
            "code_verifier": code_verifier
        }
        logger.info("Stored OAuth state: %s", oauth_state)

        # Redirect to Twitter's OAuth page
        logger.info("Redirecting to Twitter auth URL: %s", authorization_url)
        return RedirectResponse(url=authorization_url, status_code=303)

@app.get("/oauth/callback", response_class=HTMLResponse)
def callback(request: Request, code: str, state: str) -> RedirectResponse:
    """
    Callback route after user authenticates with Twitter.
      - Exchange code for token.
      - Post the tweet.
    Returns a redirect to home page with flash messages.
    """
    global current_session, current_token
    
    logger.info("Received OAuth callback with state: %s", state)
    
    # Retrieve stored info for this state
    if state not in oauth_states:
        logger.error("Invalid OAuth state received: %s", state)
        flash_messages[os.getenv("USERNAME")] = {
            "message": "Invalid state or session has expired."
        }
        return RedirectResponse(url="/", status_code=303)

    stored_data = oauth_states[state]
    text: str = stored_data["text"]
    image_path: Optional[str] = stored_data["image_path"]
    twitter_session: OAuth2Session = stored_data["twitter_session"]
    code_verifier: str = stored_data["code_verifier"]

    # Exchange code for token
    logger.info("Exchanging OAuth code for token")
    token = exchange_code_for_token(twitter_session, code, code_verifier)
    if not token:
        flash_messages[os.getenv("USERNAME")] = {
            "message": "Failed to authenticate with Twitter"
        }
        return RedirectResponse(url="/", status_code=303)

    # Update current session and save it
    current_session = twitter_session
    current_token = token
    save_token(os.getenv("USERNAME"), token)
    logger.info("Saved new token to disk")

    # Post the tweet
    logger.info("Attempting to post tweet with new token")
    response: Response = submit_tweet(text=text, media_path=image_path, new_token=token)
    
    message, tweet_link = handle_tweet_response(response)
    flash_messages[os.getenv("USERNAME")] = {
        "message": message,
        "tweet_link": tweet_link if response.ok else None
    }

    # Remove state data to avoid re-use or memory leaks
    del oauth_states[state]
    logger.info("Cleaned up OAuth state")

    return RedirectResponse(url="/", status_code=303)

@app.get("/suggestions", response_class=HTMLResponse)
async def get_tweet_suggestion(
    request: Request,
    prompt: Optional[str] = None
) -> _TemplateResponse:
    """
    Get tweet suggestions based on an optional prompt.
    Returns the suggestion template with generated text.
    """
    suggested_text = get_suggestion(prompt)
    return templates.TemplateResponse(
        "suggestion.html",
        {
            "request": request,
            "text": suggested_text
        }
    )

# To run this app:
#   uvicorn tweet:app --host 0.0.0.0 --port 5000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)