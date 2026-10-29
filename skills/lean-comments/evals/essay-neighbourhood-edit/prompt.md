---
tags: [skill-creator]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Add a cancelRegistration(String customerId) method to RegistrationService. It calls partnerClient.deleteCustomer(customerId), but the partner answers 409 when the customer still has open orders; in that case throw a new RegistrationLockedException (create it, unchecked) instead of letting the PartnerHttpException escape. Any other status should propagate unchanged. The partner does not document the 409 body, so do not try to parse it.

Input files: src/main/java/com/example/onboarding/partner/
