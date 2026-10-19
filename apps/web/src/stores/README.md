Zustand holds memory-only view state: the selected device, open dialogs and manual
SMS drafts/request IDs. It does not cache API results or store credentials. All
server data is owned by TanStack Query. Disconnecting clears drafts and view
state; closing a dialog preserves its existing request rather than resending.
