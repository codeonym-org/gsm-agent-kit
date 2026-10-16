# GSM Agent Kit

Shared language for SIM-capable cellular devices, their capabilities and mobile-network exchanges.
These terms describe the domain independently of a device model, protocol or framework.

## Language

### Cellular devices and capabilities

**Cellular device**:
A physical device or embedded module that provides access to a mobile network using a SIM and exposes a set of operations to a host machine.
_Avoid_: Modem as the universal category, SIM card

**Logical cellular device**:
An application-recognized cellular device identity that remains meaningful across reconnections and changes in its connection address.
_Avoid_: USB path, message ID as a device identity

**Device model**:
A manufacturer-designated model of cellular device, distinct from an individual physical device and from its supported operations.
_Avoid_: Protocol, manufacturer name alone

**Device variant**:
A hardware revision, firmware version and operating mode combination of a device model that can affect its exposed operations.
_Avoid_: Model name alone when describing verified behavior

**SIM**:
A subscriber identity module associated with a mobile-network subscription; it is distinct from the cellular device hosting it.
_Avoid_: Cellular device, carrier account

**Device capability**:
A defined kind of operation, such as SMS, voice calling or multimedia messaging, supported by a cellular device in its current configuration.
_Avoid_: Availability, model name as a substitute for supported operations

**Capability availability**:
The observed readiness of a supported device capability at a particular time, which may be ready, busy, unavailable or unknown.
_Avoid_: Support when referring to temporary readiness

**Inbox source**:
The origin of stored inbound SMS messages, identified by the logical cellular device, the relevant SIM or storage generation, and the storage location.
_Avoid_: Sender, unread status as a source identity

**Stored-message identity**:
The identity of a particular stored SMS occurrence within an inbox source, distinguishing it from later messages that reuse a storage identifier.
_Avoid_: Device ID, message text alone

### SMS and replies

**SMS message**:
An independently addressed text message carried by SMS, potentially composed of multiple SMS segments.
_Avoid_: Segment when referring to the whole message

**SMS segment**:
One transport-sized portion of an SMS message whose capacity depends on its encoding and transport headers.
_Avoid_: Character count, reply part

**Concatenated SMS**:
One SMS message carried by multiple segments with transport metadata identifying their relationship and order.
_Avoid_: Numbered independent SMS messages, multi-message reply

**Reply**:
A response to an incoming SMS message, expressed as one or more outgoing SMS messages.
_Avoid_: Submission, delivery

**Reply part**:
One independently addressed outgoing SMS message in a reply that spans multiple messages.
_Avoid_: Concatenated segment

### Submission and delivery

**SMS submission**:
The operation of presenting an outgoing SMS message to the cellular device or its provider for sending.
_Avoid_: Delivery

**Submission attempt**:
One attempt to perform an SMS submission; multiple attempts may concern the same intended outgoing message.
_Avoid_: New message when referring only to a retry

**Submission acceptance**:
An acknowledgement from the cellular device or provider that an SMS submission was accepted for sending, without establishing recipient delivery.
_Avoid_: Delivered, received by the recipient

**Unknown submission outcome**:
A submission outcome for which available evidence cannot establish whether the message was accepted or rejected.
_Avoid_: Failed, safe to resend

**SMS delivery**:
The arrival of an SMS message at its destination, established by delivery evidence distinct from submission acceptance.
_Avoid_: Accepted, send request succeeded

### Carrier consultations

**USSD session**:
A mobile-network interaction comprising a USSD request and its response, with possible continuation prompts until it ends or is cancelled.
_Avoid_: Balance consultation as a synonym for every USSD interaction

**Balance consultation**:
An observation of carrier account credit or remaining allowances that does not purchase, recharge or subscribe to an offer.
_Avoid_: Arbitrary USSD execution, offer activation

**Credit balance**:
A carrier-reported monetary amount available on a mobile-network account, qualified by its currency and any reported validity conditions.
_Avoid_: SMS allowance, message count

**SMS allowance**:
A carrier-reported entitlement to send a quantity of SMS messages, qualified by any reported scope and expiry conditions.
_Avoid_: Credit balance, money
