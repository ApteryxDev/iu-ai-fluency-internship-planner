"""The records used for advertisements, courses, study sessions and research.

Field names match the earlier app so existing JSON exports still work.
"""
from __future__ import annotations
import json
import math
import re
import uuid
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime, timezone
from typing import Any
from .config import CONFIG

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def identifier() -> str:
    return uuid.uuid4().hex

def text(value: Any, limit: int | None=None) -> str:
    if limit is None:
        limit = CONFIG['limits']['text_characters']
    if value is None:
        return ''
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    return value[:limit]

def safe_url(value: Any) -> str:
    value = text(value, CONFIG['limits']['url_characters']).strip()
    if not value:
        return ''
    if re.fullmatch('https?://[^\\s]+', value, flags=re.IGNORECASE):
        return value
    raise ValueError('Source URL must start with http:// or https:// and contain no spaces.')

def valid_hours(value: Any, allow_zero: bool=False) -> float:
    try:
        if isinstance(value, bool):
            raise TypeError('Boolean value is not a number.')
        hours = float(value)
    except (ValueError, TypeError):
        raise ValueError('Preparation hours must be a number.') from None
    maximum = CONFIG['learning']['maximum_preparation_hours']
    if not math.isfinite(hours) or hours < 0 or (hours == 0 and (not allow_zero)) or (hours > maximum):
        raise ValueError(f'Preparation hours must be between 0 and {maximum}; scheduling needs more than 0.')
    return hours

@dataclass
class Record:
    """Convert dataclass objects to and from the project's JSON structure."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]):
        known = {f.name for f in fields(cls)}
        return cls(**{key: val for key, val in value.items() if key in known})

@dataclass
class Advertisement(Record):
    id: str
    title: str
    employer: str = ''
    location: str = ''
    duration: str = ''
    url: str = ''
    original_text: str = ''
    requirements: str = ''
    review: str = ''
    selection_reason: str = ''
    retrieved_at: str = ''
    selected: bool = False
    verified: bool = False
    origin: str = 'manual'
    research_id: str = ''

    @property
    def requirement_lines(self) -> list[str]:
        """Split the requirements as entered, one line at a time."""
        return [line.strip(' -•\t') for line in self.requirements.splitlines() if line.strip(' -•\t')]

@dataclass
class LearningOption(Record):
    id: str
    skill: str
    jobs: str = ''
    certification: str = ''
    issuer: str = ''
    kind: str = ''
    difficulty: str = ''
    duration: str = ''
    hours: float = 0.0
    prerequisites: str = ''
    url: str = ''
    rationale: str = ''
    recognition: str = ''
    alternatives: str = ''
    review: str = ''
    approved: bool = False
    research_id: str = ''
    related_advertisement_ids: list[str] = field(default_factory=list)

@dataclass
class StudySession(Record):
    id: str
    skill_id: str
    week: int
    title: str
    jobs: str
    skill: str
    certification: str
    difficulty: str
    resource: str
    start: str
    end: str
    hours: float
    evidence: str
    rationale: str
    status: str

@dataclass
class ResearchRecord(Record):
    id: str
    kind: str
    date: str
    prompt: str
    model: str = ''
    output: str = ''
    review: str = ''
    citations: list[dict] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)
    status: str = 'pending'
    summary: str = ''
    limitations: str = ''
    error: str = ''
    configuration_hash: str = ''
    configuration_snapshot: dict = field(default_factory=dict)

def ad_record(item: dict[str, Any], origin: str = 'manual') -> dict:
    """Create an advertisement. New records always start unverified."""
    short_limit = CONFIG['limits']['short_text_characters']
    title = text(item.get('title'), short_limit).strip()
    if not title:
        raise ValueError('An advertisement title is required.')

    advertisement = Advertisement(
        id=identifier(),
        title=title,
        employer=text(item.get('employer'), short_limit),
        location=text(item.get('location'), short_limit),
        duration=text(item.get('duration'), short_limit),
        url=safe_url(item.get('url')),
        original_text=text(item.get('original_text')),
        requirements=text(item.get('requirements')),
        review=text(item.get('review')),
        selection_reason=text(item.get('selection_reason')),
        retrieved_at=text(item.get('retrieved_at'), 100) or now(),
        origin=origin,
    )
    return advertisement.to_dict()


def skill_record(item: dict[str, Any]) -> dict:
    """Create a learning option and leave approval to the user."""
    if not text(item.get('skill')).strip():
        raise ValueError('A skill name is required.')

    limit = CONFIG['limits']['skill_text_characters']
    fields_to_copy = (
        'skill', 'jobs', 'certification', 'issuer', 'kind', 'difficulty',
        'duration', 'prerequisites', 'rationale', 'recognition',
        'alternatives', 'review',
    )
    details = {field_name: text(item.get(field_name), limit) for field_name in fields_to_copy}

    linked_ads = item.get('related_advertisement_ids', [])
    if not isinstance(linked_ads, list) or any(
        not isinstance(ad_id, str) for ad_id in linked_ads
    ):
        raise ValueError('Related advertisement IDs must be a list of strings.')

    option = LearningOption(
        id=identifier(),
        **details,
        hours=valid_hours(item.get('hours') or 0, True),
        url=safe_url(item.get('url')),
        related_advertisement_ids=list(dict.fromkeys(linked_ads)),
    )
    return option.to_dict()
