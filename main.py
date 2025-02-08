# main.py
import os
import logging
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session
from fastapi import FastAPI, Request, Form, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from requests import Response
from starlette.templating import _TemplateResponse
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from x_automation_studio.models import AIModel, Prompt, TextOutput, Feedback, Domain, PromptType

from x_automation_studio.auth import (
    refresh_token_if_needed,
    initialize_oauth_flow,
    exchange_code_for_token,
    is_token_expired,
)
from x_automation_studio.tweet import submit_tweet, handle_tweet_response
from x_automation_studio.utils import get_temp_dir
from x_automation_studio.session import save_token, get_user_session
from x_automation_studio.suggestion import get_suggestion, create_output_record, rewrite_prompt, select_random_model
from x_automation_studio.models import engine, create_tables, seed_db

# Configure logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv(override=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables
    create_tables()
    seed_db()
    yield

# FastAPI application
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# Global state
oauth_states: Dict[str, Dict[str, Any]] = {}
# Add flash messages storage
flash_messages: Dict[str, Dict[str, str]] = {}

# Try to load existing session for demo user
current_session, current_token = get_user_session(os.getenv("X_USERNAME"))
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
    messages = flash_messages.pop(os.getenv("X_USERNAME"), {})

    with Session(engine) as session:
        domains = session.exec(select(Domain)).all()

    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "domains": domains,
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
                    save_token(os.getenv("X_USERNAME"), current_token)
                    logger.info("Successfully refreshed token, new expiry: %s", current_token.get("expires_at"))
                else:
                    logger.warning("Token refresh failed, will start new OAuth flow")
                    current_session = None
                    current_token = None
            
            if current_token:  # Only try posting if we still have a valid token
                response = submit_tweet(text=text, media_path=image_path, new_token=current_token)
                
                message, tweet_link = handle_tweet_response(response)
                flash_messages[os.getenv("X_USERNAME")] = {
                    "message": message,
                    "tweet_link": tweet_link if response.ok else None
                }
                return RedirectResponse(url="/", status_code=303)

        except Exception as e:
            logger.error("Error using saved session: %s", str(e))
            flash_messages[os.getenv("X_USERNAME")] = {
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
        flash_messages[os.getenv("X_USERNAME")] = {
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
        flash_messages[os.getenv("X_USERNAME")] = {
            "message": "Failed to authenticate with Twitter"
        }
        return RedirectResponse(url="/", status_code=303)

    # Update current session and save it
    current_session = twitter_session
    current_token = token
    save_token(os.getenv("X_USERNAME"), token)
    logger.info("Saved new token to disk")

    # Post the tweet
    logger.info("Attempting to post tweet with new token")
    response: Response = submit_tweet(text=text, media_path=image_path, new_token=token)
    
    message, tweet_link = handle_tweet_response(response)
    flash_messages[os.getenv("X_USERNAME")] = {
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
    background_tasks: BackgroundTasks,
    context: str = "",
    mode: str = "weighted",
    domain_id: int | str = ""
) -> _TemplateResponse:
    """
    Get tweet suggestions based on an optional context.
    Returns the suggestion template with generated text.
    """
    suggestion: dict = get_suggestion(context, mode, domain_id=domain_id)
    # Create the TextOutput record synchronously and get its id
    textoutput_id = create_output_record(suggestion)

    return templates.TemplateResponse(
        "suggestion.html",
        {
            "request": request,
            "text": suggestion["text"],
            "textoutput_id": textoutput_id
        }
    )


@app.post("/feedback", response_class=HTMLResponse)
def submit_feedback(
    request: Request,
    textoutput_id: int = Form(...),
    score: int = Form(...),
    comment: Optional[str] = Form(None)
) -> str:
    """
    Endpoint to submit feedback for a given suggestion TextOutput.
    Score should be 1 for thumbs up or -1 for thumbs down, and an optional comment.
    """
    with Session(engine) as session:
        output = session.get(TextOutput, textoutput_id)
        if output is None:
            return "Feedback submission failed: output record not found."
        # Assuming that the TextOutput model has feedback_score and feedback_comment fields
        output.feedback.append(Feedback(score=score, comment=comment))
        session.add(output)
        session.commit()
    return "<div class='alert alert-success'>Feedback recorded. Thank you!</div>"


# ----------------------
# Settings Endpoints
# ----------------------

@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    expanded_domain_id: Optional[int] = None,
    prompt_type: Optional[str] = "text"
) -> _TemplateResponse:
    """
    Render the settings page with lists of existing AI models and prompts.
    """
    with Session(engine) as session:
        models = session.exec(select(AIModel)).all()
        # Eagerly load the prompts relationship
        domains = session.exec(
            select(Domain).options(selectinload(Domain.prompts))
        ).all()
        prompts = session.exec(select(Prompt)).all()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "models": models,
        "domains": domains,
        "prompts": prompts,
        "expanded_domain_id": expanded_domain_id,
        "prompt_type": prompt_type
    })


