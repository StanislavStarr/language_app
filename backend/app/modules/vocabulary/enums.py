from enum import StrEnum


class SourceType(StrEnum):
    MANUAL = "manual"
    BOOK = "book"


class EnrichmentStatus(StrEnum):
    PENDING = "pending"
    ENRICHING = "enriching"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
