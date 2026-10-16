"""MF833T inbox decoding. Vendor fields are deliberately confined to the adapter."""

import re

from gsm_agent_core.domain.sms import InboxItem, SmsAddress


def parse_item(row: object) -> InboxItem | None:
    if not isinstance(row, dict):
        raise ValueError("Invalid SMS row")
    tag = row.get("tag")
    if isinstance(tag, bool) or str(tag) not in ("0", "1", "2", "3", "4"):
        raise ValueError("Unknown SMS tag")
    if str(tag) not in ("0", "1"):
        return None
    provider_id = row.get("id")
    if isinstance(provider_id, bool) or not re.fullmatch(r"[0-9]{1,20}", str(provider_id)):
        raise ValueError("Invalid SMS slot")
    sender, date, content = row.get("number"), row.get("date"), row.get("content")
    if not isinstance(sender, str) or not isinstance(date, str) or not date or len(date) > 128:
        raise ValueError("Invalid SMS metadata")
    if (
        not isinstance(content, str)
        or len(content) > 65536
        or not re.fullmatch(r"(?:[0-9a-fA-F]{4})*", content)
    ):
        raise ValueError("Invalid SMS wire encoding")
    complete = row.get("received_all_concat_sms", "1")
    if isinstance(complete, bool) or str(complete) not in ("0", "1"):
        raise ValueError("Invalid concatenation state")
    return InboxItem(
        str(provider_id),
        SmsAddress.from_sender(sender),
        bytes.fromhex(content).decode("utf-16-be"),
        date,
        str(complete) == "1",
    )
