"""Optional alert delivery transports. SMS and FCM require external credentials."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class DeliveryRequest:
    device_id: str
    channel: Literal['official', 'risk', 'daily', 'rain']
    title: str
    body: str
    event: str = ''
    severity: str = 'unknown'
    expires: str | None = None


@dataclass
class DeliveryResult:
    transport: str
    status: Literal['sent', 'disabled', 'failed']
    message: str
    delivered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AlertDeliveryProvider(ABC):
    transport = 'abstract'

    @abstractmethod
    async def send(self, request: DeliveryRequest) -> DeliveryResult: ...


class DisabledSmsProvider(AlertDeliveryProvider):
    transport = 'sms'

    async def send(self, request: DeliveryRequest) -> DeliveryResult:
        return DeliveryResult(
            transport=self.transport,
            status='disabled',
            message='SMS delivery is not configured. Set SMS_PROVIDER credentials to enable.',
        )


class DisabledFcmProvider(AlertDeliveryProvider):
    transport = 'fcm'

    async def send(self, request: DeliveryRequest) -> DeliveryResult:
        return DeliveryResult(
            transport=self.transport,
            status='disabled',
            message='Firebase Cloud Messaging is not configured. Set FIREBASE credentials to enable push alerts.',
        )


delivery_chain: list[AlertDeliveryProvider] = [DisabledFcmProvider(), DisabledSmsProvider()]
