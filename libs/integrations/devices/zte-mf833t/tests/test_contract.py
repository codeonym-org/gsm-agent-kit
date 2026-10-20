from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_standard_tests import DeviceContractTests
from gsm_agent_zte_mf833t import ZteMf833tDevice, ZteMf833tSettings


@pytest_asyncio.fixture
async def cellular_device() -> AsyncIterator[ZteMf833tDevice]:
    def respond(request: httpx.Request) -> httpx.Response:
        # This guard also proves the shared suite never dispatches SMS/USSD writes.
        assert request.method == "GET"
        if request.url.path == "/js/config/config.js":
            return httpx.Response(200, text="DEVICE: 'datacard/mf833T'")
        assert request.url.path == "/goform/goform_get_cmd_process"
        if request.url.params.get("cmd") == "sms_page_data":
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "id": "1",
                            "number": "+212600000000",
                            "date": "26;01;01;12;00;00;+00",
                            "content": "Synthetic incomplete SMS".encode("utf-16-be").hex(),
                            "tag": "1",
                            "received_all_concat_sms": "0",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "wa_inner_version": "fixture-firmware",
                "hardware_version": "fixture-hardware",
                "network_provider": "Fictional carrier",
                "network_type": "LTE",
                "signalbar": "3",
            },
        )

    device = ZteMf833tDevice(
        CellularDeviceId("contract-zte"),
        ZteMf833tSettings("http://device.invalid"),
        transport=httpx.MockTransport(respond),
    )
    try:
        yield device
    finally:
        await device.close()


class TestZteDeviceContract(DeviceContractTests):
    pass
