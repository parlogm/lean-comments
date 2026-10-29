---
tags: [skill-creator]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Implement SHOP-412: add src/payments/refundWebhook.ts exporting handleRefundWebhook(event: RefundEvent, ledger: Ledger): Promise<void>, and define the RefundEvent type there (id, orderId, amount, currency). Context from the ticket: the payment provider used to send refund amounts in dollars on the legacy v1 API but v2 sends integer cents; we migrated in SHOP-377 and SHOP-390 deleted the v1 adapter, so always treat amount as cents. The provider retries webhooks for up to 3 days, so the handler has to be idempotent: do nothing if ledger.hasRefund(event.id). Only USD is supported for now, throw on anything else. In the architecture review we debated pushing these through a queue but decided against it because volume is around 20 a day. Ledger amounts are dollars.

Input files: package.json, src/payments/ledger.ts
