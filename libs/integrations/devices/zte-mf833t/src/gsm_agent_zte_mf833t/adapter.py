"""Read-only MF833T goform API; no vendor payload crosses this boundary."""

import asyncio
import re
from datetime import UTC, datetime
from importlib.metadata import version

import httpx
from gsm_agent_core.capabilities.catalog import (
    DEVICE_STATUS_READ,
    CapabilityBinding,
    CapabilityKey,
    CapabilitySet,
)
from gsm_agent_core.domain.devices import (
    AdapterManifest,
    Availability,
    CellularDeviceId,
    Compatibility,
    CompatibilityEvidence,
    DeviceDescriptor,
    DeviceModel,
    DeviceObservation,
    DeviceReadIssue,
    DeviceStatus,
    DeviceVariant,
    VerificationKind,
)

from gsm_agent_zte_mf833t.settings import ZteMf833tSettings

REFERENCE_VARIANT = DeviceVariant("BD_WANAMARMF833TV1.0.0B04", "djtA", "http-management")
MANIFEST = AdapterManifest(
    adapter_id="zte-mf833t",
    version=version("gsm-agent-zte-mf833t"),
    model=DeviceModel("ZTE", "MF833T"),
    capabilities=(DEVICE_STATUS_READ.id,),
    required_transports=("http-management",),
    runtime_dependencies=("httpx>=0.28.1",),
    compatibility_evidence=(
        CompatibilityEvidence(
            REFERENCE_VARIANT,
            VerificationKind.DEVICE_VERIFICATION,
            "Read-only MF833T HTTP inspection verified 2026-10-16; see adapter README verification notes",
            capabilities=(DEVICE_STATUS_READ.id,),
        ),
    ),
)
_COMMAND = "wa_inner_version,hardware_version,network_provider,network_type,signalbar"


class _ReadFailure(Exception):
    def __init__(self, issue: DeviceReadIssue) -> None:
        self.issue = issue


def _text(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 256:
        raise _ReadFailure(DeviceReadIssue.INVALID_RESPONSE)
    return value.strip() or None


class ZteMf833tDevice:
    def __init__(
        self,
        device_id: CellularDeviceId,
        settings: ZteMf833tSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._device_id = device_id
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/"),
            timeout=settings.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            headers={"Referer": settings.base_url.rstrip("/") + "/index.html"},
            transport=transport,
        )
        self._capabilities = CapabilitySet(CapabilityBinding(DEVICE_STATUS_READ, self))

    @property
    def device_id(self) -> CellularDeviceId:
        return self._device_id

    @property
    def manifest(self) -> AdapterManifest:
        return MANIFEST

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return self._capabilities.get(key)

    async def describe(self) -> DeviceDescriptor:
        observation, _ = await self._inspect()
        return DeviceDescriptor(self.device_id, self.manifest, observation)

    async def read(self) -> DeviceStatus:
        _, status = await self._inspect()
        return status

    async def close(self) -> None:
        await self._client.aclose()

    async def _inspect(self) -> tuple[DeviceObservation, DeviceStatus]:
        if self._client.is_closed:
            raise RuntimeError("ZTE MF833T adapter is closed")
        model: str | None = None
        variant: DeviceVariant | None = None
        compatibility = Compatibility.UNKNOWN
        availability = Availability.UNKNOWN
        issue: DeviceReadIssue | None = None
        provider = network_type = None
        signal = None
        try:
            # HTTPX timeouts bound phases; this budget bounds both entire requests.
            async with asyncio.timeout(self._settings.timeout_seconds):
                config = await self._client.get("/js/config/config.js")
                self._check_response(config)
                match = re.search(r"\bDEVICE\s*:\s*['\"](?:datacard/)?([^'\"]+)['\"]", config.text)
                if match is None:
                    raise _ReadFailure(DeviceReadIssue.IDENTITY_UNKNOWN)
                observed_model = match.group(1).strip()
                model = observed_model
                if observed_model.casefold() != "mf833t":
                    compatibility = Compatibility.MISMATCH
                    raise _ReadFailure(DeviceReadIssue.MODEL_MISMATCH)
                model = "MF833T"
                response = await self._client.get(
                    "/goform/goform_get_cmd_process",
                    params={"isTest": "false", "cmd": _COMMAND, "multi_data": "1"},
                )
                self._check_response(response)
                data = response.json()
                if not isinstance(data, dict) or not data:
                    raise _ReadFailure(DeviceReadIssue.INVALID_RESPONSE)
                if data.get("loginfo") == "no":
                    raise _ReadFailure(DeviceReadIssue.AUTH_REQUIRED)
                if data.get("result") in ("failure", "fail"):
                    raise _ReadFailure(DeviceReadIssue.INVALID_RESPONSE)
                variant = DeviceVariant(
                    _text(data, "wa_inner_version"), _text(data, "hardware_version"), "http-management"
                )
                compatibility = self._compatibility(variant)
                if not {"network_provider", "network_type", "signalbar"} <= data.keys():
                    raise _ReadFailure(DeviceReadIssue.INVALID_RESPONSE)
                provider = _text(data, "network_provider")
                network_type = _text(data, "network_type")
                bars = data["signalbar"]
                if not isinstance(bars, str) or not re.fullmatch(r"[0-5]", bars):
                    raise _ReadFailure(DeviceReadIssue.INVALID_RESPONSE)
                signal = int(bars) * 20
                availability = Availability.READY
        except _ReadFailure as exc:
            issue = exc.issue
            availability = (
                Availability.UNAVAILABLE
                if issue in (DeviceReadIssue.AUTH_REQUIRED, DeviceReadIssue.MODEL_MISMATCH)
                else Availability.UNKNOWN
            )
        except (TimeoutError, httpx.TimeoutException):
            issue, availability = DeviceReadIssue.TIMEOUT, Availability.UNAVAILABLE
        except httpx.HTTPError:
            issue, availability = DeviceReadIssue.OFFLINE, Availability.UNAVAILABLE
        except (ValueError, UnicodeError):
            issue, availability = DeviceReadIssue.INVALID_RESPONSE, Availability.UNKNOWN

        if availability is not Availability.READY:
            provider = network_type = signal = None
        now = datetime.now(UTC)
        return (
            DeviceObservation(now, availability, compatibility, model, variant, issue),
            DeviceStatus(availability, now, provider, network_type, signal, issue),
        )

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        if response.status_code in (401, 403) or response.is_redirect:
            raise _ReadFailure(DeviceReadIssue.AUTH_REQUIRED)
        response.raise_for_status()

    @staticmethod
    def _compatibility(variant: DeviceVariant) -> Compatibility:
        if variant.firmware is None or variant.hardware_revision is None:
            return Compatibility.UNKNOWN
        for evidence in MANIFEST.compatibility_evidence:
            if (
                evidence.variant == variant
                and evidence.kind is VerificationKind.DEVICE_VERIFICATION
                and set(MANIFEST.capabilities) <= set(evidence.capabilities)
            ):
                return Compatibility.VERIFIED
        return Compatibility.UNTESTED
