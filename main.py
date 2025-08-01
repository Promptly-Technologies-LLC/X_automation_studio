# main.py
import os
import logging
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.templating import _TemplateResponse
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from urllib.parse import urlencode

from x_automation_studio.models import AIModel, Prompt, TextOutput, Feedback, Domain, PromptType, engine, create_tables, seed_db
from x_automation_studio.tweet import submit_tweet, handle_tweet_response
from x_automation_studio.utils import get_temp_dir
from x_automation_studio.suggestion import get_suggestion, create_output_record, rewrite_prompt, select_random_model

# Configure logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv(override=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    seed_db()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def show_form(request: Request, message: Optional[str] = None, tweet_link: Optional[str] = None) -> _TemplateResponse:
    """
    Serve a basic form (index.html) for posting tweets.
    Displays messages passed as query parameters.
    """
    with Session(engine) as session:
        domains = session.exec(select(Domain)).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "domains": domains,
            "message": message,
            "tweet_link": tweet_link
        }
    )

@app.post("/tweet", response_class=HTMLResponse, response_model=None)
async def post_tweet(
    request: Request,
    text: str = Form(...),
    image: Optional[UploadFile] = File(None)
) -> RedirectResponse:
    """
    Handle the form submission by directly posting the tweet using OAuth 1.0a credentials.
    """
    logger.info("Processing tweet request: text='%s', has_image=%s", text, bool(image))
    
    image_path = None
    if image and image.filename:
        temp_dir = get_temp_dir()
        image_path = os.path.join(temp_dir, image.filename)
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())
        logger.info("Saved uploaded image to: %s", image_path)

    try:
        response = submit_tweet(text=text, media_path=image_path)
        message, tweet_link = handle_tweet_response(response)
    except Exception as e:
        logger.error("Error posting tweet: %s", str(e))
        message = f"Error posting tweet: {str(e)}"
        tweet_link = None

    # Redirect to the main page with results in query parameters
    params = {"message": message}
    if tweet_link:
        params["tweet_link"] = tweet_link
    
    return RedirectResponse(url=f"/?{urlencode(params)}", status_code=303)


# --- All other endpoints remain the same ---
# /suggestions, /feedback, /settings/*

@app.get("/suggestions", response_class=HTMLResponse)
async def get_tweet_suggestion(
    request: Request,
    background_tasks: BackgroundTasks,
    context: str = "",
    mode: str = "weighted",
    domain_id: int | str = ""
) -> _TemplateResponse:
    suggestion: dict = get_suggestion(context, mode, domain_id=domain_id)
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
    with Session(engine) as session:
        output = session.get(TextOutput, textoutput_id)
        if output is None:
            return "Feedback submission failed: output record not found."
        output.feedback.append(Feedback(score=score, comment=comment))
        session.add(output)
        session.commit()
    return "<div class='alert alert-success'>Feedback recorded. Thank you!</div>"

@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    expanded_domain_id: Optional[int] = None,
    prompt_type: Optional[str] = "text"
) -> _TemplateResponse:
    with Session(engine) as session:
        models = session.exec(select(AIModel)).all()
        domains = session.exec(select(Domain).options(selectinload(Domain.prompts))).all()
        prompts = session.exec(select(Prompt)).all()
    return templates.TemplateResponse("settings.html", {
        "request": request, "models": models, "domains": domains, "prompts": prompts,
        "expanded_domain_id": expanded_domain_id, "prompt_type": prompt_type
    })

@app.post("/settings/add_model", response_class=HTMLResponse)
def add_model(request: Request, model_name: str = Form(...), text_output: bool = Form(False), image_output: bool = Form(False)):
    if not (text_output or image_output):
        raise HTTPException(status_code=400, detail="Model must support at least one output type (text or image)")
    with Session(engine) as session:
        new_model = AIModel(name=model_name, text_output=text_output, image_output=image_output)
        session.add(new_model)
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/delete_model/{model_id}", response_class=HTMLResponse)
def delete_model(request: Request, model_id: int):
    with Session(engine) as session:
        model = session.get(AIModel, model_id)
        if not model: raise HTTPException(status_code=404, detail="AI model not found.")
        session.delete(model)
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/add_prompt", response_class=HTMLResponse)
def add_prompt(request: Request, prompt_text: str = Form(...), domain_id: Optional[int] = Form(None), prompt_type: str = Form(...)):
    if "{context}" not in prompt_text:
        prompt_text += " Consider the following user-provided context to seed your response: {context}"
    with Session(engine) as session:
        new_prompt = Prompt(prompt=prompt_text, prompt_type=PromptType(prompt_type))
        if domain_id:
            domain = session.get(Domain, domain_id)
            domain.prompts.append(new_prompt)
        session.add(new_prompt)
        session.commit()
    return RedirectResponse(url=f"/settings?expanded_domain_id={domain_id}&prompt_type={prompt_type}", status_code=303)

@app.post("/settings/delete_prompt/{prompt_id}", response_class=HTMLResponse)
def delete_prompt(request: Request, prompt_id):
    with Session(engine) as session:
        prompt = session.get(Prompt, prompt_id)
        domain_id = prompt.domain_id
        prompt_type = prompt.prompt_type.value
        if not prompt: raise HTTPException(status_code=404, detail="Prompt not found.")
        session.delete(prompt)
        session.commit()
    return RedirectResponse(url=f"/settings?expanded_domain_id={domain_id}&prompt_type={prompt_type}", status_code=303)

@app.post("/settings/add_domain", response_class=HTMLResponse)
def add_domain(request: Request, domain_name: str = Form(...)):
    with Session(engine) as session:
        new_domain = Domain(name=domain_name)
        session.add(new_domain)
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/rewrite_prompt/{prompt_id}", response_class=HTMLResponse)
def rewrite_existing_prompt(request: Request, prompt_id: int):
    with Session(engine) as session:
        prompt_obj = session.get(Prompt, prompt_id)
        if not prompt_obj: raise HTTPException(status_code=404, detail="Prompt not found.")
        model = select_random_model(session)
        if not model or not model.text_output: raise HTTPException(status_code=400, detail="No suitable text model available.")
        rewrite_prompt(session, prompt_obj, model)
        return RedirectResponse(url=f"/settings?expanded_domain_id={prompt_obj.domain_id}&prompt_type={prompt_obj.prompt_type.value}", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)