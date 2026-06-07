"""
Seed module for avry-blog service.

Seeds a welcome blog post on startup when the blog_posts table is empty.
This provides an introductory post about Aivory for first-time visitors.
"""

import logging
from datetime import datetime, timezone

from app.database.connection import get_pool
from app.services.post_service import create_post

logger = logging.getLogger(__name__)

WELCOME_POST_TITLE = "Welcome to Aivory: Your AI-Powered Business Automation Platform"

WELCOME_POST_BODY = {
    "blocks": [
        {
            "type": "heading",
            "level": 1,
            "text": "Welcome to Aivory"
        },
        {
            "type": "paragraph",
            "text": "We're thrilled to have you here! Aivory is an AI-powered business automation platform designed to help businesses of all sizes streamline their workflows, reduce manual effort, and unlock new levels of productivity."
        },
        {
            "type": "heading",
            "level": 2,
            "text": "What is Aivory?"
        },
        {
            "type": "paragraph",
            "text": "Aivory is a comprehensive platform that brings the power of artificial intelligence to your everyday business operations. Whether you need to automate repetitive tasks, generate intelligent insights from your data, or build custom workflows that adapt to your unique processes, Aivory provides the tools to make it happen."
        },
        {
            "type": "paragraph",
            "text": "Our platform combines cutting-edge AI models with an intuitive interface, so you can focus on growing your business while Aivory handles the heavy lifting behind the scenes."
        },
        {
            "type": "heading",
            "level": 2,
            "text": "How to Use Aivory"
        },
        {
            "type": "paragraph",
            "text": "Getting started with Aivory is simple. Follow these steps to begin automating your business:"
        },
        {
            "type": "paragraph",
            "text": "Step 1: Create your account — Sign up on the platform and set up your workspace. The onboarding process guides you through initial configuration."
        },
        {
            "type": "paragraph",
            "text": "Step 2: Define your workflows — Use our visual workflow builder to map out the processes you want to automate. Drag and drop components, set triggers, and configure actions."
        },
        {
            "type": "paragraph",
            "text": "Step 3: Connect your tools — Integrate Aivory with the services you already use. Our platform supports a wide range of third-party integrations to fit seamlessly into your existing stack."
        },
        {
            "type": "paragraph",
            "text": "Step 4: Activate and monitor — Launch your automations and track their performance in real time through the dashboard. Adjust and optimize as your needs evolve."
        },
        {
            "type": "heading",
            "level": 2,
            "text": "Benefits of Using Aivory"
        },
        {
            "type": "paragraph",
            "text": "Save time and reduce costs — Automate repetitive tasks that consume hours of manual work every week. Redirect your team's energy toward high-value activities that drive growth."
        },
        {
            "type": "paragraph",
            "text": "Scale effortlessly — As your business grows, Aivory scales with you. Add new workflows, handle increased volume, and expand your automation capabilities without additional overhead."
        },
        {
            "type": "paragraph",
            "text": "Make smarter decisions — Leverage AI-driven insights to inform your strategy. Aivory analyzes patterns in your data and surfaces actionable recommendations."
        },
        {
            "type": "paragraph",
            "text": "Stay in control — Full visibility into every automated process. Monitor, pause, or adjust workflows at any time through a centralized dashboard."
        },
        {
            "type": "heading",
            "level": 2,
            "text": "Ready to Get Started?"
        },
        {
            "type": "paragraph",
            "text": "We invite you to explore what Aivory can do for your business. Whether you're looking to automate a single process or transform your entire operation, we're here to support you every step of the way. Sign up today and experience the future of business automation."
        }
    ]
}

WELCOME_POST_EXCERPT = (
    "Discover how Aivory, an AI-powered business automation platform, "
    "can help you streamline workflows, reduce manual effort, and scale your business."
)


async def seed_welcome_post() -> None:
    """
    Seed the database with a welcome blog post if the blog_posts table is empty.

    This function checks if any blog posts exist. If the table is empty, it creates
    an introductory post about Aivory with published status and the current timestamp.
    """
    pool = await get_pool()
    if pool is None:
        logger.warning("Cannot seed welcome post: database pool not available")
        return

    try:
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM blog_posts")

        if count > 0:
            logger.info(f"Blog posts table already has {count} post(s), skipping seed")
            return

        # Create the welcome post with published status
        post = await create_post(
            title=WELCOME_POST_TITLE,
            body=WELCOME_POST_BODY,
            author_name="Aivory Team",
            excerpt=WELCOME_POST_EXCERPT,
            status="published",
        )

        if post:
            logger.info(f"✓ Welcome blog post seeded successfully (slug: {post.slug})")
        else:
            logger.error("Failed to seed welcome blog post")

    except Exception as e:
        logger.error(f"Error seeding welcome blog post: {e}")