@app.post("/settings/add_model", response_class=HTMLResponse)
def add_model(
    request: Request,
    model_name: str = Form(...),
    text_output: bool = Form(False),
    image_output: bool = Form(False)
):
    """
    Add a new AI model with specified output capabilities.
    At least one output type must be specified.
    """
    if not (text_output or image_output):
        raise HTTPException(
            status_code=400,
            detail="Model must support at least one output type (text or image)"
        )
        
    with Session(engine) as session:
        new_model = AIModel(
            name=model_name,
            text_output=text_output,
            image_output=image_output
        )
        session.add(new_model)
        session.commit()
        session.refresh(new_model)
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/delete_model/{model_id}", response_class=HTMLResponse)
def delete_model(request: Request, model_id: int):
    """
    Delete an existing AI model by its ID.
    """
    with Session(engine) as session:
        model = session.get(AIModel, model_id)
        if not model:
            raise HTTPException(status_code=404, detail="AI model not found.")
        session.delete(model)
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/add_prompt", response_class=HTMLResponse)
def add_prompt(
    request: Request, 
    prompt_text: str = Form(...), 
    domain_id: Optional[int] = Form(None),
    prompt_type: str = Form(...)
):
    """
    Add a new prompt.
    """
    if not "{context}" in prompt_text:
        prompt_text = prompt_text + (
            "Consider the following user-provided "
            "context to seed your response: {context}"
        )
    
    with Session(engine) as session:
        new_prompt = Prompt(
            prompt=prompt_text,
            prompt_type=PromptType(prompt_type)  # Convert string to enum
        )
        if domain_id:
            domain = session.get(Domain, domain_id)
            domain.prompts.append(new_prompt)
        session.add(new_prompt)
        session.commit()
    return RedirectResponse(url=f"/settings?expanded_domain_id={domain_id}&prompt_type={prompt_type}", status_code=303)


@app.post("/settings/delete_prompt/{prompt_id}", response_class=HTMLResponse)
def delete_prompt(
    request: Request,
    prompt_id
):
    """
    Delete an existing prompt by its ID.
    """
    with Session(engine) as session:
        prompt = session.get(Prompt, prompt_id)
        domain_id = prompt.domain_id
        prompt_type = prompt.prompt_type.value
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found.")
        session.delete(prompt)
        session.commit()
    return RedirectResponse(url=f"/settings?expanded_domain_id={domain_id}&prompt_type={prompt_type}", status_code=303)


@app.post("/settings/add_domain", response_class=HTMLResponse)
def add_domain(request: Request, domain_name: str = Form(...)):
    """
    Add a new domain.
    """
    with Session(engine) as session:
        new_domain = Domain(name=domain_name)
        session.add(new_domain)
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/rewrite_prompt/{prompt_id}", response_class=HTMLResponse)
def rewrite_existing_prompt(request: Request, prompt_id: int):
    """
    Rewrite an existing prompt using AI and feedback from its TextOutputs.
    """
    with Session(engine) as session:
        prompt_obj = session.get(Prompt, prompt_id)
        if not prompt_obj:
            raise HTTPException(status_code=404, detail="Prompt not found.")

        model = select_random_model(session)
        if not model or not model.text_output:
            raise HTTPException(status_code=400, detail="No suitable text model available.")

        rewrite_prompt(session, prompt_obj, model)

        return RedirectResponse(
            url=f"/settings?expanded_domain_id={prompt_obj.domain_id}&prompt_type={prompt_obj.prompt_type.value}",
            status_code=303
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)