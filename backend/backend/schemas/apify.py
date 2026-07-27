"""Validated, cost-bounded request models for explicit Apify actor endpoints."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TwitterProfileRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    max_items: int = Field(default=5, ge=1, le=40)
    get_replies: bool = False
    min_reply_count: int = Field(default=10, ge=0)
    get_about_data: bool = False


class TwitterSearchRequest(BaseModel):
    search_terms: list[str] = Field(default_factory=list, max_length=50)
    twitter_handles: list[str] = Field(default_factory=list, max_length=50)
    start_urls: list[str] = Field(default_factory=list, max_length=50)
    conversation_ids: list[str] = Field(default_factory=list, max_length=50)
    max_items: int = Field(default=10, ge=1, le=50)
    tweet_language: str | None = Field(default=None, min_length=2, max_length=10)
    sort: Literal["Top", "Latest", "Latest + Top"] = "Latest"
    author: str | None = Field(default=None, max_length=50)
    in_reply_to: str | None = Field(default=None, max_length=50)
    mentioning: str | None = Field(default=None, max_length=50)
    include_search_terms: bool = False

    @model_validator(mode="after")
    def require_target(self) -> "TwitterSearchRequest":
        if not any(
            (
                self.search_terms,
                self.twitter_handles,
                self.start_urls,
                self.conversation_ids,
                self.author,
                self.in_reply_to,
                self.mentioning,
            )
        ):
            raise ValueError("At least one Twitter search target is required")
        return self


class RedditCollectRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=20)
    search_query: str | None = Field(default=None, min_length=1, max_length=500)
    search_subreddit: str | None = Field(default=None, min_length=1, max_length=100)
    sort: Literal["hot", "new", "top", "rising", "relevance"] = "hot"
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = "week"
    max_posts_per_source: int = Field(default=50, ge=1, le=500)
    include_comments: bool = False
    max_comments_per_post: int = Field(default=100, ge=1, le=1000)
    comment_depth: int = Field(default=3, ge=1, le=10)
    filter_keywords: list[str] = Field(default_factory=list, max_length=100)
    filter_keyword_mode: Literal["any", "titleOnly", "all", "exactPhrase"] = "any"
    deduplicate_posts: bool = True

    @model_validator(mode="after")
    def require_target(self) -> "RedditCollectRequest":
        if not self.urls and not (self.search_query or "").strip():
            raise ValueError("At least one Reddit URL or search query is required")
        return self


class LinkedInBulkRequest(BaseModel):
    action: Literal["get-profiles", "get-companies"] = "get-profiles"
    keywords: list[str] = Field(..., min_length=1, max_length=50)
    query_mode: Literal["keyword", "name", "url"] = "keyword"
    limit: int = Field(default=5, ge=1, le=100)
    locations: list[str] = Field(default_factory=list, max_length=25)


class LinkedInPostsSearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=500)
    sort_type: Literal["relevance", "date_posted"] = "relevance"
    page_number: int = Field(default=1, ge=1)
    date_filter: Literal["", "past-1h", "past-24h", "past-week", "past-month"] = ""
    limit: int = Field(default=50, ge=1, le=50)
    total_posts: int | None = Field(default=None, ge=1, le=10_000)
    company_urns: str | None = Field(default=None, max_length=2000)
    author_company_urns: str | None = Field(default=None, max_length=2000)
    author_industry_urns: str | None = Field(default=None, max_length=2000)
    author_job_title: str | None = Field(default=None, max_length=200)
    member_urns: str | None = Field(default=None, max_length=5000)


class FacebookPagesRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=50)


class FacebookPostsRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=50)
    results_limit: int = Field(default=20, ge=1, le=500)
    caption_text: bool = False
    only_posts_newer_than: str | None = Field(default=None, max_length=100)
    only_posts_older_than: str | None = Field(default=None, max_length=100)
