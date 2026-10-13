"""
Shared data models — canonical internal schema.

These are NOT the raw IRSA VOTable columns; we normalise to stable fields
and carry enough provenance to reproduce any query.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DataRelease(str, Enum):
    QR2 = "spherex_qr2"
    QR3 = "spherex_qr3"
    UNKNOWN = "unknown"


class ObservationRecord(BaseModel):
    """One SPHEREx Level-2 Spectral Image that covers the queried position."""

    obs_id: str = Field(..., description="Original archive observation identifier")
    collection: str = Field(..., description="IRSA SIA collection name, e.g. spherex_qr3")
    access_url: str = Field(..., description="Full URL to the on-premises FITS file")
    obs_start: Optional[datetime] = Field(None, description="Observation start (UTC)")
    obs_stop: Optional[datetime] = Field(None, description="Observation stop (UTC)")
    mjd_start: Optional[float] = Field(None, description="MJD start (TDB)")
    mjd_stop: Optional[float] = Field(None, description="MJD stop (TDB)")
    ra_center: Optional[float] = Field(None, description="Image centre RA (deg, ICRS)")
    dec_center: Optional[float] = Field(None, description="Image centre Dec (deg, ICRS)")
    em_min: Optional[float] = Field(None, description="Minimum wavelength covered (m)")
    em_max: Optional[float] = Field(None, description="Maximum wavelength covered (m)")
    em_min_um: Optional[float] = Field(None, description="Minimum wavelength (µm)")
    em_max_um: Optional[float] = Field(None, description="Maximum wavelength (µm)")
    exptime: Optional[float] = Field(None, description="Exposure time (s)")
    calib_level: Optional[int] = Field(None, description="IVOA calibration level")
    instrument: Optional[str] = None
    facility: Optional[str] = None
    s_region: Optional[str] = Field(None, description="Spatial footprint (STC-S)")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("em_min_um", mode="before")
    @classmethod
    def calc_em_min_um(cls, v, info):
        if v is None and info.data.get("em_min"):
            return round(info.data["em_min"] * 1e6, 4)
        return v

    @field_validator("em_max_um", mode="before")
    @classmethod
    def calc_em_max_um(cls, v, info):
        if v is None and info.data.get("em_max"):
            return round(info.data["em_max"] * 1e6, 4)
        return v


class TimelineResponse(BaseModel):
    ra: float
    dec: float
    radius_deg: float
    observations: list[ObservationRecord]
    releases_queried: list[str]
    total: int
    warnings: list[str] = []
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class PreviewRecord(BaseModel):
    obs_id: str
    collection: str
    ra: float
    dec: float
    size_deg: float
    preview_url: str = Field(..., description="Backend URL serving the PNG preview")
    obs_start: Optional[datetime] = None
    mjd_start: Optional[float] = None
    em_min_um: Optional[float] = None
    em_max_um: Optional[float] = None
    stretch: str = "asinh"
    quality_warnings: list[str] = []
    attribution: str = (
        "SPHEREx data from IRSA/IPAC. DOI: 10.26131/IRSA652 (QR2), 10.26131/IRSA662 (QR3). "
        "JPL/Caltech/NASA."
    )


class CompareResponse(BaseModel):
    first: ObservationRecord
    second: ObservationRecord
    compatible: bool
    compatibility_notes: list[str]
    first_preview_url: str
    second_preview_url: str
    time_delta_days: Optional[float] = None
    wavelength_overlap_um: Optional[list[float]] = None


class HealthResponse(BaseModel):
    status: str
    irsa_reachable: bool
    cache_entries: int
    version: str = "1.0.0"
