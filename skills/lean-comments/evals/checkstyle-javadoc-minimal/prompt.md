---
tags: [skill-creator]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Add a `ProviderAvailability` class in the `availability` package with fields providerId (UUID), date (LocalDate), slots (List<LocalTime>) and zone (ZoneId), a constructor, getters, and a `boolean isAvailableAt(LocalTime time)` that checks whether the time is one of the slots. It has to pass our checkstyle config.

Input files: config/checkstyle/checkstyle.xml, src/main/java/com/example/booking/availability/ProviderSchedule.java
