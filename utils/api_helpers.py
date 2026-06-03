import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


def publish_linkedin_post(text: str) -> dict:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    person_urn = os.getenv("LINKEDIN_PERSON_URN")

    if not token or not person_urn:
        raise EnvironmentError("LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN must be set in .env")

    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    response = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    post_id = response.headers.get("x-restli-id", "")
    return {
        "status": "published",
        "post_id": post_id,
        "url": f"https://www.linkedin.com/feed/update/{post_id}",
    }


def publish_instagram_post(caption: str, image_url: Optional[str] = None) -> dict:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")

    if not token or not account_id:
        raise EnvironmentError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID must be set in .env"
        )

    # Step 1: Create media container
    container_params: dict = {
        "caption": caption,
        "access_token": token,
    }
    if image_url:
        container_params["image_url"] = image_url
    else:
        # Text-only not supported on Instagram — requires an image
        raise ValueError("Instagram posts require an image_url. Provide a hosted image URL.")

    container_response = requests.post(
        f"https://graph.facebook.com/v18.0/{account_id}/media",
        params=container_params,
        timeout=30,
    )
    container_response.raise_for_status()
    creation_id = container_response.json().get("id")

    # Step 2: Publish the container
    time.sleep(2)
    publish_response = requests.post(
        f"https://graph.facebook.com/v18.0/{account_id}/media_publish",
        params={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    publish_response.raise_for_status()
    media_id = publish_response.json().get("id", "")
    return {
        "status": "published",
        "media_id": media_id,
        "url": f"https://www.instagram.com/p/{media_id}/",
    }
