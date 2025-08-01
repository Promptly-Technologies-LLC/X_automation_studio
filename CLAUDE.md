# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Installation
```bash
# Install UV package manager (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Setup environment
cp example.env .env
# Edit .env with required API keys
```

### Running the Application
```bash
# Start development server
uv run python main.py

# Server runs on http://127.0.0.1:5000
```

### Type Checking
```bash
# Run MyPy type checking
uv run mypy .
```

## Architecture Overview

### Core Application Structure
X_automation_studio is a **FastAPI-based Twitter/X automation platform** that enables LLM-assisted social media marketing. The application combines AI-powered content generation with Twitter API integration for automated posting.

**Technology Stack:**
- **Backend**: FastAPI with Jinja2 templates
- **Database**: SQLite with SQLModel ORM
- **Frontend**: Bootstrap 5 + HTMX for dynamic interactions
- **Authentication**: OAuth 1.0a for Twitter API
- **AI Integration**: LiteLLM with OpenRouter for multi-model access
- **Package Management**: UV (modern Python dependency management)

### Key Components

#### Database Models (`x_automation_studio/models.py`)
- **AIModel**: Stores AI model configurations with text/image capabilities
- **Domain**: Categories for organizing prompts (e.g., "Tech", "Marketing")
- **Prompt**: Template prompts with `{context}` placeholders for AI generation
- **TextOutput/ImageOutput**: Generated content storage
- **Feedback**: User feedback system (+1/-1 scores) for continuous improvement

#### AI Suggestion Engine (`x_automation_studio/suggestion.py`)
The most complex component featuring:
- **Selection Strategies**: Random, weighted (softmax-based), and highest-performing
- **Feedback Integration**: Uses historical feedback to improve future selections
- **Prompt Enhancement**: AI-powered prompt rewriting based on user feedback
- **Text Processing**: Context injection, response cleaning, Twitter character limits

#### Authentication & Twitter Integration
- **OAuth 1.0a**: (`auth.py`) Handles Twitter API authentication
- **Tweet Management**: (`tweet.py`) Tweet posting with media upload support
- **Media Handling**: (`media.py`) Image upload to Twitter's CDN

### Template Architecture
- **base.html**: Bootstrap layout with navigation (Home/Settings)
- **index.html**: Main interface with tweet composer and AI suggestions
- **settings.html**: AI model and prompt management interface
- **suggestion.html**: Dynamic suggestion cards loaded via HTMX

### Environment Configuration
Required environment variables in `.env`:
```bash
X_API_KEY=              # Twitter API key
X_API_SECRET=           # Twitter API secret
X_ACCESS_TOKEN=         # Twitter access token
X_ACCESS_TOKEN_SECRET=  # Twitter access token secret
X_USERNAME=             # Twitter username for link generation
OPENROUTER_API_KEY=     # OpenRouter API key for AI models
OPENAI_API_KEY=         # OpenAI API key for image generation
```

### Database Behavior
- **Auto-initialization**: Database tables and default data created on startup
- **Seeding**: Default AI models and prompts automatically populated
- **Feedback Loop**: User interactions stored to improve future AI selections

### AI Integration Patterns
- **Model Agnostic**: Uses LiteLLM to support 100+ AI models via OpenRouter
- **Retry Logic**: Built-in retry mechanisms for AI API failures
- **Response Processing**: Handles various AI response formats and cleans output
- **Context Injection**: Dynamic prompt templating with user-provided context

### Key Workflows
1. **Suggestion Generation**: Context → Model/Prompt Selection → AI Generation → Processing → Display
2. **Tweet Posting**: Compose → OAuth → Media Upload (optional) → Tweet Post → Feedback
3. **Feedback Loop**: User Rating → Database Storage → Future Selection Weighting
4. **Prompt Improvement**: Feedback Analysis → AI-powered Prompt Rewriting → Database Update

### Development Notes
- **No Tests**: Currently no test suite - tests should be added for core functionality
- **SQLite Database**: Single-file database (`database.db`) - good for development, consider migration for production
- **HTMX Integration**: Frontend interactivity handled server-side with HTMX rather than client-side JavaScript
- **OAuth State**: Uses session files for Twitter authentication state management
- **Type Safety**: MyPy type checking enabled - run `uv run mypy .` before commits