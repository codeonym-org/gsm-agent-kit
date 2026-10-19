TanStack Query owns server data. Keys include logical device and pagination;
credentials never enter keys. API errors are normalized in api/client. Each
connection gets a fresh cache so authentication changes cannot reuse data.

The realtime provider invalidates inbox, assistant, job and submission reads.
Hardware status and configured-device queries poll every 30 seconds. Balance
consultation and SMS submission are explicit actions, never query refetches.
