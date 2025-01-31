import os
import logging
import requests
from typing import Optional, Dict, Any
from .media import create_media_payload

logger = logging.getLogger("uvicorn.error")

def create_text_payload(text: str) -> dict[str, str]:
    return {"text": text}

def create_tweet_payload(text: str, media_path: str | None = None) -> dict:
    text_payload = create_text_payload(text=text)
    if media_path is None:
        return text_payload
    media_payload = create_media_payload(path=media_path)
    return {**text_payload, **media_payload}

def construct_tweet_link(tweet_id: str) -> str:
    """Construct the tweet link from the username and tweet ID."""
    return f"https://x.com/{os.getenv("X_USERNAME")}/status/{tweet_id}"


def handle_tweet_response(response: requests.Response) -> tuple[Optional[str], Optional[str]]:
    """
    Handle the response from posting a tweet.
    Returns (message, tweet_link) tuple.
    """
    message: Optional[str] = None
    tweet_link: Optional[str] = None
    
    if response.ok:
        logger.info("Successfully posted tweet")
        message = "Tweet posted successfully!"
        # Extract tweet link on success
        logger.info("Response: %s", response.json())
        tweet_id = response.json().get("data", {}).get("id", "")
        tweet_link = construct_tweet_link(tweet_id=tweet_id)
        if tweet_link:
            logger.info("Tweet URL: %s", tweet_link)
    else:
        try:
            error_details = response.json()
            if 'errors' in error_details:
                # Handle Twitter API specific error format
                error_messages = [error['message'] for error in error_details['errors']]
                message = f"Twitter API Error: {'; '.join(error_messages)}"
                logger.error("Twitter API errors: %s", error_messages)
            else:
                # Handle general API errors
                status_code = response.status_code
                if status_code == 429:
                    message = "Rate limit exceeded. Please wait a few minutes and try again."
                    logger.error("Rate limit exceeded")
                else:
                    # Get the most meaningful error detail
                    detail = error_details.get('detail') or error_details.get('title') or response.reason
                    message = f"Error ({status_code}): {detail}"
                    logger.error("API error %d: %s", status_code, detail)
        except ValueError:
            message = f"Error ({response.status_code}): {response.reason}"
            logger.error("Failed to parse error response: %s", response.text)
        
        logger.error("Failed to post tweet: %s %s - %s", 
                    response.status_code, response.reason, response.text)
    
    return message, tweet_link

def submit_tweet(text: str, media_path: str | None = None, new_token: Dict[str, Any] | None = None) -> requests.Response:
    """
    Post a tweet with optional media.
    Returns the raw response object.
    """
    if not new_token:
        raise ValueError("Token is required")
        
    tweet_payload = create_tweet_payload(text=text, media_path=media_path)
    logger.info(f"Posting tweet with payload: {tweet_payload}")
    
    return requests.request(
        method="POST",
        url="https://api.x.com/2/tweets",
        json=tweet_payload,
        headers={
            "Authorization": f"Bearer {new_token['access_token']}",
            "Content-Type": "application/json",
        },
    )
