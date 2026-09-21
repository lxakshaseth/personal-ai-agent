"""
Tests for FastRouter deterministic intent matching and conversational responses.
"""
import pytest
from app.agent.fast_router import FastRouter, ResponseMode


def test_fast_router_greetings():
    for phrase in ["Hi", "Hello", "Hey Nova", "hey", "hello there", "good morning"]:
        match = FastRouter.match(phrase)
        assert match.matched is True, f"Failed on {phrase}"
        assert match.mode == ResponseMode.CHAT
        assert match.direct_response is not None
        assert len(match.direct_response) > 0


def test_fast_router_open_url():
    match = FastRouter.match("open youtube")
    assert match.matched is True
    assert match.mode == ResponseMode.COMMAND
    assert match.tool_name == "open_url"
    assert match.arguments["url"] == "https://www.youtube.com"

    match = FastRouter.match("open github.com")
    assert match.matched is True
    assert match.tool_name == "open_url"
    assert "github.com" in match.arguments["url"]


def test_fast_router_open_apps():
    match = FastRouter.match("open notepad")
    assert match.matched is True
    assert match.tool_name == "open_application"
    assert match.arguments["app_name"] == "Notepad"

    match = FastRouter.match("launch VS Code")
    assert match.matched is True
    assert match.tool_name == "open_application"
    assert match.arguments["app_name"] == "VS Code"


def test_fast_router_folder_and_screenshot():
    match = FastRouter.match("open downloads")
    assert match.matched is True
    assert match.tool_name == "open_folder"

    match = FastRouter.match("take a screenshot")
    assert match.matched is True
    assert match.tool_name == "take_screenshot"


def test_fast_router_youtube_search():
    match = FastRouter.match("search youtube for React tutorial")
    assert match.matched is True
    assert match.tool_name == "open_url"
    assert "react+tutorial" in match.arguments["url"]


def test_fast_router_unmatched_falls_to_groq():
    # Complex or natural-language commands should not be fast-routed
    for phrase in [
        "Write a Python script that scrapes headlines",
        "Find a React tutorial on YouTube, open VS Code, and create a folder called ReactPractice",
        "Open the website where I usually watch coding tutorials",
    ]:
        match = FastRouter.match(phrase)
        assert match.matched is False, f"Should not match {phrase}"


def test_is_knowledge_query():
    from app.agent.fast_router import is_knowledge_query

    # Should match as knowledge queries
    positive_cases = [
        "explain the concept of the machine learning",
        "what is quantum computing",
        "how does a neural network work",
        "why is the sky blue",
        "tell me about Albert Einstein",
        "describe the process of photosynthesis",
        "define polymorphism in python",
        "can you explain gradient descent",
    ]
    for q in positive_cases:
        assert is_knowledge_query(q) is True, f"Failed on positive case: {q}"

    # Should NOT match as knowledge queries (contain tool/action signals or are short commands)
    negative_cases = [
        "open whatsapp and message Aniket",
        "open notepad",
        "create a file named notes.txt",
        "search youtube for lo-fi beats",
        "take a screenshot",
        "lock the computer",
        "hello",
    ]
    for q in negative_cases:
        assert is_knowledge_query(q) is False, f"Failed on negative case: {q}"
