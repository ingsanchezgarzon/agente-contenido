import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


def search_tavily(query: str, max_results: int = 5) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise EnvironmentError("TAVILY_API_KEY not set in .env")

    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_raw_content": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": r.get("content", "")[:500],
            "date": r.get("published_date"),
        }
        for r in results
    ]


def search_serper(query: str, max_results: int = 5) -> list[dict]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise EnvironmentError("SERPER_API_KEY not set in .env")

    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": max_results},
        timeout=30,
    )
    response.raise_for_status()
    organic = response.json().get("organic", [])
    return [
        {
            "url": r.get("link", ""),
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
            "date": r.get("date"),
        }
        for r in organic
    ]


def search(query: str, max_results: int = 5) -> list[dict]:
    if os.getenv("TAVILY_API_KEY"):
        return search_tavily(query, max_results)
    elif os.getenv("SERPER_API_KEY"):
        return search_serper(query, max_results)
    else:
        raise EnvironmentError("No search API key found. Set TAVILY_API_KEY or SERPER_API_KEY in .env")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "SCI LMNP France expat 2024"
    print(f"Searching: {query}\n")
    results = search(query, max_results=3)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print(f"   {r['snippet'][:150]}...")
        print()
