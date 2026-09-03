from dataclasses import dataclass


@dataclass(slots=True)
class SmsSendResult:
    accepted: bool
    provider_message_id: str | None = None


class SmsProvider:
    async def send_code(self, phone: str, code: str) -> SmsSendResult:
        raise NotImplementedError


class StubSmsProvider(SmsProvider):
    """Development adapter; replace only this adapter after the carrier API is known."""

    async def send_code(self, phone: str, code: str) -> SmsSendResult:
        return SmsSendResult(accepted=True, provider_message_id="stub")
