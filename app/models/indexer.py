from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlmodel import Column, Field, JSON, SQLModel


class IndexerState(SQLModel, table=True):
    __tablename__ = "indexer_state"

    contract_name: str = Field(primary_key=True)
    contract_address: str
    last_scanned_block: int = Field(default=0)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class IndexedEvent(SQLModel, table=True):
    __tablename__ = "indexed_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    contract_name: str = Field(index=True)
    contract_address: str = Field(index=True)
    event_name: str = Field(index=True)
    block_number: int = Field(index=True)
    transaction_hash: str = Field(index=True)
    log_index: int
    args: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CompetitionRecord(SQLModel, table=True):
    __tablename__ = "competitions"

    id: int = Field(primary_key=True)
    organization: str = Field(index=True)
    name: str
    category: str
    end_at: int
    certificate_cid: str
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WinnerRecord(SQLModel, table=True):
    __tablename__ = "winners"

    id: Optional[int] = Field(default=None, primary_key=True)
    winner_id: int = Field(index=True)
    participant: str = Field(index=True)
    competition_id: int = Field(index=True)
    participant_winner_id: int
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CertificateParticipantRecord(SQLModel, table=True):
    __tablename__ = "certificate_participants"

    id: Optional[int] = Field(default=None, primary_key=True)
    token_id: int = Field(index=True)
    participant: str = Field(index=True)
    competition_id: int = Field(index=True)
    uri: str
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CertificateParticipantWinnerRecord(SQLModel, table=True):
    __tablename__ = "certificate_participant_winners"

    id: Optional[int] = Field(default=None, primary_key=True)
    token_id: int = Field(index=True)
    participant: str = Field(index=True)
    competition_id: int = Field(index=True)
    winner_id: int = Field(index=True)
    uri: str
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class FeeSettingRecord(SQLModel, table=True):
    __tablename__ = "fee_settings"

    fee_id: int = Field(primary_key=True)
    treasury_fee: str
    title: str
    description: str
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ListingTokenPrizeRecord(SQLModel, table=True):
    __tablename__ = "listing_token_prizes"

    id: Optional[int] = Field(default=None, primary_key=True)
    listing_token_prize_id: int = Field(index=True)
    token_address: str = Field(index=True)
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SignerAddressRecord(SQLModel, table=True):
    __tablename__ = "signer_addresses"

    id: Optional[int] = Field(default=None, primary_key=True)
    contract_name: str = Field(index=True)
    signer_address: str = Field(index=True)
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TreasuryPlatformRecord(SQLModel, table=True):
    __tablename__ = "treasury_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_type: str = Field(index=True)
    token_address: Optional[str] = Field(default=None, index=True)
    sender: str = Field(index=True)
    amount: str
    transaction_hash: str
    block_number: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
