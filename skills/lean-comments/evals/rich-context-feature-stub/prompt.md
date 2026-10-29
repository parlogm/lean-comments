---
tags: [skill-creator]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Implement ABC-2410. Context from the ticket: the bulk export endpoint (ABC-1024) needs an entitlement check before it returns customer data, but the entitlements service does not exist yet. The epic ABC-1210 is waiting on ABC-2281 (a spike), then ABC-2153 (data model and API), then ABC-2354 (enterprise tiers), and none of them has started, so there is no contract to integrate against. In the design review we agreed to ship a stub EntitlementGateway that grants every check so the endpoint can be built and reviewed. Important: that means the endpoint returns customer data with no entitlement gate. What protects deployed environments is the reports:export:all role, which must not be granted in production until ABC-2153 lands. Once ABC-2153 is done this gets replaced by a remote gateway that calls the entitlements API and fails closed. We considered a feature flag instead but rejected it because the flag service can't be read from this module.

Add PlaceholderEntitlementGateway in the entitlement package implementing EntitlementGateway. Log a warning once, on first use, saying entitlements are not enforced (java.util.logging, no frameworks in this module).

Input files: src/main/java/com/example/reports/entitlement/EntitlementGateway.java
