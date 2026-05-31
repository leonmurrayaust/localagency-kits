"""
localagency/models/client.py
══════════════════════════════
Per-client data models for business profile, brand voice, service catalog, etc.
"""

from __future__ import annotations

from datetime import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class BusinessVertical(str, Enum):
    """Supported trades/service verticals."""
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
    ROOFING = "roofing"
    LANDSCAPING = "landscaping"
    AUTO_REPAIR = "auto_repair"
    DENTAL = "dental"
    SALON = "salon"
    MED_SPA = "med_spa"
    PEST_CONTROL = "pest_control"
    POOL_SERVICE = "pool_service"
    GENERAL_CONTRACTOR = "general_contractor"
    OTHER = "other"


class BrandVoice(BaseModel):
    """Client's brand voice configuration shared across all Kits."""
    greeting_name: str = Field(default="", description="What the AI calls the business, e.g. 'Joe's Plumbing'")
    tone: str = Field(default="friendly_professional", description="friendly_professional | warm | direct | humorous | luxury")
    personality_notes: str = Field(default="", description="Free-text brand voice guidelines")
    catchphrase: str = Field(default="", description="Optional tagline or catchphrase")
    response_style: str = Field(default="concise", description="concise | detailed | conversational")
    avoid_phrases: list[str] = Field(default_factory=list, description="Words/phrases the AI should avoid")


class OperatingHours(BaseModel):
    """Daily operating hours. None = closed."""
    monday: Optional[str] = Field(default="09:00-17:00")
    tuesday: Optional[str] = Field(default="09:00-17:00")
    wednesday: Optional[str] = Field(default="09:00-17:00")
    thursday: Optional[str] = Field(default="09:00-17:00")
    friday: Optional[str] = Field(default="09:00-17:00")
    saturday: Optional[str] = Field(default=None)
    sunday: Optional[str] = Field(default=None)


class ServiceItem(BaseModel):
    """A single service offered by the client."""
    name: str = Field(description="Service name, e.g. 'Water Heater Replacement'")
    description: str = Field(default="")
    price_range: str = Field(default="Call for pricing")
    duration_minutes: Optional[int] = Field(default=None)
    category: str = Field(default="general", description="Service category for booking")


class ServiceCatalog(BaseModel):
    """Full service menu for the client business."""
    services: list[ServiceItem] = Field(default_factory=list)
    default_category: str = Field(default="general")


class ClientProfile(BaseModel):
    """
    Complete client profile — the single source of truth for all Kits.
    Stored in PostgreSQL (warm) with Redis hot cache.
    """
    client_id: str = Field(description="Unique identifier (UUID v7)")
    business_name: str
    vertical: BusinessVertical = BusinessVertical.OTHER
    address: str = Field(default="")
    phone: str = Field(default="", description="Client's business phone number")
    website: str = Field(default="")
    service_area: str = Field(default="Phoenix Metro Area")
    service_area_zip_codes: list[str] = Field(default_factory=list)

    brand_voice: BrandVoice = Field(default_factory=BrandVoice)
    operating_hours: OperatingHours = Field(default_factory=OperatingHours)
    service_catalog: ServiceCatalog = Field(default_factory=ServiceCatalog)

    # Integration tokens — scoped per client
    twilio_phone_sid: Optional[str] = Field(default=None)
    gbp_account_id: Optional[str] = Field(default=None)
    facebook_page_id: Optional[str] = Field(default=None)
    facebook_access_token: Optional[str] = Field(default=None)
    stripe_customer_id: Optional[str] = Field(default=None)
    calendly_link: Optional[str] = Field(default=None)
    gohighlevel_location_id: Optional[str] = Field(default=None)

    # Billing state
    subscription_status: str = Field(default="trialing")  # trialing | active | past_due | canceled
    subscription_id: Optional[str] = Field(default=None)
    mrr: float = Field(default=497.0)

    # Metadata
    created_at: str = Field(default="")
    updated_at: str = Field(default="")
    onboarded_at: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)

    # Preferences
    social_auto_approve: bool = Field(default=False)
    booking_sms_confirm: bool = Field(default=True)
    referral_program_opted_in: bool = Field(default=True)

    model_config = {"extra": "forbid"}
